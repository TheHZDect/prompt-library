"""Phase 2c：全库文档频率表（sidecar，独立于 prompts.db，避免被 build_lib2 重建抹掉）。

用途：给检索侧的"残余片段自动成词"做噪声过滤——属性/配饰/具体物件词是开放长尾
（墨镜、草帽、冰淇淋、霰弹枪），不可能枚举进词表，改用 DF 判据自动识别哪些 2-3 字
串值得当检索词：占比太高的是套话（画面/整体/高分辨率），太低的多半是截断碎片。
这与硬规则 8 在评测里验证过的 DF 过滤是同一套判据，只是搬到 query 侧。

  python phase2c_df.py            # 重建 df_terms.db
入库新月份或改清洗规则后需重跑。
"""
import os, re, sqlite3, json
import paths as P

LIB = P.CACHE
DB = os.path.join(LIB, 'df_terms.db')
CJK = re.compile(r'[一-鿿]+')
META = os.path.join(LIB, 'df_meta.json')


def grams_of(text, ns=(2, 3)):
    """只取连续中文串内的 n-gram，跨标点/字母的词不拼接。每篇只计一次（DF 非 TF）。"""
    out = set()
    for run in CJK.findall(text):
        for n in ns:
            for i in range(len(run) - n + 1):
                out.add(run[i:i + n])
    return out


def build():
    con = sqlite3.connect(os.path.join(LIB, 'prompts.db'))
    rows = con.execute('SELECT text FROM cases')
    df = {}
    n = 0
    for (t,) in rows:
        n += 1
        for g in grams_of(t or ''):
            df[g] = df.get(g, 0) + 1
    con.close()
    if os.path.exists(DB): os.remove(DB)
    out = sqlite3.connect(DB)
    out.execute('CREATE TABLE df(term TEXT PRIMARY KEY, n INTEGER) WITHOUT ROWID')
    out.executemany('INSERT INTO df(term,n) VALUES(?,?)', df.items())
    out.commit(); out.close()
    json.dump({'n_cases': n, 'n_terms': len(df)}, open(META, 'w', encoding='utf-8'))
    print(f'DF 表：{n} 条正文，{len(df)} 个 2-3 字串 -> {DB}  '
          f'({os.path.getsize(DB)/1048576:.1f} MB)')


if __name__ == '__main__':
    build()
