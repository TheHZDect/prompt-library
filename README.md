# prompt-library

11,966 条真实文生图提示词检索库。一句口语描述 → 取回可直接改用的原文骨架与预览图。零服务、零联网，本地跑。

## 30 秒上手

```bash
git clone https://github.com/TheHZDect/prompt-library.git && cd prompt-library
python tools/rebuild_db.py                 # 从 data/ 重建检索库（产出 .cache/，不进 git）
node agents/skills/prompt-library/bin/install.mjs trae   # 装成 agent 技能（目标可换 codex|claude|agents|trae）
```

装完后对你的 agent 说人话即可：

> 帮我找"国风少女 室内窗边"的提示词参考

agent 会按技能说明（SKILL.md）自动路由到家族、取回原文和预览图。不想用 agent 的话，手动命令见下。

## 手动检索

```bash
# 路由：这句需求该去哪个家族找（只吃短语，2-4 个关键词）
python tools/query_lib2.py route "国风 少女" -k 3

# 检索：取原文（能吃整句，自动切术语）
python tools/query_lib2.py search "女性 国风" -k 5

# 常用过滤
#   --family portrait_guofeng   限定家族
#   --scene indoor|street|seaside|night|snow|...  场景标签
#   --needs 0                   只要拿来即用的（不依赖参考图/填空）
#   --aspect explicit           只要正文声明了画幅比例的
#   --line main|daily|kook      限定数据线
```

### 输出怎么读

```
[  33.50] d0619_0041  daily/26-06-19  段172-182  族=portrait_guofeng  len=1042
    缩略图=D:\...\assets\thumbs\d0619\d0619_0041_1.jpg   ← 预览图（绝对路径，直接打开）
    '色彩基调：……核心元素：……'                          ← 正文前 200 字
```

要全文：

```bash
python -c "import sqlite3;print(sqlite3.connect('.cache/prompts.db').execute('SELECT text FROM cases WHERE entry_id=?',('d0619_0041',)).fetchone()[0])"
```

出现 `（未命中，已放宽：X）`= 词 X 无满足项已放弃，不是命中，换个说法再查。

## 复用一条提示词

> **先看一眼再用**：相当一部分条目是模板——含【填空】/占位符字段，或需要上传参考图。直接拿去生图会把占位符原样画出来；要么先填掉槽位、备好参考图，要么用 `--needs 0` 只取拿来即用的。

1. 以取回的原文为骨架，只替换主体/服装/场景/光线，**保留它的结构分层**（画面风格 / 核心元素 / 具体内容，或 JSON 字段）——结构是出图质量的大头。
2. 查该家族的写法要点与翻车点：`agents/skills/prompt-library/references/families/<族id>.md`；族总表 `references/index.md`。
3. 一次挑 2-3 条相近的对比用，别只信第一条。

例：原文是「冷感东亚女生 + 水墨圆月背景 + 黑白撞色套装」，你要赛博雨夜——保留其"色彩基调→画面风格→核心元素→构图"的分层写法，逐段替换内容词。

## 库里有什么

| 项 | 值 |
|---|---|
| 条目 | 11,966 条提示词原文 |
| 家族 | 27，按 产物 / 主体 / 人像风格 分；场景、光线是筛选标签 |
| 预览图 | 12,738 张缩略图（512px） |
| 依赖 | Python 3（标准库） |

## 常见问题

- **查不到想要的概念？** 库里没写过的东西召不回（如"App 登录界面"零条目）。先用 `route` 看家族分布，再放宽词试 `search`；确认没有就是库容缺口。
- **想改分类或扩充数据？** 维护规程与决策记录见 `docs/PROJECT_STATE.md`。
