"""从仓库内 data/ 重建检索库到 .cache/（不进 git）。仓库自洽：不需要源 docx、不需要工作区。

  python tools/rebuild_db.py            # 重建 .cache/prompts.db + .cache/df_terms.db
  python tools/rebuild_db.py --verify   # 重建后跑一组自检 query

产出与原库同构：cases(20 列 + thumbs) + cases_fts(trigram) + families。
"""
import os, sys, csv, json, hashlib, sqlite3, re, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, 'data')
CACHE = os.path.join(ROOT, '.cache')
sys.path.insert(0, HERE)
import famlib as F                                              # noqa: E402

CJK = re.compile(r'[一-鿿]+')
COLS = ('entry_id, line, date, source_docx, start_para, end_para, img_count, imgs, media,'
        ' char_len, text_fp, note, dup_of, family_id, style, subject, scene, text,'
        ' aspect_state, needs_input, thumbs')


def load_names():
    """data/batch_source.tsv 台账：批次 -> 源 docx 的真实文件名（工作区入库时登记）。"""
    p = os.path.join(DATA, 'batch_source.tsv')
    out = {}
    for c in read_entries(p):
        if c.get('batch'):
            out[c['batch']] = c.get('source_docx') or ''
    out.setdefault('2026H1_主库', out.get('main', ''))        # 仓库侧 main 用的是中文目录名
    return out


def batch_meta(batch, names=None):
    """批次目录名 -> (line, date, source_docx)；台账缺失时退回按目录名推导。"""
    names = names or {}
    if batch.startswith('d') and len(batch) == 5:
        return 'daily', '26-%s-%s' % (batch[1:3], batch[3:5]), names.get(batch) or batch + '.docx'
    if batch.startswith('k') and len(batch) == 5:
        return 'kook', '26-%s-%s' % (batch[1:3], batch[3:5]), names.get(batch) or batch + '.docx'
    return 'main', '2026-H1', names.get(batch) or batch


def read_entries(path):
    """必须 QUOTE_NONE：text_flat 常以引号开头，默认解析会凭空改坏正文（硬规则 6）。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding='utf-8-sig', newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t', quoting=csv.QUOTE_NONE))


def load_thumbs():
    p = os.path.join(DATA, 'thumbs_index.tsv')
    out = {}
    if not os.path.exists(p):
        return out
    with open(p, encoding='utf-8-sig') as fh:
        for line in fh:
            c = line.rstrip('\n').split('\t')
            if len(c) >= 2 and c[0] != 'entry_id':
                out[c[0]] = c[1]
    return out


def collect():
    thumbs = load_thumbs()
    names = load_names()
    rows = []
    for batch in sorted(os.listdir(DATA)):
        d = os.path.join(DATA, batch)
        if not os.path.isdir(d):
            continue
        line, date, docx = batch_meta(batch, names)
        for r in read_entries(os.path.join(d, 'entries.tsv')):
            text = (r.get('text_flat') or '').replace('\\n', '\n')
            if not text.strip():
                continue
            eid = r['entry_id']
            imgs = [x for x in (r.get('imgs') or '').split('|') if x.strip()]
            art = F.classify_artifact(text)
            subj = F.classify_subject(text) if art == 'photo' else ''
            fid, _ = F.family_of(text, art, subj)
            rows.append((eid, line, date, docx, int(r.get('start_para') or 0), int(r.get('end_para') or 0),
                         int(r.get('img_count') or 0), '|'.join(imgs), '',
                         int(r.get('char_len') or len(text)), hashlib.sha256(text.encode()).hexdigest()[:16],
                         r.get('note') or '', None, fid, '|'.join(F.style_tags(text)), subj,
                         F.scene_of(text), text, F.aspect_state(text), F.needs_input(text), thumbs.get(eid, '')))
    return rows


def write_db(rows):
    os.makedirs(CACHE, exist_ok=True)
    db = os.path.join(CACHE, 'prompts.db')
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.execute('''CREATE TABLE cases(
        entry_id TEXT PRIMARY KEY, line TEXT, date TEXT, source_docx TEXT,
        start_para INTEGER, end_para INTEGER, img_count INTEGER, imgs TEXT, media TEXT,
        char_len INTEGER, text_fp TEXT, note TEXT, dup_of TEXT,
        family_id TEXT, style TEXT, subject TEXT, scene TEXT, text TEXT,
        aspect_state TEXT, needs_input INTEGER, thumbs TEXT)''')
    con.execute("CREATE VIRTUAL TABLE cases_fts USING fts5(entry_id UNINDEXED, text, tokenize='trigram')")
    con.executemany('INSERT INTO cases VALUES(%s)' % ('?,' * 20 + '?'), rows)
    con.executemany('INSERT INTO cases_fts VALUES(?,?)', [(r[0], r[17]) for r in rows])
    con.execute('CREATE INDEX idx_line ON cases(line)')
    con.execute('CREATE INDEX idx_family ON cases(family_id)')
    con.execute('CREATE TABLE families(family_id TEXT PRIMARY KEY, name TEXT, parent TEXT, scene TEXT, count INTEGER)')
    cnt = {}
    for r in rows:
        cnt[r[13]] = cnt.get(r[13], 0) + 1
    con.executemany('INSERT INTO families VALUES(?,?,?,?,?)',
                    [(f, f, f, '', c) for f, c in cnt.items()])
    con.commit()
    con.close()
    return db, len(cnt)


def write_df(rows):
    """文档频率表：残余片段自动成词的噪声过滤依据（与 phase2c_df.py 同判据）。"""
    df = {}
    for r in rows:
        seen = set()
        for run in CJK.findall(r[17]):
            for n in (2, 3):
                for i in range(len(run) - n + 1):
                    seen.add(run[i:i + n])
        for g in seen:
            df[g] = df.get(g, 0) + 1
    db = os.path.join(CACHE, 'df_terms.db')
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE df(term TEXT PRIMARY KEY, n INTEGER) WITHOUT ROWID')
    con.executemany('INSERT INTO df VALUES(?,?)', df.items())
    con.commit()
    con.close()
    json.dump({'n_cases': len(rows), 'n_terms': len(df)},
              open(os.path.join(CACHE, 'df_meta.json'), 'w', encoding='utf-8'))
    return len(df)


VERIFY = ['女性 国风', '猫戴着墨镜', '一个穿汉服的姑娘在雨里撑伞', '老板在会议室看投影', '人像 复古 街道']


def verify():
    os.environ['PROMPT_LIB_HOME'] = ROOT
    import importlib
    for m in ('build_docx', 'query_lib2'):
        if m in sys.modules:
            del sys.modules[m]
    sys.path.insert(0, HERE)
    import query_lib2 as Q
    importlib.reload(Q)
    ok = 0
    for q in VERIFY:
        rows = Q.search_relaxed(q, k=3)[0]
        fams = [r[1] for r in rows[:2]]
        print('  %-24s terms=%-22s %s' % (q, '/'.join(Q._split_terms(q))[:22], ' | '.join(fams) or '无结果'))
        ok += bool(rows)
    print('自检 %d/%d 有结果' % (ok, len(VERIFY)))
    return ok == len(VERIFY)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', action='store_true')
    a = ap.parse_args()
    rows = collect()
    db, nfam = write_db(rows)
    nterm = write_df(rows)
    print('重建 %d 条 / %d 族 -> %s；DF %d 词' % (len(rows), nfam, db, nterm))
    if a.verify:
        sys.exit(0 if verify() else 2)


if __name__ == '__main__':
    main()
