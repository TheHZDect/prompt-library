"""工作区路径单点。整个工程的所有绝对路径只从这里出。

默认根自动推导 = 本文件的父目录，搬家/换盘零修改；跨布局改道设环境变量 `PROMPT_WORK_HOME`。
仓库快照（tools/paths.py）因此也不携带任何本机路径。

架构五分（判据：删掉它需要跑什么命令才能恢复——跑得回来的进 CACHE，跑不回来的进 DATA）：
  DATA   库\\        不可再生真相：批次正文（ENTRIES）、原图、缩略图、collection、台账
  CACHE  缓存\\      可以随便删（几分钟重算）：prompts.db / library.json / skill
  TOOLS  工具\\      代码（扁平，脚本间裸名互相 import，不可再分子目录）
  INBOX  入库区\\    新批次唯一入口（顶层放 docx）；已入库归档在 ARCHIVE
  REPO   prompt-library-repo\\  唯一对外面、唯一 push 面
"""
import os

# 默认根 = 本文件所在目录的父目录（工作区版在 工具\ 下、仓库快照在 tools\ 下，推导结果
# 都是各自的工作区/仓库根）。环境变量 PROMPT_WORK_HOME 可显式改道。
HOME = os.environ.get('PROMPT_WORK_HOME') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA = os.path.join(HOME, '库')                              # 不可再生真相
ENTRIES = os.path.join(DATA, 'entries')                      # 批次正文：<ENTRIES>\main / <ENTRIES>\d0715 …
ORIG = os.path.join(DATA, '原图')                             # 原图按批次存放（不建索引、不进仓库）
COLLECTION = os.path.join(DATA, 'collection')                # 无正文图收藏（index 是 qc 算账依据）
REGISTRY = os.path.join(DATA, 'registry.tsv')                # 跨批正文指纹 -> 首现条目
BATCH_SOURCE = os.path.join(DATA, 'batch_source.tsv')        # 批次 -> 原件文件名台账
GOLD = os.path.join(DATA, 'gold_labels.tsv')                 # 人工金标裁定（唯一不可再生的标注）
DRIFT = os.path.join(DATA, 'qc_known_drift.tsv')             # 已知偏差批次登记
DUP_VARIANTS = os.path.join(DATA, 'dup_variants.tsv')        # 跨批同正文的配图归属登记

CACHE = os.path.join(HOME, '缓存')                            # 一切可重建产物
THUMB = os.path.join(DATA, '缩略图')                           # 分发本体（重压昂贵且是仓库同步源）+ thumbs_index.tsv
SKILL = os.path.join(CACHE, 'skill')                          # 技能包（工作区版，绝对路径）

TOOLS = os.path.join(HOME, '工具')                             # 代码（扁平）

REPO = os.path.join(HOME, 'prompt-library-repo')              # 待推送的私库（含 .git）

INBOX = os.path.join(HOME, '入库区')                           # 待入库 docx 放这里（只扫顶层 .docx）
ARCHIVE = os.path.join(INBOX, '已入库')                        # 已入库原件归档（防重摄；qc full 档凭据）

# 过渡性：历史批次原件所在的区外目录，仅作 qc full 档 / collect_noref 页眉检查的凭据。
# 原件清理后此目录消失，docx_of() 返回 None，qc 自动走 light 档——库不依赖它。
SRC_HISTORY = r'D:\AI\提示词'


def media_dir(prefix):
    """批次 prefix（main / d0715 / k0508）对应的原图目录。"""
    return os.path.join(ORIG, prefix)


def batch_dir(prefix):
    """批次 prefix（main / d0715 / k0508）对应的正文目录。"""
    return os.path.join(ENTRIES, prefix)
