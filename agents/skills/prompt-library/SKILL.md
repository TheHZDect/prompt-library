---
name: prompt-library
description: 检索 11966 条真实文生图提示词库，按意图路由到家族并取回可直接改用的原文与预览图。当需要生成、改写图像提示词，或要按风格/场景/产物找示例时使用。
---

# 提示词库检索（prompt-library）

零服务、零联网，查询只依赖 Python 标准库 sqlite3。

## 仓库获取

引擎与数据不在技能目录内，在配套仓库：

```
git clone https://github.com/TheHZDect/prompt-library.git
cd prompt-library
python tools/rebuild_db.py    # 从 data/ 重建 .cache/prompts.db（库文件不入库、不进 git）
```

## 仓库路径（`<R>`）如何确定

技能内所有命令的 `<R>` = 仓库根绝对路径。`tools/query_lib2.py` 内置三级解析，依次尝试：

1. **自定位**：脚本在 `<R>/tools/` 下，其上级目录同时含 `data/` 与 `agents/` → 认定仓库根，零配置可用
2. **环境变量** `PROMPT_LIB_HOME=<仓库根>`（显式改道）
3. **技能目录下 `bin/lib_home.txt`**：一行仓库根，安装时由 `install.mjs` 写入

技能直接在仓库内使用走第 1 条；被装到别处则靠第 2、3 条。执行时把 `<R>` 展开成绝对路径，一切命令与 cwd 无关。

- 检索入口：`<R>/tools/query_lib2.py`
- 数据库：  `<R>/.cache/prompts.db`（11966 条，含 FTS5 全文索引）
- 家族定义：`references/library.json`（27 个家族）
- 家族明细：`references/families/<家族id>.md`；总表 `references/index.md`；词表 `references/tags.md`；场景标签 `references/scenes.md`

## 工作流

1. 先路由拿家族，但 **route 只吃短语**（2-4 个风格/产物/主体关键词），别丢整句：
   ```
   python <R>/tools/query_lib2.py route "国风 少女" -k 3
   ```
   返回按分数排序的家族；读第一名家族的 `references/families/<id>.md`，拿到它的写法要点与翻车点。
   route 打印「词表未命中」= 说法在标签词表外（单字主体如猫/狗、长尾物件如墨镜/牛肉面），此时 route 的排序是兜底没有参考性——**跳过 route，直接进第 2 步用 search**。
2. 再取原文（search 能吃整句，它会自己切词）：
   ```
   python <R>/tools/query_lib2.py search "<关键词1 关键词2>" -k 5 [--line daily] [--family portrait_guofeng] [--style 古风国风] [--scene indoor] [--aspect explicit|slot|none] [--needs 0|1]
   ```
   输出含 entry_id、家族、来源与段落区间、配图文件名（`图=` 行）与缩略图绝对路径（`缩略图=` 行）、正文前 200 字。
   `--aspect explicit`=正文声明了画幅比例（生成时可直接沿用其比例）；`--needs 0`=拿来即用、不依赖参考图/填空（用户没上传图、没给品牌名时优先用这个过滤）。
3. 要全文时用 `--family` 精确定位，或按 entry_id 取：
   ```
   python -c "import sqlite3;print(sqlite3.connect(r'<R>/.cache/prompts.db').execute('SELECT text FROM cases WHERE entry_id=?',('<id>',)).fetchone()[0])"
   ```
4. 生成新提示词：以取回的原文为骨架，替换主体/服装/场景/光线，**保留它的结构分层**（画面风格 / 核心元素 / 具体内容 或 JSON 字段），并套用家族页里的 guidance 与 pitfalls。**原文含【槽位】/占位符或参考图依赖时必须先处理，不能看都不看直接生图**（只想要拿来即用的就加 `--needs 0`）。
5. 一次给 2-3 个家族候选并说明差异，让用户选，不要自作主张定一个。

## 检索策略

- 顺序：产物类别 → 风格族 → 具体条目。场景与光线是标签不是家族，要按场景收窄用 `--scene <id>`（取值与各场景写法要点见 `references/scenes.md`）。用户说"海报/截图/信息图/详情图/三视图"时，产物类别优先于风格。
- 可以直接把用户原话整句丢给 `search`：它会先按识别词表切出术语再检索，2 字词和单字主体词（猫、狗）也能查，不必自己先分词或凑 3 字标准术语。
- 输出里出现`（未命中，已放宽：X）`时，说明 X 没有满足项、已被放弃 —— 要转述给用户，不能当作命中。
- `route` 打印「词表未命中」时给的是兜底排序而非结论：按工作流第 1 步跳过 route，用 `search` 整句检索（词表见 `references/tags.md`）。
- 配图路径直接可用，`imgs` 与 `media` 是提取出的原图，未做缩略图。
- **给用户看缩略图必须给完整路径**：原样输出 `缩略图=` 行的绝对路径；用相对路径时必须从会话工作目录写起、带仓库目录层（`prompt-library-repo/assets/thumbs/<批次>/<id>_1.jpg`）。只给文件名会报「工作区文件过多，无法确认唯一匹配」，省掉仓库目录层则是死链——两种都让用户点不开图。

## 边界

- 没有语义向量。词表之外的长尾说法（配饰、具体物件、食物名）由"残余片段自动成词"按文档频率兜住，不必人工扩词；但**库里根本没写过的概念依然召不回**（例如没有任何 App 登录界面类条目），此时检索会提示已放宽了哪个词，不要把它当成命中。
- 图片本身不可检索，只能靠配对正文命中。
- 三条内容线互不重叠（重合仅个位数），合并使用只是并集。

## 维护

仓库内只需重建索引：`python tools/rebuild_db.py --verify`。

交接与踩坑记录见 `docs/PROJECT_STATE.md`。
