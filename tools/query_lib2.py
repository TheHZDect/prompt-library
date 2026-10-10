"""Phase 5 检索入口 query_lib2.py
两件事：
  search  关键词/短语检索（FTS5 trigram + 词表同义扩展 + 家族/风格/线过滤）
  route   意图 -> 家族排序（风格×场景×产物 命中 + 对 useWhen 的 BM25）
零依赖，只用标准库 sqlite3。"""
import os, re, sys, json, sqlite3, argparse, collections
import paths as P
import famlib as F

LIB = P.CACHE
DB = os.path.join(LIB, 'prompts.db')
FAM_JSON = os.path.join(LIB, 'library.json')

# 仓库模式仓库根 R 的解析顺序：脚本自定位（本脚本在 <R>/tools/ 下，父目录含 data/ 与
# agents/ 即认定仓库根——仓库版优先自身位置，保证 clone 后零配置可用）→ PROMPT_LIB_HOME
# 环境变量（显式改道）→ 脚本旁/上级 lib_home.txt（install.mjs 写入）→ 本地工作区路径。
# 技能被复制到任何位置后，只要按 SKILL.md 用 <R>/tools/ 绝对路径调用，不依赖 cwd、不依赖环境变量。
_HERE = os.path.dirname(os.path.abspath(__file__))
_cand = os.path.dirname(_HERE)
if os.path.isdir(os.path.join(_cand, 'data')) and os.path.isdir(os.path.join(_cand, 'agents')):
    _HOME = _cand
else:
    _HOME = os.environ.get('PROMPT_LIB_HOME')
    if not _HOME:
        for _p in (os.path.join(_HERE, 'lib_home.txt'), os.path.join(os.path.dirname(_HERE), 'lib_home.txt')):
            if os.path.exists(_p):
                _HOME = open(_p, encoding='utf-8').read().strip()
                break
if _HOME:
    LIB = os.path.join(_HOME, '.cache')
    DB = os.path.join(LIB, 'prompts.db')
    FAM_JSON = os.path.join(_HOME, 'agents', 'skills', 'prompt-library', 'references', 'library.json')

THUMB_BASE = os.path.join(_HOME, 'assets', 'thumbs') if _HOME else P.THUMB

if not os.path.exists(FAM_JSON):
    sys.exit('找不到家族定义 %s：请在仓库根跑 python tools/rebuild_db.py（脚本自定位仓库根，无需环境变量）' % FAM_JSON)

FAMS = {f['id']: f for f in json.load(open(FAM_JSON, encoding='utf-8'))['families']}

# 同义扩展表：风格/场景/光线/人像风格四路 + 人工维护的 SEARCH_SYNONYMS。
# 不含 SUBJECT_RULES_HEAD：那是分类判别器，组内是同类并列（女性/运动员/骑士 同现率仅 0.0–0.3%），
# 一旦展开成同义词，任何主体词都能召回全部主体。
SYN = collections.defaultdict(set)
for group in list(F.STYLE_SEG_WORDS.values()) + list(F.SCENES.values()) + \
             [F.LIGHTING[k] for k in F.LIGHTING] + [p[2] for p in F.PORTRAIT_STYLE_PRIORITY] + \
             list(F.SEARCH_SYNONYMS):
    words = [w for w in group if '(?' not in w]
    for w in words:
        SYN[w] |= set(words)

# 识别词表：只用于"从 query 里切出词表片段"，不参与同义展开。
# 必须比 SYN 宽——主体/产物判别词（仙女、新郎、珠宝）该被认出来，但不该被同义替换。
VOCAB = set(SYN)
for _g in ([s[1] for s in F.SUBJECT_RULES_HEAD] + [a[1] for a in F.ARTIFACT_RULES] +
           [list(F.ARTIFACT_NAME.values()) + list(F.SUBJECT_NAME.values()) + list(F.SCENE_NAME.values())] +
           [[p[1] for p in F.PORTRAIT_STYLE_PRIORITY]]):
    VOCAB |= {w.split('(')[0] for w in _g}   # 断言只服务分类精度，识别时剥掉留词干
    VOCAB.discard('')


def expand(q):
    """query 里出现的每个词表术语，扩成该术语所在的同义组"""
    terms = set()
    for w, syn in SYN.items():
        if w and w in q:
            terms |= {s for s in syn if len(s) >= 2}
    if not terms:
        terms = {t for t in re.split(r'[\s,，、]+', q) if t}
    return terms


# 文档频率表（phase2c_df.py 产出）：供残余片段自动成词做噪声过滤
DFN = 0
_dfcon = None
if os.path.exists(os.path.join(LIB, 'df_terms.db')) and os.path.exists(os.path.join(LIB, 'df_meta.json')):
    _dfcon = sqlite3.connect(os.path.join(LIB, 'df_terms.db'))
    DFN = json.load(open(os.path.join(LIB, 'df_meta.json'), encoding='utf-8'))['n_cases']
_df_cache = {}


def _df(term):
    if not _dfcon: return 0
    if term not in _df_cache:
        r = _dfcon.execute('SELECT n FROM df WHERE term=?', (term,)).fetchone()
        _df_cache[term] = r[0] if r else 0
    return _df_cache[term]


FUNC_CHARS = set('的了是在和与及对于这张个些主被让给从到就都也又而着种样其之每一二三我你他她它们')


def _residual_terms(seg, keep):
    """片段里未被已选词覆盖的中文串，按文档频率挑出值得当检索词的实体名。
    属性/配饰/具体物件（墨镜、冰淇淋、霰弹枪）是开放长尾，不枚举进词表；
    DF 下限挡截断碎片，上限挡"画面/整体/高分辨率"这类套话。"""
    if not _dfcon:
        return []
    cover = [False] * len(seg)
    for w in sorted(keep, key=len, reverse=True):
        i = seg.find(w)
        while i >= 0:
            for j in range(i, min(i + len(w), len(seg))): cover[j] = True
            i = seg.find(w, i + 1)
    cands, run = set(), ''
    for ch, c in zip(seg + ' ', cover + [True]):      # 哨兵与字符两侧等长，否则末段永不冲刷
        if not c and '一' <= ch <= '鿿':
            run += ch
            continue
        if len(run) >= 2:
            for n in (2, 3):
                for i in range(len(run) - n + 1): cands.add(run[i:i + n])
        run = ''
    lo, hi = max(10, DFN // 3000), max(DFN // 12, 50)
    # 含虚词的片段（一个穿/她的帽）不是实体名，DF 再合适也要丢
    scored = sorted((_df(t), t) for t in cands
                    if lo <= _df(t) <= hi and not any(f in t for f in FUNC_CHARS))
    return [t for _c, t in scored[:1]]


def _segs(q):
    return [t for t in re.split(r'[\s,，、。;；：:！!？?]+', q) if t]


def _split_terms(q):
    """每个片段先用识别词表切出词表术语（长词优先、丢被包含的），再补单字主体词与
    残余实体词；三者都没有才整段当检索词。"""
    out = []
    for s in _segs(q):
        inside = sorted({w for w in VOCAB if w and w in s}, key=len, reverse=True)
        keep = []
        for w in inside:
            if not any(w in k for k in keep): keep.append(w)
        for m in F.SUBJECT_MONOGRAMS:
            if m in s and not any(m in k or k in m for k in keep): keep.append(m)
        keep += [t for t in _residual_terms(s, keep) if t not in keep]
        out.extend(keep or [s])
    return out


def build_query(q):
    """组内 OR（同义替换）、组间 AND（每个原始词都要满足）。
    同组的长词走 FTS、短词走 LIKE，并存时都要参与——丢短词会让用户原话从查询里消失。"""
    groups = []
    for t in _split_terms(q):
        var = {t} | set(SYN.get(t, ()))
        longv = sorted(v for v in var if len(v) >= 3 and not re.search(r'[:*()^"]', v))
        shortv = sorted(v for v in var if len(v) == 2)
        if not longv and not shortv and t:
            shortv = [t]
        if longv or shortv:
            groups.append((longv, shortv, t))
    return groups


def _group_ids(con, longv, shortv):
    """一个同义组的命中集合：长词走 trigram 索引，短词回退子串扫描，取并集。"""
    ids = set()
    if longv:
        expr = ' OR '.join('"%s"' % t for t in longv)
        ids |= {r[0] for r in con.execute(
            'SELECT entry_id FROM cases_fts WHERE cases_fts MATCH ?', (expr,))}
    if shortv:
        ids |= {r[0] for r in con.execute(
            'SELECT entry_id FROM cases WHERE ' + ' OR '.join(['text LIKE ?'] * len(shortv)),
            ['%' + t + '%' for t in shortv])}
    return ids


def search(q, k=10, line=None, family=None, style=None, scene=None, aspect=None, needs=None):
    rows, _, _ = search_relaxed(q, k, line, family, style, scene, aspect, needs)
    return rows


def search_relaxed(q, k=10, line=None, family=None, style=None, scene=None, aspect=None, needs=None):
    """返回 (rows, dropped, blocked)。
    - 交集为空：按命中集从小到大逐级放宽，dropped 报告放弃过哪些词。
    - 交集非空但被 --family/--style/… 过滤掏空：blocked 报告每个过滤的单独命中数，
      归因"哪个过滤拦光的"还是"各自都有但组合为空"。
    两条路径都必须出声——静默"无结果"会让使用者误以为库里没有（过滤同理）。"""
    groups = build_query(q)
    if not groups:
        return [], [], []
    con = sqlite3.connect(DB)
    hits = [(term, longv + shortv, _group_ids(con, longv, shortv)) for longv, shortv, term in groups]
    idxs = list(range(len(hits)))
    ids = set()
    while idxs:
        ids = None
        for i in idxs:
            ids = hits[i][2] if ids is None else ids & hits[i][2]
            if not ids:
                break
        if ids:
            break
        idxs.remove(min(idxs, key=lambda i: len(hits[i][2])))
    dropped = [hits[i][0] for i in range(len(hits)) if i not in idxs]
    if not ids:
        con.close()
        return [], dropped, []
    allterms = [t for i in idxs for t in hits[i][1]]
    con.execute('CREATE TEMP TABLE _hits(id TEXT PRIMARY KEY)')
    con.executemany('INSERT INTO _hits(id) VALUES(?)', ((i,) for i in ids))
    sql = ('SELECT c.entry_id, c.family_id, c.line, c.date, c.source_docx, c.start_para, c.end_para, '
           'c.imgs, c.media, c.char_len, c.style, c.text FROM cases c JOIN _hits h ON h.id=c.entry_id')
    conds = []                                    # (标签, SQL, 参数)
    if line: conds.append(('--line ' + line, 'c.line=?', line))
    if family: conds.append(('--family ' + family, 'c.family_id LIKE ?', family + '%'))
    if style: conds.append(('--style ' + style, 'c.style LIKE ?', '%' + style + '%'))
    if scene: conds.append(('--scene ' + scene, 'c.scene=?', scene))
    if aspect: conds.append(('--aspect ' + aspect, 'c.aspect_state=?', aspect))
    if needs is not None: conds.append(('--needs %d' % needs, 'c.needs_input=?', needs))
    if conds:
        cnt_sql = 'SELECT COUNT(*) FROM cases c JOIN _hits h ON h.id=c.entry_id'
        blocked = [(lab, con.execute(cnt_sql + ' WHERE ' + cond, (p,)).fetchone()[0])
                   for lab, cond, p in conds]
        rows = list(con.execute(sql + ' WHERE ' + ' AND '.join(c for _l, c, _p in conds),
                               [p for _l, _c, p in conds]))
        if not rows:
            con.close()
            return [], dropped, blocked           # 词集非空、被过滤掏空 → 交 CLI 归因
    else:
        rows = list(con.execute(sql))
    con.close()
    out = []
    exact_segs = [s for s in _segs(q) if len(s) >= 3]
    for r in rows:
        text = r[11] or ''
        seg = F.segments(text) if text else {}
        scope = seg.get('style', '') + seg.get('core', '')
        cnt = sum(text.count(t) for t in allterms)
        exact = 40 * sum(1 for s in exact_segs if s in text)
        score = exact + 2 * sum(scope.count(t) for t in allterms) + cnt / (1 + r[9] / 600.0)
        out.append(r[:11] + (score, text[:200]))
    out.sort(key=lambda x: (-x[11], -x[9]))
    return out[:k], dropped, []


_PSTYLE_KW = {fid: [k.lower() for k in kws] for fid, _n, kws in F.PORTRAIT_STYLE_PRIORITY}
_ART_KW = {aid: [k for k in kws] for aid, kws in F.ARTIFACT_RULES}
_SUBJ_KW = {sid: [k for k in kws] for sid, kws in F.SUBJECT_RULES_HEAD}

def _fam_keywords(f):
    base = f['parent']
    kw = set()
    for s in (f.get('tag_style') or {}):
        kw |= set(F.STYLE_SEG_WORDS.get(s, []))
    if base.startswith('portrait_'):
        kw |= set(_PSTYLE_KW.get(base[len('portrait_'):], []))
    elif base.startswith('photo_'):
        kw |= set(_SUBJ_KW.get(base[len('photo_'):], []))
    else:
        kw |= set(_ART_KW.get(base, []))
    if f.get('scene'):
        kw |= set(F.SCENES.get(f['scene'], []))
    kw |= {f['name'], f['name_en']}
    return {k.lower() for k in kw if k}


FAM_KW = {fid: _fam_keywords(f) for fid, f in FAMS.items()}


PERSON_HINTS = set(sum([k for sid, k in _SUBJ_KW.items() if sid == 'portrait'], [])) | \
               {'女生', '写真', '自拍', '女性', '男士', '女士', '男孩', '人物'}


def _route_signals(q):
    """查询命中的词表信号。全空说明说法在词表外，此时的排序只是兜底。"""
    low = q.lower()
    sig = {}
    sig['style'] = {s for s, kws in F.STYLE_SEG_WORDS.items() if any(k.lower() in low for k in kws)}
    sig['pstyle'] = [fid for fid, kws in _PSTYLE_KW.items() if any(k in low for k in kws)]
    sig['scene'] = {sc for sc, kws in F.SCENES.items() if any(kw in q for kw in kws)}
    sig['art'] = next((aid for aid, kws in _ART_KW.items()
                       if any((re.search(k, q) if '(?' in k else k in q) for k in kws)), None)
    sig['subj'] = {sid for sid, kws in _SUBJ_KW.items()
                   if any((re.search(k, low) if '(?' in k else k in low) for k in kws)}
    sig['person'] = 'portrait' in sig['subj'] or any(w in q for w in PERSON_HINTS)
    return sig


def route(q, k=5):
    """意图 -> 家族排序：词表信号加权，中文整句不依赖空白分词。"""
    sig = _route_signals(q)
    qstyle, qpstyle = sig['style'], sig['pstyle']
    qart, qsubj, has_person = sig['art'], sig['subj'], sig['person']
    low = q.lower()

    scored = []
    for fid, fam in FAMS.items():
        base = fam['parent']
        is_portrait = base.startswith('portrait_')
        is_artifact = base in F.ARTIFACT_NAME and base != 'photo'
        s = 0.0
        s += 3.0 * len(qstyle & set(fam.get('tag_style') or {}))
        if qpstyle and base == f'portrait_{qpstyle[0]}': s += 5.0
        elif qpstyle and base in {f'portrait_{p}' for p in qpstyle}: s += 2.0
        if is_portrait and not has_person: s -= 7.0          # 人物闸门：没提人就不给像族
        if is_artifact:
            s += 6.0 if qart == base else -8.0                # 产物族必须有产物意图
        elif qart:
            s -= 6.0
        if base.startswith('photo_') and base[6:] in qsubj: s += 2.5
        elif qsubj and base.startswith('photo_'): s -= 5.0   # 主体闸门：背景词不得越主主体
        if is_portrait and qsubj and 'portrait' not in qsubj: s -= 6.0   # 主体优先于风格（机甲战士属机本，不属赛博人像）
        s += 1.2 * sum(1 for kw in FAM_KW[fid] if kw and kw.lower() in low)
        scored.append((s, fid, fam))
    scored.sort(key=lambda x: (-x[0], -x[2]['count']))
    return scored[:k]


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['search', 'route', 'family'])
    ap.add_argument('arg')
    ap.add_argument('-k', type=int, default=10)
    ap.add_argument('--line', choices=['main', 'daily', 'kook'])
    ap.add_argument('--family'); ap.add_argument('--style'); ap.add_argument('--scene')
    ap.add_argument('--aspect', choices=['explicit', 'slot', 'none'], help='画幅声明三态过滤（C1）')
    ap.add_argument('--needs', type=int, choices=[0, 1], help='1=需要参考图/填空的半截话模板，0=拿来即用')
    a = ap.parse_args()
    if a.cmd == 'route':
        sig = _route_signals(a.arg)
        if not (sig['style'] or sig['pstyle'] or sig['scene'] or sig['art'] or sig['subj']):
            print('（词表未命中：说法在标签词表外，以下排序为兜底，参考性低）')
        elif sig['scene']:
            print('（场景是标签不是家族，收窄请用 search --scene %s）' % '|'.join(sorted(sig['scene'])))
        for s, fid, fam in route(a.arg, a.k):
            print(f'[{s:5.1f}] {fid:26s} {fam["name"]:20s} n={fam["count"]:5d}  {fam["useWhen"][:54]}')
    elif a.cmd == 'family':
        fam = FAMS.get(a.arg)
        if not fam: print('无此家族'); sys.exit(1)
        print(json.dumps(fam, ensure_ascii=False, indent=1))
    else:
        rows, dropped, blocked = search_relaxed(a.arg, a.k, a.line, a.family, a.style, a.scene, a.aspect, a.needs)
        if not rows:
            if blocked:
                zero = [lab for lab, n in blocked if n == 0]
                if zero:
                    print('无结果：%s 单独命中 0，是它拦光的；去掉该过滤再试。' % '、'.join(zero))
                else:
                    print('无结果：各过滤单独都有命中（%s），但组合为空；逐个放宽。'
                          % ' '.join('%s=%d' % (lab, n) for lab, n in blocked))
            else:
                print('无结果')
            sys.exit(0)
        if dropped: print('（未命中，已放宽：%s）' % '、'.join(dropped))
        th = {}
        if rows:
            try:
                c2 = sqlite3.connect(DB)
                ids = [r[0] for r in rows]
                for eid, tp in c2.execute('SELECT entry_id, thumbs FROM cases WHERE entry_id IN (%s)'
                                          % ','.join('?' * len(ids)), ids):
                    th[eid] = tp or ''
                c2.close()
            except sqlite3.OperationalError:
                pass                                    # 老库还没 thumbs 列
        for r in rows:
            print(f'[{r[11]:7.2f}] {r[0]}  {r[2]}/{r[3]}  {r[4]} 段{r[5]}-{r[6]}  族={r[1]}  len={r[9]}')
            print(f'    图={r[7]}')
            if th.get(r[0]):
                # 库内 thumbs 存的是相对缩略图根的路径；工作区根=库\缩略图，仓库根=assets\thumbs
                tp = th[r[0]]
                print('    缩略图=%s' % (tp if os.path.isabs(tp) else os.path.join(THUMB_BASE, tp.replace('/', os.sep))))
            print(f'    {r[12]!r}'[:200])
