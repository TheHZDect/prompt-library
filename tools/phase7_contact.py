"""Phase 7：族样本联系表（contact sheet）。零依赖，输出单个 HTML，图片按绝对路径引用本地文件。

用途：人工按族复核分类与挑参考图——看一屏 24 张比逐条读正文快得多。
  python phase7_contact.py --gold                     # 全部金标条目
  python phase7_contact.py --family portrait_cinema -n 24
  python phase7_contact.py --scene cafe -n 24
  python phase7_contact.py --all-families -n 8        # 每族抽 8 张，一次看全族
"""
import paths as P
import os, sys, html, random, sqlite3, argparse
import famlib as F

LIB = P.CACHE
OUT_DIR = os.path.join(LIB, 'contact')
THUMB_ROOT = P.THUMB
# 私库模式仓库根：脚本自定位（在 <R>/tools/ 下）→ PROMPT_LIB_HOME → 工作区版 lib_home.txt。
# 与 query_lib2.py 同一顺序，保证 clone 后零配置可用。
_HOME = ''
_cand = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(_cand, 'data')) and os.path.isdir(os.path.join(_cand, 'agents')):
    _HOME = _cand
else:
    _HOME = os.environ.get('PROMPT_LIB_HOME') or ''
    if not _HOME:
        _d = os.path.dirname(os.path.abspath(__file__))
        for _p in (os.path.join(_d, 'lib_home.txt'), os.path.join(os.path.dirname(_d), 'lib_home.txt')):
            if os.path.exists(_p):
                _HOME = open(_p, encoding='utf-8').read().strip()
                break
if _HOME:                                   # 私库模式：读仓库 .cache，图在 assets/thumbs 下
    LIB = os.path.join(_HOME, '.cache')
    OUT_DIR = os.path.join(LIB, 'contact')
    THUMB_ROOT = os.path.join(_HOME, 'assets', 'thumbs')
os.makedirs(OUT_DIR, exist_ok=True)
GOLD = os.path.join(LIB, 'gold_labels.tsv')


def gold_ids():
    for p in (GOLD, P.GOLD, os.path.join(_HOME or '', 'data', 'gold_labels.tsv')):
        if p and os.path.exists(p):
            return [l.split('\t')[0] for l in open(p, encoding='utf-8').read().splitlines()[1:] if l.strip()]
    return []


def first_img(thumbs, media):
    """优先缩略图（~25 KB），没有才回退原图（单张可达数 MB）。"""
    for root, blob in ((THUMB_ROOT, thumbs), (None, media)):
        for p in (blob or '').split('|'):
            p = p.strip()
            if not p:
                continue
            full = p if root is None else os.path.join(root, p)
            if os.path.exists(full):
                return 'file:///' + full.replace('\\', '/')
    return ''


PAGE = """<!doctype html><meta charset="utf-8"><title>{title}</title>
<style>
body{{background:#15171a;color:#dfe3e8;font:13px/1.5 system-ui,sans-serif;margin:16px}}
h1{{font-size:16px;margin:0 0 4px}} .meta{{color:#8b95a1;margin-bottom:14px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:12px}}
.card{{background:#1d2025;border:1px solid #2b3038;border-radius:8px;overflow:hidden}}
.card img{{width:100%;height:230px;object-fit:cover;display:block;background:#0d0e10}}
.card .noimg{{height:230px;display:flex;align-items:center;justify-content:center;color:#5c6672}}
.card .b{{padding:8px 9px}} .id{{font-family:ui-monospace,monospace;color:#79c0ff}}
.tag{{display:inline-block;background:#2b3641;border-radius:10px;padding:1px 8px;margin:2px 3px 0 0;color:#b9c6d2;font-size:12px}}
.t{{color:#c9d3dd}} .g{{color:#8ec07c}} .miss{{color:#e06c75}}
</style>
<h1>{title}</h1><div class="meta">{meta}</div><div class="grid">{cards}</div>
"""


def render(con, title, meta, rows):
    cards = []
    for eid, fam, scene, style, text, thumbs, media in rows:
        src = first_img(thumbs, media)
        seg = F.segments(text)
        note = (seg.get('core') or seg.get('style') or text)[:78]
        img = (f'<img loading="lazy" src="{src}">' if src
               else '<div class="noimg">无可用配图</div>')
        tags = ''.join(f'<span class="tag">{html.escape(s)}</span>'
                       for s in (style or '').split('|') if s)
        cards.append(
            f'<div class="card">{img}<div class="b"><div class="id">{eid}</div>'
            f'<div><span class="t">{html.escape(fam)}</span>'
            + (f' <span class="g">{scene}</span>' if scene else '') + '</div>'
            + tags + f'<div>{html.escape(note)}</div></div></div>')
    out = os.path.join(OUT_DIR, title.replace('/', '_').replace(' ', '_') + '.html')
    open(out, 'w', encoding='utf-8').write(
        PAGE.format(title=html.escape(title), meta=html.escape(meta), cards=''.join(cards)))
    n_img = sum(1 for r in rows if first_img(r[5], r[6]))
    print(f'{out}  |  {len(rows)} 格，配图可用 {n_img} 张')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--family'); ap.add_argument('--scene'); ap.add_argument('--line')
    ap.add_argument('--gold', action='store_true')
    ap.add_argument('--all-families', action='store_true')
    ap.add_argument('-n', type=int, default=24)
    ap.add_argument('--seed', type=int, default=20260828)
    a = ap.parse_args()
    con = sqlite3.connect(os.path.join(LIB, 'prompts.db'))
    has_th = any(c[1] == 'thumbs' for c in con.execute('PRAGMA table_info(cases)'))
    COL = 'entry_id, family_id, scene, style, text, %s, media' % (
        'thumbs' if has_th else "'' AS thumbs")

    if a.all_families:
        fams = [r[0] for r in con.execute('SELECT family_id FROM families ORDER BY count DESC')]
        for fam in fams:
            rows = list(con.execute(f'SELECT {COL} FROM cases WHERE family_id=?', (fam,)))
            random.Random(a.seed).shuffle(rows)
            render(con, fam, f'每族 {a.n} 张 / 共 {len(rows)} 条', rows[:a.n])
        return
    if a.gold:
        ids = gold_ids()
        q = f'SELECT {COL} FROM cases WHERE entry_id IN ({",".join("?" * len(ids))})'
        render(con, 'gold', f'金标 {len(ids)} 条', list(con.execute(q, ids)))
        return

    conds, params = [], []
    if a.family: conds.append('family_id LIKE ?'); params.append(a.family + '%')
    if a.scene: conds.append('scene=?'); params.append(a.scene)
    if a.line: conds.append('line=?'); params.append(a.line)
    where = (' WHERE ' + ' AND '.join(conds)) if conds else ''
    rows = list(con.execute(f'SELECT {COL} FROM cases{where}', params))
    random.Random(a.seed).shuffle(rows)
    title = '_'.join(str(x) for x in [a.family or a.scene or 'all', a.line or '']) + f'_n{a.n}'
    render(con, title, f'候选 {len(rows)} 条，随机取 {min(a.n, len(rows))}（seed={a.seed}）', rows[:a.n])


if __name__ == '__main__':
    main()
