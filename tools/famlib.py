"""分类规则 v2（段落感知）。核心改进：关键词只在结构上有意义的片段里匹配，避免
  - 文中顺带提到"人物群体"就把建筑摄影判成人像
  - "像电影海报般的构图"这种比喻把摄影误判成海报
结构信号：画面风格：/核心元素：/具体内容： 是该语料的强模板，先解析再判定。"""
import re

ARTIFACT_NAME = {
    'screenshot': '社媒截图', 'ecom': '电商与品牌物料', 'infographic': '信息图表', 'charcard': '角色设定',
    'ui': 'UI 界面', 'wallpaper': '壁纸头像', 'document': '文档排版', 'comic': '漫画分镜',
    'poster': '海报', 'dbl_expo': '双重曝光', 'photo': '单图摄影',
}
SUBJECT_NAME = {
    'portrait': '人像', 'mecha': '机本科幻', 'pet': '宠物动物', 'food': '美食', 'product': '产品',
    'plant': '植物自然', 'scenearch': '建筑场景', 'guofeng': '古风', 'vehicle': '载具', 'misc': '综合',
}

# 产物：指令式/几乎不会作为比喻出现的强标记
ARTIFACT_RULES = [
    ('screenshot',  ['小红书', '朋友圈', '微博', '聊天截图', '聊天记录', '弹幕', '备忘录界面', '公众号', '知乎', '豆瓣', '短信界面']),
    ('ecom',        ['电商', '详情图', '详情页', '说明页', '主图', '带货', '淘宝', '拼多多', '货架',
                     'logo', '徽章', '品牌全案', '品牌套件', '品牌规范', '品牌标识', '视觉识别', 'vi 设计']),
    ('infographic', ['信息图', '知识卡', '科普', '图鉴', '思维导图', '知识图谱', '流程图', '说明书', '说明图',
                     '示意图', '讲解图', '解读图', '结构图', '时间线', '时间轴', '对比图表', '档案卡', '百科',
                     '网格', '信息板', '演进图']),
    ('charcard',    ['角色设定', '三视图', '四视图', '立绘', '角色卡', '世界观档案', '英雄档案', '设定图', '角色介绍',
                     '角色设计', '转视图']),
    ('ui',          ['仪表盘', '落地页', '登录页', '界面设计', 'app 界面', '网页设计', '交互界面', '后台界面']),
    ('wallpaper',   ['壁纸', '锁屏', '桌面背景', '头像图']),
    ('document',    ['简历', '报纸', '杂志版面', '书籍内页', '幻灯片', '手册页', '论文']),
    ('comic',       ['漫画', '分镜', '连环画', '漫画页']),
    ('poster',      ['海报', '封面', '主视觉', '宣传画', '演唱会', '大促', '广告', '字体设计']),
    ('dbl_expo',    ['双重曝光', '重曝']),
]
SUBJECT_RULES_HEAD = [  # 只用于 核心元素/主体 段的开头部分；一律用 2 字以上复合词，避免单字误伤
    # （头发⊅花、刘海⊅海、头像⊅像、宫崎骏⊅宫 之类单字命中是误判主因）
    ('portrait',  ['女性', '男性', '少女', '少年', '女孩', '男孩', '美女', '模特', '人像', '肖像',
                   '女子', '男子', '老人', '老者', '儿童', '孩子', '宝宝', '情侣', '武士', '侠女',
                   '仙女', '英雄', '角色', '人物', '主播', '选手', '祭司', '巫师', '骑士', '法师',
                   '女人', '男人', '男生', '女生', '女学生', '运动员', '舞者', '新娘', '新郎', '伴娘',
                   '短发', '长发', '卷发', '发丝', '马尾', '女仆',
                   '魔法师', '剑客', '侠客', '忍者', '公主', '王子', '女王', '将军',
                   '精灵', '天使', '女神', '神女', '书生', '工匠', '学生', '白领', '职员', '医生',
                   '护士', '警察', '空乘', '农民', '水手', '海盗',
                   '奶奶', '爷爷', '大叔', '大妈', '妈妈', '爸爸', '姐姐', '妹妹', '哥哥',
                   '弟弟', '老师', '教练', '球手', '主角', '男主', '女主', '男士',
                   '女士', '队长', '主唱', '画师', '剑士', '术士', '女战士', '男战士', '弓手', '甜妹',
                   # 换脸模板族（主库 15+ 条）通篇只说「主体」不点人称，靠这两个模板专词认人；
                   # 不用裸「面部」——实测 55 条含猫脸/驴脸/机器人脸（B1 人工 #07 裁定：一定要有真人）
                   '面部参考', '面部身份']),
    ('mecha',     ['机甲', '机器人', '战舰', '装甲', '高达', '宇航', '赛博', '星战', '机械臂', '机械', '传送门']),
    ('pet',       ['猫咪', '小猫', '宠物', '狗狗', '小狗', '动物', '小鸟', '小鹿', '兔子', '锦鲤',
                   '蝴蝶(?!结)', '恐龙', '狮子', '熊猫', '骆驼', '骏马', '狐狸', '老虎', '鲸鱼',
                   '河马', '橘猫', '柴犬', '鹦鹉', '仓鼠', '水獭']),
    ('food',      ['美食', '食物', '菜肴', '菜品', '甜点', '咖啡(?!馆)', '奶茶', '烘焙', '汉堡', '寿司',
                   '火锅', '蛋糕', '早餐', '午餐', '料理', '甜品', '水果']),
    ('product',   ['产品', '商品', '包装', '香水', '化妆品', '口红', '珠宝', '手表', '球鞋', '瓶身',
                   '护肤品', '饮料', '咖啡杯']),
    ('vehicle',   ['汽车', '跑车', '摩托', '火车', '飞机', '无人机', '自行车', '车辆', '电车', '列车']),
    ('plant',     ['花朵', '花海', '花园', '多肉', '盆栽', '森林', '樱花', '向日葵', '玫瑰',
                   '鲜花', '植物', '荷花', '竹林']),
    ('scenearch', ['建筑', '室内', '教堂', '房间', '城市', '街景', '街道', '风景', '雪山', '大海',
                   '海滩', '天空', '庭院', '景观', '家居', '装修', '天际线', '石桥', '宫殿', '故宫',
                   '寺庙', '博物馆', '咖啡馆', '教室', '校园', '海岸', '山谷', '古镇', '胡同',
                   '摩天大楼', '摩天楼', '廊道', '高楼', '街区', '商店', '店铺', '门店', '门面', '橱窗']),
]

# 检索同义表：只收「同一语义维度且可互换」的表述，与分类判别表解耦。
# SUBJECT_RULES_HEAD 是判别器——核心元素段命中任意一词即判人像，词间是同类并列而非同义。
# 实测 女性 × 运动员/新娘/骑士/武士 同现率仅 0.0–0.3%（正交维度），短发 与 长发 更是反义
# （同现 27/754），所以身份职业类与发型类一律不建组，靠精确匹配召回即可。
SEARCH_SYNONYMS = [
    ('女性', '女子', '女人', '女生', '女孩', '美女', '少女'),
    ('男性', '男子', '男人', '男生', '男孩', '少年'),
    ('儿童', '孩子', '宝宝'),
    ('老人', '老者'),
    ('人像', '肖像', '人物'),
    ('情侣', '恋人'),
    ('猫咪', '小猫'),
    ('狗狗', '小狗'),
    ('宠物', '动物'),
    ('美食', '食物', '料理', '菜肴', '菜品'),
    ('甜点', '甜品'),
    ('机甲', '机器人'),
    ('产品', '商品'),
]

# 单字主体词：**只供检索侧识别口语说法**（用户会直接说"猫""狗"），绝不参与分类与路由。
# 判别词表一律 2 字以上，是因为单字误伤（马卡龙⊅马、龙门⊅龙、刘海⊅海）正是分类层踩过的坑；
# 检索侧不同：命中变宽只影响候选多少，排序能压住，而分类判错会整个方向错。
SUBJECT_MONOGRAMS = ('猫', '狗', '鸟', '鱼', '马', '虎', '狮', '兔', '猴', '鹿', '狼', '狐', '蝶')

STYLE_SEG_WORDS = {  # 风格词只在"画面风格/整体风格"段内找
    '写实': ['写实', '超写实', '照片级', '摄影', '真实'],
    '时尚商业': ['时尚', '街拍', '杂志', '广告', '秀场', '硬照', 'editorial', '商业大片'],
    '清新治愈': ['清新', '治愈', '日系', '日式', '韩系', '韩式', '温暖', '元气', '地中海', '度假感'],
    '古风国风': ['古风', '国风', '水墨', '中式', '国潮', '古典', '东方', '新中式', '敦煌', '工笔', '写意', '青花', '唐卡'],
    '赛博朋克': ['赛博', '霓虹', '科幻', '未来'],
    '电影感': ['电影', '史诗', '大片', '戏剧', '电影级'],
    '动漫插画': ['动漫', '插画', '二次元', '漫画', '卡通', 'cg', '皮克斯', '吉卜力', '赛璐璐', '厚涂', '扁平', '像素', '原画', '绘本'],
    '3D立体': ['3d', '渲染', 'c4d', 'blender', '立体', '微缩', '等距', '轴测', '手办', '盲盒', '潮玩', '积木'],
    '极简': ['极简', '简约', '留白', '单色', '莫兰迪'],
    '复古胶片': ['复古', '胶片', '怀旧', '老照片', '港风', '民国', '老上海', '黑白', 'lofi'],
    '梦幻唯美': ['梦幻', '唯美', '浪漫', '仙气', '童话'],
    '高级质感': ['高级', '奢华', '精致', '高端', '巴洛克', '洛可可', '法式', '意式', '宫廷', '高定', '高级定制'],
    '暗黑氛围': ['暗黑', '阴郁', '哥特', '恐怖', '神秘', '废土', '末日', '克苏鲁'],
    '超现实数字': ['超现实', '数字艺术', '概念设计', '奇幻', '魔幻', '梦境'],
    '拼贴手作': ['拼贴', '剪纸', '纸艺', '黏土', '陶土', '手作', '布艺', '大漆', '漆艺', '油画', '丙烯', '素描', '速写', '线稿', '版画'],
}

PORTRAIT_STYLE_PRIORITY = [
    ('guofeng', '古风', ['古风', '汉服', '仙侠', '武侠', '国风', '水墨', '旗袍', '江湖', '古典', '中式',
                         '新中式', '敦煌', '工笔', '写意', '青花', '唐卡']),
    ('anime', '动漫', ['动漫', '动画', '二次元', '漫画', '卡通', 'cg', '插画', '皮克斯', '吉卜力', '赛璐璐',
                       '厚涂', '扁平', '像素', '绘本', '原画', 'Q版']),
    ('cyber', '赛博科幻', ['赛博', '赛博朋克', '科幻', '机甲', '义肢', '未来', '废土', '末日']),
    ('cinema', '电影感', ['电影', '电影感', '电影风格', '史诗', '大片', '戏剧', '电影级']),
    ('retro', '复古胶片', ['复古', '胶片', '怀旧', '老照片', '港风', '民国', '老上海', '黑白']),
    ('dark', '暗黑', ['暗黑', '阴郁', '哥特', '恐怖', '诡谲']),
    ('dream', '梦幻', ['梦幻', '唯美', '仙气', '浪漫', '童话']),
    ('healing', '治愈日系', ['治愈', '日系', '日式', '韩系', '韩式', '清新', '温暖', '元气', '地中海']),
    ('real', '写实', ['写实', '超写实', '照片级', '纪实', '时尚', '街拍', '杂志', '广告']),
]
# 上义/泛化人称词：单独出现不足以断定主体是人像（"食物角色""故事人物"会把别的主体吸成人像）
PORTRAIT_WEAK = ('角色', '人物', '人像', '肖像', '模特')

# ── 本轮五类系统性错分的修法词表（每块对应 §6.9 一类）────────────────────
# ① 风格「本体词」：说出来就决定画法（动画/插画/水墨/汉服/胶片）。其余如 梦幻/唯美/浪漫/
#    清新/治愈/摄影/写真 是氛围修饰或体裁通称，权重必须低一档——实测 11 条族内错分都是
#    「霓虹」「电影级光影」「浪漫梦幻」这类词反超了正文自己声明的风格。
STYLE_NOUNS = {
    'guofeng': {'古风', '国风', '水墨', '汉服', '旗袍', '敦煌', '唐卡', '工笔', '写意', '仙侠', '武侠'},
    'anime':   {'动漫', '动画', '插画', '漫画', '二次元', '卡通', '吉卜力', '赛璐璐', '像素', '绘本', '原画', '厚涂'},
    'cyber':   {'赛博', '赛博朋克', '机甲', '义肢', '科幻'},
    'cinema':  {'电影感', '电影风格', '电影级', '史诗'},
    'retro':   {'胶片', '港风', '民国', '老上海', '复古'},
    'dark':    {'暗黑', '哥特', '诡谲', '阴郁'},
    'dream':   {'童话', '仙气'},
    'healing': {'日系', '日式', '韩系', '韩式'},   # 不含 清新/治愈：氛围词，实测当本体词会让该族吞掉 1600 条
    'real':    {'写实', '超写实', '照片级', '纪实'},
}
# 人像·古风的族定义本身就是中式造型：造型在场就不跟着摄影声明走。
# 不收 旗袍／古装 —— 前者常属港风民国复古族，后者过泛；实测收下它们会让 guofeng 多吸 300 条。
GUOFENG_LOOK = ('汉服', '凤冠', '霞帔', '马面裙', '油纸伞', '发髻', '深衣')
# ② 人物只是画面元素或尺度参照（剪影/渺小/背影），不作主体证据
ELEMENT_CTX = ('剪影', '渺小', '远景', '背影', '小小', '人群', '之一', '远处', '微缩', '点缀', '群像')
# B1 人工 #18 裁定：风格段声明「人像摄影」体裁时，剪影/背影只是拍摄姿态，不夺主体；
# 尺度词（渺小/远处/之一…）仍夺主体。玩具不是真人（#07 裁定），不享受此豁免。
PORTRAIT_POSTURE = ('剪影', '背影')
PORTRAIT_TOY = ('娃娃', '人偶', '手办', '玩偶', 'bjd', '积木', '毛绒')
# ②′ 物体族同理：背景道具词不决定任何物体族的归属
# （"门口停放的白色自行车"、"架空轨道与行驶车辆"、"背景里的城堡"）
PROP_CTX = ('停放', '行驶', '背景', '门口', '窗外', '路边', '桌上', '散落', '点缀', '远处', '远景')
# ③ 比喻与用途列举：「画面质感如壁纸般精致」「可用于旅行海报、家居装饰、壁纸等」不是产物意图
SIMILE_PRE = ('如', '似', '像', '仿', '同')
SIMILE_POST = ('般', '一样', '似的', '的质感', '效果')
PURPOSE_CTX = ('可用于', '应用场景', '适用于', '用途', '周边', '延展')
# 平台名常只表示审美流派（"小红书仙气纯欲风"），须同现界面形式词才算截图仿制
PLATFORM_WORDS = ('小红书', '朋友圈', '微博', '知乎', '豆瓣', '公众号', 'b站')
SCREEN_FORM_WORDS = ('界面', '截图', '弹幕', '点赞', '评论', '聊天记录', '笔记', '主页', '动态',
                     '粉丝', '关注', '自拍', '头像', '推文', 'app', '私信', '群聊')

SEG_RE = [
    ('style', re.compile(r'画面风格[:：]\s*(.{0,180}?)(?:。|$)')),
    ('core',  re.compile(r'核心元素[:：]\s*(.{0,180}?)(?:。|$)')),
    ('detail', re.compile(r'具体内容[:：]\s*(.{0,400}?)(?:。|$)')),
]

def segments(text):
    segs = {}
    for name, rx in SEG_RE:
        m = rx.search(text)
        if m: segs[name] = m.group(1)
    return segs

INSTR = re.compile(r'(?:生成|创建|制作|设计|创作|做一个|帮我做)[^。]{0,25}')
LAYOUT_MARK = {'comic', 'charcard'}   # 版式类标记允许在核心元素段出现
LAYOUT_WIDE = {'comic', 'charcard', 'infographic'}   # 常写在长模板靠后位置，另给 90 字宽窗口
# 命中点前后出现这些词，说明产物词是在讲材质/地点而非产物本身
# （"材质为报纸 / 杂志拼贴"、"坐在报刊亭或杂志摊前" vs "生成一张报纸头版"）
MATERIAL_CTX = ('拼贴', '材质', '纹理', '碎片', '摊', '亭', '装饰', '贴纸', '做旧',
                '装满', '摆放', '陈列', '背景', '图案')
# 风格段里也能安全判定产物的类别。document 不在内：它的"报纸/杂志/幻灯片"既可能是
# 产物（生成一张报纸头版），也可能是材质与地点（报纸拼贴人像、报刊亭前女性）。
STRONG_ARTIFACT = {'screenshot', 'ecom', 'infographic', 'charcard', 'ui', 'comic', 'poster',
                   'dbl_expo', 'wallpaper'}
# ④ 形式标记（交付物是什么）优先于题材标记（画面里在卖什么/讲什么）：
# 「直播带货截图」里"带货"@2 早于"弹幕"@16，按最早命中会判成电商，但交付形式是截图。
FORM_MARKS = {
    'screenshot':  {'聊天截图', '聊天记录', '弹幕', '备忘录界面', '短信界面'},
    'ecom':        {'详情图', '详情页', '主图', '商品主图', 'logo', '徽章', '品牌套件', '品牌规范',
                    '视觉识别', 'vi 设计'},
    'infographic': {'信息图', '知识卡', '思维导图', '流程图', '说明书', '示意图', '结构图',
                    '时间线', '对比图表', '讲解图', '解读图', '图鉴'},
    'charcard':    {'三视图', '四视图', '立绘', '角色设定', '角色卡', '设定图', '世界观档案', '英雄档案',
                    '角色设计', '转视图'},
    'ui':          {'界面设计', '登录页', '仪表盘', '落地页', '交互界面', '后台界面', '网页设计', 'app 界面'},
    'wallpaper':   {'壁纸', '锁屏', '桌面背景', '头像图'},
    'document':    {'简历', '报纸', '杂志版面', '书籍内页', '幻灯片', '手册页'},
    'comic':       {'分镜', '漫画页', '连环画', '漫画'},
    'dbl_expo':    {'双重曝光', '重曝'},
    'poster':      {'海报', '封面', '主视觉', '宣传画', '字体设计'},
}

def classify_artifact(text):
    segs = segments(text)
    low_all = text.lower()

    def off_of(s):      # 片段在全文里的起始偏移，语境检查必须用绝对坐标
        return max(0, low_all.find(s.lower()[:40])) if s else 0

    fields = [(0, text[:60], 'any')]               # 标题式开头本身就是产物声明，不必有动词
    fields += [(m.start(), m.group(0), 'any') for m in INSTR.finditer(text)]
    if segs.get('style'): fields.append((off_of(segs['style']), segs['style'][:80], 'strong'))
    if segs.get('core'): fields.append((off_of(segs['core']), segs['core'][:80], 'layout'))
    fields.append((0, text[:90], 'wide'))
    best = None
    for off, scope, kind in fields:      # 片段顺序即优先级；同一片段内按标记出现位置择优
        if not scope or best is not None: continue
        hits = []
        for aid, kws in ARTIFACT_RULES:
            if kind == 'layout' and aid not in LAYOUT_MARK: continue
            if kind == 'wide' and aid not in LAYOUT_WIDE: continue
            if kind == 'strong' and aid not in STRONG_ARTIFACT: continue
            for kw in kws:
                kl = kw.lower()
                pat = kl if '(?' in kw else re.escape(kl)
                m = re.search(pat, scope.lower())
                if not m: continue
                A = off + m.start()                        # 全文绝对位置
                pre, post = low_all[max(0, A - 8):A], low_all[A + len(kl):A + len(kl) + 5]
                ctx = low_all[max(0, A - 10):A + len(kl) + 10]
                if any(x in ctx for x in MATERIAL_CTX): continue
                if pre.endswith(SIMILE_PRE) or post.startswith(SIMILE_POST): continue   # 比喻
                if any(x in low_all[max(0, A - 30):A] for x in PURPOSE_CTX): continue   # 用途列举
                if aid == 'screenshot' and kl in PLATFORM_WORDS \
                        and not any(f in low_all for f in SCREEN_FORM_WORDS): continue  # 平台审美词
                # 槽位枚举：「【角色设定】」是模板占位符不是产物声明（同 SIMILE/PURPOSE 一类，
                # 与正文真声明「设计…Logo」相对；B1R2 #03）
                if low_all[max(0, A - 1):A] == '【' or low_all[A + len(kl):A + len(kl) + 1] == '】': continue
                # 「构图……角色立绘」是取景描述不是设定板交付（2026-09-01 盲标 #37 裁定）
                if aid == 'charcard' and kl == '立绘' and '构图' in low_all[max(0, A - 12):A]: continue
                lvl = 0 if kl in FORM_MARKS.get(aid, ()) else 1
                hits.append((lvl, A, aid))
                break
        if hits:
            best = min(hits)[2]
    return best or 'photo'

def _hit(text, kw):
    return bool(re.search(kw, text)) if '(?' in kw else (kw in text)

def classify_subject(text):
    """core 段主体归谁就归谁：人物在场仍判人像（族体系既定设计），但物体族之间按主体词
    在段内的**位置**择优，不再由族表书写顺序决定；带道具语境的命中（门口停放的自行车、
    背景里的城堡）一律不决定归属——背景道具词不决定任何物体族的归属。"""
    segs = segments(text)
    # 有骨架：主体写在"核心元素"段首，只看前 60 字；无骨架：退化到正文前 80 字
    head = segs['core'][:60] if 'core' in segs else text[:80]
    low = head.lower()
    # 体裁豁免（B1 人工 #18）：风格段明说「人像摄影」且非玩具 → 剪影/背影是姿态不是元素
    genre = ('人像摄影' in segs.get('style', '')
             and not any(w in text.lower() for w in PORTRAIT_TOY))
    hits, weak = [], False
    for sid, kws in SUBJECT_RULES_HEAD:
        if sid == 'portrait':
            banned = tuple(x for x in ELEMENT_CTX if not genre or x not in PORTRAIT_POSTURE)
        else:
            banned = PROP_CTX
        for k in kws:
            stem = k.split('(')[0].lower()
            i = low.find(stem)
            if '(?' in k:
                if not _hit(low, k.lower()): continue
                i = i if i >= 0 else 0
            elif i < 0:
                continue
            # 人像侧：剪影/背影是后缀，需查后文；物体侧：道具引导词在名词前，只查前文
            ctx = (low[max(0, i - 12):i + len(stem) + 12] if sid == 'portrait'
                   else low[max(0, i - 8):i])
            if any(x in ctx for x in banned):
                continue                          # 元素/道具语境，不作主体证据
            if sid == 'portrait' and k in PORTRAIT_WEAK:
                weak = True; continue             # 上义词单独不作证据
            hits.append((i, sid))
    if not hits:
        return 'portrait' if weak else 'misc'
    if any(s == 'portrait' for _p, s in hits):
        return 'portrait'
    return min(hits)[1]

def style_tags(text):
    segs = segments(text)
    scope = (segs.get('style') or text[:200])
    low = scope.lower()
    return [s for s, kws in STYLE_SEG_WORDS.items() if any(k.lower() in low for k in kws)]

def portrait_style(text):
    """风格族判定：以风格段首位声明的写法为准，本体词压过修饰词。
    正文明说「日系清新」就是 healing，后面补的「浪漫梦幻」不许反超（§6.9 类①，11 条）。
    平票按"该族最强词出现得更早"裁决，不再靠词表书写顺序偏袒排前的族。"""
    segs = segments(text)
    style, core = segs.get('style', ''), segs.get('core', '')
    # 「X质感」尾挂补笔是修饰不是流派声明（2026-09-01 盲标 #43/#35 裁定：
    # "自然写实…具有胶片质感" / "写实街拍…雨天胶片质感" 都判 real，胶片只是补笔）。
    # 只剥首个标点之后的尾部；head（首位声明）原样保留——"胶片质感人像"开头仍算 retro。
    head = re.split(r'[，、,；;。]', style)[0] if style else ''
    tail = re.sub(r'(?:具有|带有|充满|兼具)?[^，。；]{0,4}(胶片|电影|梦幻|暗黑|赛博|油画|水彩|复古|港风|水墨)[一-鿿]{0,2}质感', '', style[len(head):])
    style = head + tail
    if any(w in core + style + text[:140] for w in GUOFENG_LOOK):      # 造型即古风，不看摄影声明
        return 'guofeng', '古风'
    head = re.split(r'[，、,；;。]', style)[0] if style else ''
    scopes = []
    if head: scopes.append((head, 30, 1))
    if style: scopes.append((style, 6, 1))
    if core: scopes.append((core, 6, 1))
    if not scopes: scopes = [(text[:200], 6, 1)]
    probe = (style + '\n' + core + '\n' + text).lower()

    def scan(only_noun, skip_real=False):
        best = None
        for fid, fname, kws in PORTRAIT_STYLE_PRIORITY:
            if skip_real and fid == 'real':
                continue                          # 写实是技法不是流派，让位给真正的流派词
            nouns = STYLE_NOUNS.get(fid, set())
            sc, first = 0, len(probe) + 1
            for k in kws:
                isnoun = k in nouns
                if only_noun and not isnoun: continue
                kl = k.lower()
                for scope, wn, wa in scopes:
                    c = scope.lower().count(kl)
                    if c: sc += c * (wn if isnoun else wa)
                p = probe.find(kl)
                if p >= 0: first = min(first, p)
            if sc and (best is None or sc > best[0] or (sc == best[0] and first < best[1])):
                best = (sc, first, fid, fname)
        return best
    # 三轮：非写实族本体词 → 含写实族本体词 → 修饰词兜底。
    # 没有「画面风格：」声明时不走修饰词轮：正文零散出现一个"浪漫/唯美"不足以定流派。
    b = scan(True, skip_real=True) or scan(True) or (scan(False) if style else None)
    if b:
        return b[2], b[3]
    return 'real', '写实'

# 场景词典：只用 2 字以上复合词（单字 海/山/湖 会误伤 刘海/头像/江湖）
SCENES = {
    'indoor':   ['室内', '房间', '窗边', '卧室', '客厅', '走廊', '教室', '工作室', '窗台', '阳台', '屋内', '窗前'],
    'street':   ['街道', '街景', '马路', '人行道', '巷子', '路口', '天台', '街头', '路面', '斑马线', '街拍'],
    'city':     ['城市', '天际线', '高楼', '摩天楼', '建筑群', '商业区', '都市', '楼宇'],
    'historic': ['古镇', '故宫', '宫殿', '寺庙', '庭院', '园林', '城墙', '废墟', '遗迹', '庙宇', '古建筑',
                 '石窟', '洞窟', '回廊', '廊道', '牌楼', '佛塔', '古塔', '灯塔'],
    'nature':   ['森林', '草原', '山野', '山谷', '溪流', '湖水', '田野', '花田', '花海', '草地', '湖边'],
    'seaside':  ['海边', '沙滩', '海滩', '海浪', '泳池', '海岛', '海岸', '礁石'],
    'cafe':     ['咖啡馆', '咖啡店', '餐厅', '书店', '图书馆', '酒吧', '面包店', '便利店', '超市'],
    'night':    ['夜空', '星空', '月光', '深夜', '月色', '夜色', '星夜'],
    'snow':     ['雪景', '雪地', '飘雪', '雪山', '冬日', '霜雪'],
}
SCENE_NAME = {'indoor': '室内', 'street': '街头', 'city': '都市', 'historic': '古建', 'nature': '自然',
              'seaside': '海边', 'cafe': '店铺', 'night': '星夜', 'snow': '雪景'}
# 光线是属性不是场景（实测"逆光/金色光"在各族都 21-49%，当子族会切错），单列为 facet。
# 场景同理且更严重：全文匹配下 47% 的条目命中 >=2 个场景、29% 只在背景出现，
# 而 _subsplit 按书写顺序取第一个命中，等于抛硬币；同父族各子族的风格分布几乎相同
# （guofeng 父 32/25/8 vs 三子族 32/28/9、33/28/8、29/26/11）→ 场景一律降级为 facet，不再拆族。
LIGHTING = {
    '逆光轮廓': ['逆光', '轮廓光', '剪影'],
    '金色暖光': ['金色光', '暖阳', '夕阳', '落日', '黄昏', '余晖', '暖光'],
    '柔光朦胧': ['柔和', '朦胧', '柔焦', '漫射'],
    '硬光高对比': ['高对比', '强烈光影', '硬光', '明暗对比'],
    '冷色调': ['冷调', '冷色', '蓝调', '清冷'],
    '霓虹光效': ['霓虹', '彩色光'],
}


def lighting_tags(text):
    low = text.lower()
    return [k for k, kws in LIGHTING.items() if any(w.lower() in low for w in kws)]


def scene_of(text):
    """主场景 facet：核心元素段权重 2、画面风格段权重 1，背景与具体内容段不计。
    无定域证据时返回空串——宁可没有场景标签，也不拿背景词硬贴。"""
    segs = segments(text)
    core, style = segs.get('core', ''), segs.get('style', '')
    best = None
    for sid, kws in SCENES.items():
        sc = 2 * sum(core.count(k) for k in kws) + sum(style.count(k) for k in kws)
        if sc and (best is None or sc > best[0]):
            best = (sc, sid)
    return best[1] if best else ''


def family_of(text, artifact=None, subject=None):
    if artifact is None:
        artifact = classify_artifact(text)
        subject = classify_subject(text) if artifact == 'photo' else ''
    if artifact != 'photo':
        return artifact, ARTIFACT_NAME[artifact]
    if subject == 'portrait':
        fid, fname = portrait_style(text)
        return f'portrait_{fid}', f'人像·{fname}'
    return f'photo_{subject}', f'摄影·{SUBJECT_NAME.get(subject, "综合")}'


# ── C1 结构约束列（§6：只有 aspect_ratio 值得单独成列且必须三态；参考图与槽位合成一个 flag）──
# 三态而非二态的理由：「画幅比例：{9:16 / 16:9}」是模板槽位里的**示例值**，
# 既不是"用户声明了画幅"（explicit），也不是"没提"（none）——硬塞进任一侧都会污染过滤。
_RATIO_RX = re.compile(r'\d{1,2}(?:\.\d)?[:：]\d{1,2}(?:\.\d)?')
# 【…】在本语料里一律是填空槽位（实测高频内容为 主色调/品牌名/画幅比例…），长度不设上限：
# 「画幅比例：【画幅比例，例如2:3竖版 / 3:4竖版 / …】」整段是槽位，设 20 字上限会漏判成 explicit。
_BRACKET_RX = re.compile(r'【[^】]+】|\{argument\b')

def aspect_state(text):
    """explicit=正文有非槽位的 N:M 比例声明；slot=比例只出现在【】/{argument} 模板槽位里；
    none=通篇无比例。JSON 形态正文的 "16:9" 是字段值（用户声明），其花括号不匹配 _BRACKET_RX，
    故天然判 explicit。时间串误报（"凌晨2:47"）实测仅 0.06%，不做专门排除。"""
    ms = list(_RATIO_RX.finditer(text))
    if not ms:
        return 'none'
    spans = [(m.start(), m.end()) for m in _BRACKET_RX.finditer(text)]
    # 只要有一个比例落在槽位外，就是真声明（explicit）；全部落在槽位内才是 slot
    if any(not any(a <= m.start() < b for a, b in spans) for m in ms):
        return 'explicit'
    return 'slot'

REF_RX = re.compile(r'参考图|参考照片|上传的图|上传图片|上传图|基于上传|垫图|按照上传|参考上传'
                    r'|以这张图|用这张图|参考这|按照这|依照这|根据这|这张照片|图1|图2|参考该|根据该图')

def needs_input(text):
    """1=这条提示词是半截话：需要外部素材（参考图）或用户填空（【】槽位/{argument}）才能出图。
    JSON 形态正文的 {} 是数据不是槽位，故花括号只认 {argument 这一种确定性模板标记。"""
    return 1 if (REF_RX.search(text) or _BRACKET_RX.search(text)) else 0
