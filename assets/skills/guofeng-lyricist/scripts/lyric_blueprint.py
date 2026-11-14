#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lyric_blueprint.py —— 中国风作词蓝图（主题/情绪 → 韵辙 + 句式 + 意象 + 典故 + 结构卡 + .lyr 骨架）

纯标准库实现。输入 JSON 全可选（最小写 {} 就能出完整蓝图）。

产出：
  1) <name>.blueprint.json  机器可读蓝图（给下游脚本/Agent 用）
  2) <name>.blueprint.md    人读蓝图（韵辙推荐、句式候选 3 套、意象包 3 组、
                            典故候选 3–5 条、结构卡、金句位、参考案例、避坑 5 条、
                            可直接复制的 .lyr 骨架）

用法：
  python lyric_blueprint.py
        无参数 = 内置 demo（相思 + 抒情 + 女声），产物写到系统临时目录
        guofeng-lyric-out/作词蓝图-demo.{blueprint.json,blueprint.md}
  python lyric_blueprint.py --demo
        同上（显式 demo）
  python lyric_blueprint.py --input 需求.json
        输出 同目录/需求.blueprint.json + .blueprint.md
  python lyric_blueprint.py --input 需求.json --out 蓝图/江南雨
        输出 蓝图/江南雨.blueprint.json + 蓝图/江南雨.blueprint.md
  python lyric_blueprint.py --help

输入 JSON 字段（全可选；未知字段会提示并忽略）：
  theme        题材：相思|离别|怀古|家国|江湖|隐逸|悼亡|少年|市井|禅意
  style        风格：抒情|古风|戏腔|国潮|叙事（也接受 shuqing/gufeng/xiqiang/guochao/narrative）
  mood         情绪自由文本，如「雨夜、旧巷、哀而不伤」
  voice        男|女|合唱
  perspective  第一|第二|第三（人称视角）
  duration_lines  目标总句数（默认 22；16 更短，28 更长）
  rhyme        强制指定辙口：言前|人辰|中东…（也可写 a/an/ing 等韵母）
  style_hint   额外风格提示，自由文本

退出码：0 正常；2 参数/输入问题（报告会说明下一步）。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # 不依赖 cwd

VERSION = "1.0.0"
SKILL = "guofeng-lyricist"


def _setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ================================================================ 十三辙

# 辙名 → 代表韵母 / 色彩 / 适合题材 / 推荐度（题材侧重由 THEMES 覆盖）
ZHES: dict[str, dict] = {
    "发花": {"mu": "a / ia / ua", "color": "开阔、亮、略显外放，深悲不宜", "fit": ["市井", "少年"]},
    "梭波": {"mu": "o / e / uo", "color": "圆润沉稳，叙述不飘", "fit": ["市井", "隐逸", "怀古"]},
    "乜斜": {"mu": "ie / üe", "color": "窄而凄清，短促，适合决绝与伤痛", "fit": ["离别", "悼亡"]},
    "一七": {"mu": "i / ü / -i", "color": "细、尖、内收，最贴内心独白", "fit": ["相思", "悼亡"]},
    "姑苏": {"mu": "u", "color": "暗、闷、有厚度，适合感慨与苍凉", "fit": ["怀古", "禅意"]},
    "怀来": {"mu": "ai / uai", "color": "开而有回响，适合叹息与凭吊", "fit": ["家国", "怀古"]},
    "灰堆": {"mu": "ei / ui", "color": "柔、轻愁、尾音易收", "fit": ["相思", "离别"]},
    "遥条": {"mu": "ao / iao", "color": "飘、远、带豪气", "fit": ["江湖", "少年"]},
    "油求": {"mu": "ou / iu", "color": "幽、含蓄、尾音柔", "fit": ["隐逸", "禅意"]},
    "言前": {"mu": "an / ian / uan / üan", "color": "宽、亮、最通用，拖长音最舒服", "fit": ["相思", "家国", "离别"]},
    "人辰": {"mu": "en / in / un / ün", "color": "深、细、偏内省，适合收尾", "fit": ["相思", "悼亡", "禅意"]},
    "江阳": {"mu": "ang / iang / uang", "color": "宏、亮、余响长，适合豪迈与咏叹", "fit": ["家国", "江湖", "怀古"]},
    "中东": {"mu": "eng / ing / ong / iong", "color": "长、远、有钟磬般的余韵", "fit": ["离别", "怀古", "少年"]},
}

ZHE_ORDER = ["言前", "人辰", "江阳", "中东", "遥条", "油求", "一七", "灰堆", "发花", "梭波", "乜斜", "怀来", "姑苏"]

# 韵母 → 辙名（用户用韵母指定辙口时用）
MU_TO_ZHE = {
    "a": "发花", "ia": "发花", "ua": "发花",
    "o": "梭波", "e": "梭波", "uo": "梭波", "er": "梭波",
    "ie": "乜斜", "ve": "乜斜", "üe": "乜斜",
    "i": "一七", "v": "一七", "ü": "一七",
    "u": "姑苏",
    "ai": "怀来", "uai": "怀来",
    "ei": "灰堆", "ui": "灰堆", "uei": "灰堆",
    "ao": "遥条", "iao": "遥条",
    "ou": "油求", "iu": "油求", "iou": "油求",
    "an": "言前", "ian": "言前", "uan": "言前", "van": "言前", "üan": "言前",
    "en": "人辰", "in": "人辰", "un": "人辰", "vn": "人辰", "ün": "人辰",
    "ang": "江阳", "iang": "江阳", "uang": "江阳",
    "eng": "中东", "ing": "中东", "ong": "中东", "iong": "中东",
}

# 每辙 6 个常用韵脚词（2 字，收尾字必在该辙），蓝图骨架直接用
RHYME_WORDS: dict[str, list[str]] = {
    "发花": ["天涯", "落花", "年华", "晚霞", "人家", "白发"],
    "梭波": ["江河", "旧歌", "楼阁", "夜色", "烟波", "烟火"],
    "乜斜": ["明月", "残雪", "长别", "落叶", "今夜", "佳节"],
    "一七": ["归期", "故里", "旧事", "心事", "烟雨", "青丝"],
    "姑苏": ["归路", "朝暮", "孤独", "旧书", "故土", "寒露"],
    "怀来": ["归来", "楼台", "沧海", "尘埃", "边塞", "独白"],
    "灰堆": ["流水", "年岁", "余晖", "沉醉", "眼泪", "相随"],
    "遥条": ["年少", "长桥", "春晓", "芳草", "归鸟", "良宵"],
    "油求": ["深秋", "回首", "长留", "离愁", "白首", "渡口"],
    "言前": ["人间", "长天", "旧年", "江南", "关山", "无眠"],
    "人辰": ["故人", "黄昏", "乡音", "前尘", "春深", "梦痕"],
    "江阳": ["故乡", "月光", "沧桑", "他乡", "斜阳", "风霜"],
    "中东": ["长风", "旧梦", "钟声", "故城", "残红", "相逢"],
}


# ================================================================ 声调表（骨架用）
# 现代普通话四声：1 阴平 / 2 阳平 / 3 上声 / 4 去声。只收本脚本骨架会用到的字。
TONE: dict[str, int] = {}

# 精确单字表：多音字按其在本脚本骨架里的读音登记（阴平/阳平/上声/去声）
_PRECISE: dict[str, int] = {
    # 阴平
    "灯": 1, "花": 1, "窗": 1, "双": 1, "芭": 1, "蕉": 1, "砧": 1, "声": 1, "檐": 2,
    "笺": 1, "钗": 1, "炉": 2, "烟": 1, "衾": 1, "孤": 1, "帆": 1, "关": 1, "歌": 1,
    "嘶": 1, "钟": 1, "枝": 1, "杯": 1, "青": 1, "衫": 1, "舟": 1, "荒": 1, "宫": 1,
    "风": 1, "鸦": 1, "山": 1, "烽": 1, "边": 1, "松": 1, "溪": 1, "弓": 1, "刀": 1,
    "旌": 1, "兵": 1, "家": 1, "书": 1, "芦": 1, "蓑": 1, "箫": 1, "鱼": 2, "竿": 1,
    "阶": 1, "衣": 1, "空": 1, "犁": 2, "香": 1, "灰": 1, "经": 1, "春": 1, "街": 1,
    "元": 2, "宵": 1, "鞭": 1, "筝": 1, "靴": 1, "棚": 2, "挑": 1, "锅": 1, "蒸": 1,
    "音": 1, "钵": 1, "珠": 1, "蒲": 2, "团": 2, "秋": 1, "天": 1, "佳": 1, "今": 1,
    "心": 1, "沧": 1, "埃": 1, "晖": 1, "相": 1, "芳": 1, "乡": 1, "他": 1, "霜": 1,
    "光": 1, "桑": 1, "昏": 1, "深": 1, "间": 1, "筝": 1, "笳": 1, "刁": 1, "鸢": 1,
    "锅": 1, "烟": 1,
    # 阳平
    "棂": 2, "铜": 2, "罗": 2, "回": 2, "廊": 2, "笛": 2, "鸣": 2, "虫": 2, "吟": 2,
    "寒": 2, "长": 2, "亭": 2, "旗": 2, "阳": 2, "骊": 2, "琵": 2, "琶": 2, "行": 2,
    "囊": 2, "台": 2, "墙": 2, "苔": 2, "痕": 2, "啼": 2, "樵": 2, "渔": 2, "石": 2,
    "桥": 2, "蹄": 2, "琴": 2, "壶": 2, "竹": 2, "篱": 2, "茅": 2, "塘": 2, "荷": 2,
    "涛": 2, "门": 2, "池": 2, "云": 2, "莲": 2, "尘": 2, "无": 2, "眠": 2, "人": 2,
    "南": 2, "黄": 2, "前": 2, "斜": 2, "城": 2, "红": 2, "逢": 2, "流": 2, "余": 2,
    "沉": 2, "随": 2, "留": 2, "愁": 2, "头": 2, "年": 2, "华": 2, "霞": 2, "涯": 2,
    "白": 2, "明": 2, "别": 2, "节": 2, "独": 2, "河": 2, "楼": 2, "阁": 2, "来": 2,
    "隔": 2, "拾": 2, "成": 2, "敌": 2, "笼": 2, "铃": 2, "坛": 2, "葫": 2, "茶": 2,
    "枰": 2, "函": 2, "坟": 2, "符": 2, "旗": 2, "沿": 2, "杷": 2, "投": 2, "传": 2,
    "怀": 2, "柴": 2, "柴": 2, "弹": 2, "霓": 2, "疑": 2, "鱼": 2, "佛": 2, "尘": 2,
    # 上声
    "雨": 3, "短": 3, "柳": 3, "酒": 3, "橹": 3, "马": 3, "鼓": 3, "角": 3, "甲": 3,
    "斗": 3, "井": 3, "瓦": 3, "野": 3, "斧": 3, "冷": 3, "纸": 3, "草": 3, "挽": 3,
    "枕": 3, "板": 3, "里": 3, "土": 3, "海": 3, "眼": 3, "首": 3, "鸟": 3, "晓": 3,
    "水": 3, "影": 3, "塔": 3, "子": 3, "伞": 3, "杆": 3, "小": 3, "老": 3, "好": 3,
    "古": 3, "有": 3, "我": 3, "你": 3, "已": 3, "起": 3, "满": 3, "掩": 3, "与": 3,
    "暖": 3, "锁": 3, "粉": 3, "染": 3, "惹": 3, "煮": 3, "盏": 3, "数": 3, "铲": 3,
    "杆": 3, "褶": 3, "摆": 3, "杳": 3, "染": 3,
    # 去声
    "镜": 4, "帐": 4, "落": 4, "燕": 4, "信": 4, "绣": 4, "帕": 4, "玉": 4, "驿": 4,
    "路": 4, "渡": 4, "断": 4, "戟": 4, "苑": 4, "废": 4, "磬": 4, "唱": 4, "雀": 4,
    "帖": 4, "拓": 4, "片": 4, "剑": 4, "漠": 4, "戍": 4, "号": 4, "印": 4, "穗": 4,
    "笠": 4, "径": 4, "药": 4, "圃": 4, "唳": 4, "韵": 4, "灶": 4, "卷": 4, "肆": 4,
    "铺": 4, "巷": 4, "秤": 4, "卖": 4, "算": 4, "布": 4, "瓮": 4, "念": 4, "过": 4,
    "照": 4, "浸": 4, "映": 4, "半": 4, "又": 4, "在": 4, "向": 4, "带": 4, "借": 4,
    "问": 4, "记": 4, "忘": 4, "尽": 4, "化": 4, "梦": 4, "夜": 4, "月": 4, "叶": 4,
    "事": 4, "暮": 4, "露": 4, "泪": 4, "岁": 4, "醉": 4, "忆": 4, "故": 4, "旧": 4,
    "恨": 4, "怨": 4, "倦": 4, "自": 4, "正": 4, "更": 1, "当": 4, "担": 4, "令": 4,
    # 补充（骨架扫描补齐）
    "分": 1, "惊": 1, "江": 1, "湿": 1, "生": 1, "锦": 3, "残": 2, "漏": 4, "雁": 4,
    "寻": 2, "色": 4, "只": 3, "口": 3, "佩": 4, "址": 3, "碑": 1, "火": 3, "大": 4,
    "朔": 4, "铁": 3, "胡": 2, "铠": 3, "桨": 3, "良": 2, "离": 2, "犬": 3, "吠": 4,
    "锄": 2, "棋": 2, "床": 2, "遗": 2, "簪": 1, "幡": 1, "钱": 2, "骏": 4, "堤": 1,
    "折": 2, "锣": 2, "晚": 3, "盘": 2, "发": 4, "说": 1, "梆": 1, "糖": 2, "木": 4,
    "拂": 2, "素": 4, "绣": 4,
    "扇": 4, "爆": 4, "叫": 4, "画": 4, "鹤": 4, "梵": 4, "镜": 4, "荡": 4, "幔": 4,
    "素": 4, "误": 4, "悟": 4, "树": 4, "岁": 4, "霭": 4, "翠": 4, "峭": 4, "絮": 4,
}

TONE = dict(_PRECISE)

# 补充声调（意象包扩到 8 个/组后新增的字）
TONE.update({
    "纸": 3,
    "环": 2,
    "衣": 1,
    "剑": 4,
    "鼓": 3,
    "渔": 2,
    "马": 3,
    "铁": 3,
    "暮": 4,
    "更": 1,
    "风": 1,
    "声": 1,
    "绣": 4,
    "鞋": 2,
    "囊": 2,
    "桨": 3,
    "笛": 2,
    "鞭": 1,
    "伞": 3,
    "军": 1,
    "令": 4,
    "战": 4,
    "血": 4,
    "鞍": 1,
    "旧": 4,
    "刀": 1,
    "屋": 1,
    "鸣": 2,
    "泉": 2,
    "盘": 2,
    "篮": 2,
    "碗": 3,
    "遗": 2,
    "物": 4,
    "佛": 2,
    "号": 4,
    "木": 4,
    "梳": 1,
    "函": 2,
    "素": 4,
    "帐": 4,
    "快": 4,
    "腰": 1,
    "带": 4,
    "锦": 3,
    "短": 3,
    "铜": 2,
    "锣": 2,
    "吆": 1,
    "喝": 1,
    "车": 1,
    "铃": 2,
    "罐": 4,
    "凳": 4,
    "炉": 2,
    "香": 1,
    "念": 4,
    "珠": 1,
    "拂": 2,
    "尘": 2,
    "团": 2,
    "蒲": 2,
    "卷": 4,
    "盏": 3,
    "经": 1,
    "梵": 4,
    "音": 1,
    "鱼": 2,
    "钟": 1,
    "涛": 2,
    "松": 1,
    "影": 3,
    "塔": 3,
    "云": 2,
    "池": 2,
    "莲": 2,
    "痕": 2,
    "苔": 2,
    "阶": 1,
    "石": 2,
    "门": 2,
    "山": 1,
    "烟": 1,
    "光": 1,
    "月": 4,
    "花": 1,
    "灯": 1,
    "窗": 1,
    "英": 1,
    "柴": 2,
    "古": 3,
    "砚": 4,
    "印": 4,
    "址": 3,
    "故": 4,
    "下": 4,
    "客": 4,
    "船": 2,
    "远": 3,
    "中": 1,
    "槛": 3,
    "后": 4,
    "院": 4,
    "少": 4,
    "归": 1,
    "陶": 2,
    "笑": 4,
    "点": 3,
})


# 骨架连接词（单字动词/介词，声调必填）
CONNECTORS = "落过照浸掩映生满半又在与向随带惊起湿冷暖斜分隔锁借问寻记忘空尽成化挑拾"

# 题材 → 单字句内虚词（补足奇数字数用）
FILLERS: dict[str, list[str]] = {
    "相思": ["又", "空", "正", "半"],
    "离别": ["又", "正", "只", "空"],
    "怀古": ["自", "空", "尽", "只"],
    "家国": ["正", "又", "尽", "自"],
    "江湖": ["正", "又", "只", "自"],
    "隐逸": ["自", "空", "尽", "只"],
    "悼亡": ["空", "又", "只", "尽"],
    "少年": ["正", "又", "只", "自"],
    "市井": ["正", "又", "尽", "只"],
    "禅意": ["自", "空", "只", "尽"],
}


# ================================================================ 十大题材

THEMES: dict[str, dict] = {
    "相思": {
        "core": "不说「我想你」，只写你留下的痕迹",
        "zhe": ["言前", "一七", "人辰"],
        "images": [
            ["灯花", "窗纸", "铜镜", "罗帐", "落英", "双燕", "回廊", "芭蕉"],
            ["残漏", "砧声", "笛声", "暮雨", "雁鸣", "虫吟", "更鼓", "风声"],
            ["信笺", "绣帕", "玉环", "锦书", "炉烟", "寒衣", "绣鞋", "香囊"],
        ],
        "pack_names": ["视觉（你走后屋里剩下的）", "听觉（夜里替你说话的声音）", "器物（可触摸的信物）"],
        "allusions": ["尾生抱柱", "鲛人泣珠", "牛郎织女", "洛神", "青衫湿"],
        "pitfalls": [
            "把「思念」直接写进句子：主语+想你+程度，等于没写；改成「信笺压在灯下没拆」这类动作。",
            "通篇只写对方不写自己：相思词的重量在「我这里的物证」，缺了物证就空。",
        ],
    },
    "离别": {
        "core": "离别的信息量在「最后一眼」与「回不去的那条路」",
        "zhe": ["言前", "中东", "灰堆"],
        "images": [
            ["长亭", "短亭", "柳色", "酒旗", "驿路", "孤帆", "残照", "渡口"],
            ["阳关", "骊歌", "马嘶", "橹声", "琵琶", "钟声", "桨声", "笛声"],
            ["柳枝", "酒杯", "行囊", "青衫", "玉佩", "舟灯", "马鞭", "纸伞"],
        ],
        "pack_names": ["视觉（送别地的坐标）", "听觉（告别时的声音）", "器物（带得走与带不走的）"],
        "allusions": ["阳关三叠", "灞桥折柳", "湘妃竹", "青衫湿", "二十四桥"],
        "pitfalls": [
            "只写「挥泪告别」：没有具体地点与动作，读者无处落脚；先给一个可指认的地标。",
            "把送别写成风景明信片：柳、帆、夕阳各一句，没有一件东西承载决定（走/留）。",
        ],
    },
    "怀古": {
        "core": "用一件今天的残物，撬开一整段旧时间",
        "zhe": ["江阳", "姑苏", "中东"],
        "images": [
            ["遗址", "残碑", "断剑", "荒台", "故苑", "宫墙", "苔痕", "废井"],
            ["钟鼓", "松风", "鸦啼", "渔歌", "渔唱", "更鼓", "溪声", "柴斧"],
            ["古剑", "石马", "碑帖", "拓片", "残瓦", "铁马", "古砚", "玉印"],
        ],
        "pack_names": ["视觉（今与昔的重叠处）", "听觉（把废墟叫醒的声音）", "器物（时间的证物）"],
        "allusions": ["黍离之悲", "铜雀台", "乌衣巷", "苏武牧羊", "卧薪尝胆"],
        "pitfalls": [
            "朝代堆砌：汉唐宋元一口气列完，等于没有朝代；只留一个具体年份/地名/人名。",
            "借古讽今太直白：议论句盖过画面，怀古词要先「看见」再「感慨」。",
        ],
    },
    "家国": {
        "core": "大词要落到小物件：一封家书、一面残旗、一枚印",
        "zhe": ["江阳", "言前", "怀来"],
        "images": [
            ["关山", "烽火", "边城", "大漠", "朔风", "残旗", "戍楼", "铁衣"],
            ["号角", "鼓角", "胡笳", "刁斗", "战马", "笳声", "号令", "军鼓"],
            ["弓刀", "铠甲", "旌旗", "印信", "兵符", "家书", "铁衣", "血书"],
        ],
        "pack_names": ["视觉（边地的尺度）", "听觉（战争的背景音）", "器物（身份与牵挂）"],
        "allusions": ["精卫填海", "苏武牧羊", "荆轲易水", "卧薪尝胆"],
        "pitfalls": [
            "口号化：把「报国」「热血」当韵脚，副歌会变成标语；换成可执行的动作。",
            "只有宏阔没有私人：家国词最好有一处「我」的私事（家书/名字/未寄出的信）。",
        ],
    },
    "江湖": {
        "core": "江湖不是打斗，是「来过又走了」的潇洒与代价",
        "zhe": ["遥条", "江阳", "油求"],
        "images": [
            ["孤舟", "芦花", "剑穗", "酒旗", "野渡", "断桥", "蓑衣", "残阳"],
            ["箫声", "桨声", "马蹄", "风声", "琴声", "钟声", "橹声", "雨声"],
            ["长剑", "酒壶", "斗笠", "短笛", "鱼竿", "青衫", "马鞍", "旧刀"],
        ],
        "pack_names": ["视觉（江湖的坐标）", "听觉（路上的动静）", "器物（侠客的行头）"],
        "allusions": ["高山流水", "庄周梦蝶", "尾生抱柱", "荆轲易水"],
        "pitfalls": [
            "武侠名词大礼包：剑、江湖、恩怨、天涯各来一个，却没有一件具体事发生。",
            "只写潇洒不写代价：没有失去（人名/旧约/伤）的江湖词，听起来像广告。",
        ],
    },
    "隐逸": {
        "core": "写「少」而不是写「山」：茶凉了、锄头钝了",
        "zhe": ["油求", "姑苏", "人辰"],
        "images": [
            ["竹篱", "茅屋", "松径", "荷塘", "药圃", "石阶", "山月", "苔衣"],
            ["柴斧", "溪声", "松涛", "鹤鸣", "琴韵", "犬吠", "鸟鸣", "泉声"],
            ["茶灶", "药炉", "犁锄", "蓑笠", "棋盘", "书卷", "竹篮", "陶碗"],
        ],
        "pack_names": ["视觉（退到哪一步）", "听觉（山里的时间刻度）", "器物（日常的手艺）"],
        "allusions": ["桃花源", "高山流水", "庄周梦蝶", "归去来兮"],
        "pitfalls": [
            "写成旅游宣传：山、水、云、雾四件套，没有一个「我在干什么」。",
            "隐逸变成炫耀清高：少用「红尘」「俗世」作贬义对照，用生活方式本身说话。",
        ],
    },
    "悼亡": {
        "core": "忌嚎哭，写「还在原处等你」的错位",
        "zhe": ["人辰", "一七", "乜斜"],
        "images": [
            ["空床", "旧衣", "遗物", "白幡", "孤灯", "冷镜", "纸灰", "坟草"],
            ["挽歌", "经声", "钟鼓", "纸钱", "梵唱", "佛号", "木鱼", "香火"],
            ["香灰", "酒杯", "旧信", "木梳", "枕函", "素帐", "纸伞", "遗书"],
        ],
        "pack_names": ["视觉（留下来没动的）", "听觉（仪式的声音）", "器物（她的与我的）"],
        "allusions": ["湘妃竹", "庄周鼓盆", "潘岳悼亡", "牛郎织女"],
        "pitfalls": [
            "把死亡写成景观：白、冷、灰一路铺陈，却没有一件只有你们两人知道的事。",
            "用「天堂」「来世」收尾：落在宗教套话上会稀释痛感，用生活细节收更狠。",
        ],
    },
    "少年": {
        "core": "少年感 = 明知会输还先冲出去的那一步",
        "zhe": ["遥条", "中东", "发花"],
        "images": [
            ["快马", "春衫", "长街", "元宵", "花灯", "纸鸢", "柳堤", "酒旗"],
            ["箫鼓", "爆竹", "酒令", "歌板", "马蹄", "锣鼓", "笑声", "鼓点"],
            ["折扇", "玉佩", "马鞭", "灯笼", "风筝", "腰刀", "锦带", "短笛"],
        ],
        "pack_names": ["视觉（热闹与少年同框）", "听觉（节庆与奔跑）", "器物（还没用旧的装备）"],
        "allusions": ["荆轲易水", "闻鸡起舞", "投笔从戎", "高山流水"],
        "pitfalls": [
            "少年写成小孩：叠字、蹦跳、糖葫芦堆一起会低龄；少年感要靠「决定」不靠「可爱」。",
            "用「时光不老我们不散」这类口号收尾：青春词最忌励志标语。",
        ],
    },
    "市井": {
        "core": "把日子写成可以闻到的：油烟、铜钱、吆喝",
        "zhe": ["发花", "梭波", "遥条"],
        "images": [
            ["长街", "茶棚", "酒肆", "当铺", "巷口", "灯笼", "石桥", "挑担"],
            ["叫卖", "算盘", "锣声", "说书", "铜锣", "锅铲", "吆喝", "车铃"],
            ["铜钱", "糖画", "油纸伞", "布头", "秤杆", "蒸笼", "陶碗", "竹篮"],
        ],
        "pack_names": ["视觉（一条街的纵深）", "听觉（市声的节奏）", "器物（手里的生计）"],
        "allusions": ["举案齐眉", "破镜重圆", "尾生抱柱", "二十四桥"],
        "pitfalls": [
            "把市井写成脏乱差清单：只罗列物件没有人物关系，读者记不住。",
            "古词与今词混用出错：写古代市井就别放「手机」「外卖」（L6 会报）。",
        ],
    },
    "禅意": {
        "core": "禅意靠「减法」：少一个动作，多一层空白",
        "zhe": ["人辰", "油求", "姑苏"],
        "images": [
            ["山门", "石阶", "苔痕", "莲池", "孤松", "云影", "残经", "塔影"],
            ["钟声", "木鱼", "梵音", "风铃", "溪声", "鹤鸣", "松涛", "泉声"],
            ["蒲团", "经卷", "药罐", "茶盏", "念珠", "拂尘", "香炉", "木凳"],
        ],
        "pack_names": ["视觉（山寺的层次）", "听觉（把心按下去的声音）", "器物（修行的手边物）"],
        "allusions": ["庄周梦蝶", "桃花源", "拈花一笑", "菩提本无树"],
        "pitfalls": [
            "禅意写成说教：「放下」「随缘」「无求」全塞进副歌，变成心灵鸡汤。",
            "堆佛词：菩提、明镜、尘埃三连，缺一件生活里的事来承接。",
        ],
    },
}

THEME_ALIAS = {k: k for k in THEMES}
THEME_ALIAS.update({"爱情": "相思", "思念": "相思", "送别": "离别", "怀乡": "离别",
                    "爱国": "家国", "边塞": "家国", "武侠": "江湖", "田园": "隐逸",
                    "归隐": "隐逸", "悼念": "悼亡", "青春": "少年", "人间": "市井",
                    "佛系": "禅意", "古风": "相思"})


# ================================================================ 典故库（每条：出处 / 原意 / 示范句 / 用法与禁忌）

ALLUSIONS: dict[str, dict] = {
    "尾生抱柱": {
        "source": "《庄子·盗跖》",
        "meaning": "尾生与女子约于桥下，女子未至，水涨不去，抱柱而死；原意是「守信至死」。",
        "sample": "桥柱还留着指痕，水位已退了三年",
        "tip": "只用在「痴守/失约」语境；不能反过来当「背信弃义」用。",
    },
    "鲛人泣珠": {
        "source": "晋·张华《博物志》（亦见《搜神记》）",
        "meaning": "鲛人寄居人家，临别泣泪成珠；喻以眼泪换来的贵重之物。",
        "sample": "你若落一滴泪，我就有整盘的珠子",
        "tip": "适合写「代价/不值得」；别写成「鲛人唱歌」这类跑偏设定。",
    },
    "牛郎织女": {
        "source": "《古诗十九首·迢迢牵牛星》（星名早见《诗经·小雅·大东》）",
        "meaning": "隔河相望，一年一会；喻被外力隔开的相爱者。",
        "sample": "银河不宽，够我们走一整年",
        "tip": "适合「距离/等待」；用在「团聚欢乐」场景属于反用，需点明反差。",
    },
    "洛神": {
        "source": "曹植《洛神赋》",
        "meaning": "写可望不可即的神女之美；喻理想化的、无法拥有的人。",
        "sample": "你在水中央，我连鞋都没敢脱",
        "tip": "适合「仰视/求不得」；不要用来写具体婚恋日常。",
    },
    "青衫湿": {
        "source": "白居易《琵琶行》「江州司马青衫湿」",
        "meaning": "听曲落泪，泪湿官职最低的青衫；喻同是天涯沦落人的共感。",
        "sample": "满座都在听，只有我的袖子先湿",
        "tip": "重点在「共感/沦落」，不是单纯哭；别写成衣服颜色描写。",
    },
    "阳关三叠": {
        "source": "王维《送元二使安西》（后人谱为《阳关三叠》）",
        "meaning": "劝酒送别，一唱三叠；喻反复不舍的送别。",
        "sample": "第三杯了，你还没接过缰绳",
        "tip": "只用于送别；「三叠」可化作三段重复的结构。",
    },
    "灞桥折柳": {
        "source": "《三辅黄图》载灞桥；折柳赠别为汉唐风俗",
        "meaning": "长安东灞桥折柳送客；柳谐「留」，喻挽留。",
        "sample": "桥头那截柳，被我折成了两半",
        "tip": "适合送别；「柳」的谐音挽留义别和写景柳树混为一谈。",
    },
    "湘妃竹": {
        "source": "晋·张华《博物志》（舜崩苍梧，二妃泪染竹成斑）",
        "meaning": "斑竹是泪痕所化；喻丧偶之痛、至死不渝的哀。",
        "sample": "竹上的斑点，数到第七节就断了",
        "tip": "专用于「丧偶/至哀」；写普通离别会过重。",
    },
    "二十四桥": {
        "source": "杜牧《寄扬州韩绰判官》「二十四桥明月夜」",
        "meaning": "扬州月夜名景；喻繁华旧梦与故地重游。",
        "sample": "桥数到二十四，月亮还没落",
        "tip": "适合怀旧/故地；不要当作真实桥的数量考据使用。",
    },
    "黍离之悲": {
        "source": "《诗经·王风·黍离》",
        "meaning": "故都废墟长满黍稷，行者悲而作诗；喻亡国之痛与物是人非。",
        "sample": "宫殿的位置，长出了一人高的谷子",
        "tip": "用于家国/怀古大悲；日常失恋用会失当。",
    },
    "铜雀台": {
        "source": "曹操建于邺；杜牧《赤壁》「铜雀春深锁二乔」",
        "meaning": "胜利者收藏美人与权力的象征；喻征服与囚禁。",
        "sample": "台修得再高，锁住的也只是两个人",
        "tip": "用「锁」的意象时注意不要把「二乔」写成真实历史结局。",
    },
    "乌衣巷": {
        "source": "刘禹锡《乌衣巷》",
        "meaning": "王谢旧宅今成寻常百姓家；喻门第兴衰。",
        "sample": "燕子还认这门，门牌换了三回",
        "tip": "适合写兴衰；用「燕子」要落到具体一户人家的变化。",
    },
    "苏武牧羊": {
        "source": "《汉书·李广苏建传》",
        "meaning": "持节牧羊十九年不改汉节；喻持守与归期无望。",
        "sample": "手里的节旄，毛都掉光了还没放",
        "tip": "用于「守节/长期坚持」；不要写成单纯放牧场景。",
    },
    "卧薪尝胆": {
        "source": "《史记·越王勾践世家》",
        "meaning": "勾践睡柴草、尝苦胆以自励；喻忍辱图强。",
        "sample": "柴房的灯，比宫殿的亮",
        "tip": "适合励志/复仇线；不要用在轻松日常，语气会打架。",
    },
    "精卫填海": {
        "source": "《山海经·北山经》",
        "meaning": "溺死化鸟，衔木石填海；喻明知不可为而为的执念。",
        "sample": "我衔的石头，海不知道",
        "tip": "重点在「徒劳但有意义」；别写成环保或工程叙事。",
    },
    "荆轲易水": {
        "source": "《史记·刺客列传》（《易水歌》）",
        "meaning": "易水送别，一去不返；喻决绝赴死或孤注一掷。",
        "sample": "水这么冷，他还是往前走了",
        "tip": "用于「决绝/告别」；情绪极重，不适合轻愁。",
    },
    "高山流水": {
        "source": "《列子·汤问》（亦见《吕氏春秋·本味》）",
        "meaning": "伯牙鼓琴，钟子期知音；喻知音难遇。",
        "sample": "我不弹了，因为没有人会停下手里的活",
        "tip": "写「懂」而不是写「弹琴」；别把它当友情万金油。",
    },
    "庄周梦蝶": {
        "source": "《庄子·齐物论》",
        "meaning": "不知周之梦为蝴蝶，还是蝴蝶之梦为周；喻真假难辨、物我两忘。",
        "sample": "醒来的时候，翅膀还压在身下",
        "tip": "适合「恍惚/身份不确定」；不要写成单纯做梦。",
    },
    "桃花源": {
        "source": "陶渊明《桃花源记》",
        "meaning": "避世之地，再寻不得；喻理想国与不可复返。",
        "sample": "第二次去，桃花开在别人家的院里",
        "tip": "关键在「再寻不得」；只写景就成了游记。",
    },
    "归去来兮": {
        "source": "陶渊明《归去来兮辞》",
        "meaning": "弃官归田的宣言；喻主动退出与自我保全。",
        "sample": "官印交出去那天，风特别轻",
        "tip": "适合「主动离开」；不要当成被迫退隐来写。",
    },
    "庄周鼓盆": {
        "source": "《庄子·至乐》",
        "meaning": "妻死，庄子鼓盆而歌；喻以通达消解至痛。",
        "sample": "他敲着盆，谁也不敢劝",
        "tip": "悼亡用，但基调是「通达」；与湘妃竹的「至哀」不可混用。",
    },
    "潘岳悼亡": {
        "source": "潘岳《悼亡诗》三首（《文选》）",
        "meaning": "开悼亡诗先河，写帷帐、遗物、旧居；喻睹物思人。",
        "sample": "她的梳子还在原来的位置",
        "tip": "最稳的悼亡写法：只写遗物，不写哭声。",
    },
    "闻鸡起舞": {
        "source": "《晋书·祖逖传》",
        "meaning": "祖逖与刘琨闻鸡鸣即起练剑；喻及时奋发。",
        "sample": "鸡叫第一声，剑已经出鞘",
        "tip": "适合少年/励志；不要写成早起打卡的现代梗。",
    },
    "投笔从戎": {
        "source": "《后汉书·班超传》",
        "meaning": "班超弃文从军；喻转换人生道路的决断。",
        "sample": "笔搁在案上，人已经出了城门",
        "tip": "适合家国/少年；用「笔」与「刀」的具体动作承载。",
    },
    "举案齐眉": {
        "source": "《后汉书·梁鸿传》",
        "meaning": "梁鸿妻孟光送饭举案至眉，相敬如宾；喻夫妻相敬。",
        "sample": "碗举到眉那么高，日子就低下来了",
        "tip": "写「敬」不写「甜」；用于市井/家常最贴。",
    },
    "破镜重圆": {
        "source": "唐·孟棨《本事诗·情感》（徐德言与乐昌公主）",
        "meaning": "分镜各持一半，后以镜为凭重合；喻离散后重逢。",
        "sample": "半边镜子，磨了十年才配上",
        "tip": "必须落在「重逢/凭证」；只写镜子会跑题。",
    },
    "拈花一笑": {
        "source": "禅宗公案，见《五灯会元》",
        "meaning": "世尊拈花，迦叶微笑，以心传心；喻不必言说的默契。",
        "sample": "他什么也没说，我点了点头",
        "tip": "适合禅意/克制的关系；不要用来写热闹场面。",
    },
    "菩提本无树": {
        "source": "慧能偈，见《六祖坛经》",
        "meaning": "破除对「有」的执着；喻心不被物所缚。",
        "sample": "扫了一辈子落叶，院子本来就没有树",
        "tip": "适合禅意收尾；用之前先有具体动作，否则成口号。",
    },
    "望帝啼鹃": {
        "source": "晋·常璩《华阳国志·蜀志》（杜宇化鹃）；李商隐《锦瑟》用典",
        "meaning": "蜀王失国而死，魂化杜鹃啼血；喻哀怨不绝的思念。",
        "sample": "这鸟叫了整夜，像替谁喊冤",
        "tip": "适合相思/亡国；「杜鹃」也可指花，注意语境别混。",
    },
    "巴山夜雨": {
        "source": "李商隐《夜雨寄北》",
        "meaning": "夜雨涨池，归期未定；喻异地思念。",
        "sample": "雨把池塘填满了，我还没攒够路费",
        "tip": "适合异地相思；不要写成单纯天气描写。",
    },
    "嫦娥奔月": {
        "source": "《淮南子·览冥训》",
        "meaning": "窃药飞升，独居月宫；喻得到之后的长久孤独。",
        "sample": "高处风大，连影子都没有",
        "tip": "重点在「孤独的代价」；不要写成浪漫升仙。",
    },
    "结草衔环": {
        "source": "《左传·宣公十五年》（结草）；《续齐谐记》（衔环）",
        "meaning": "受恩必报，生死不忘；喻报恩。",
        "sample": "这恩我没还上，就先欠着",
        "tip": "适合「恩义」；不要和「姻缘」混用。",
    },
}


# ================================================================ 风格与句式

STYLES: dict[str, dict] = {
    "抒情": {"id": "shuqing", "name": "抒情国风", "pattern": "P2", "density": "偶数句押韵即可（2/4 句）",
             "words": "动词优先、少用形容词；一句一个画面"}, 
    "古风": {"id": "gufeng", "name": "古风叙事", "pattern": "P1", "density": "段内 2/4 句押，换段可转韵",
             "words": "五言为主、虚词节制；可局部对仗"},
    "戏腔": {"id": "xiqiang", "name": "戏腔国风", "pattern": "P3", "density": "韵脚密（1/2/4 句），长短句交替",
             "words": "长短句、三字逗、衬字；副歌可加拖腔字"},
    "国潮": {"id": "guochao", "name": "国潮节奏", "pattern": "P2", "density": "副歌句句押，主歌偶句押",
             "words": "短句+重音动词；可少量现代意象（需自查 L6）"},
    "叙事": {"id": "narrative", "name": "叙事国风", "pattern": "P1", "density": "每段一韵，末尾转韵收束",
             "words": "主歌交代时间地点人物；副歌只抒情不推进"},
}

STYLE_ALIAS = {k: k for k in STYLES}
STYLE_ALIAS.update({
    "shuqing": "抒情", "gufeng": "古风", "xiqiang": "戏腔", "guochao": "国潮",
    "narrative": "叙事", "抒情国风": "抒情", "古风叙事": "古风", "戏腔国风": "戏腔",
})

PATTERNS: dict[str, dict] = {
    "P1": {
        "id": "P1",
        "name": "五言主歌 + 七言副歌（古雅稳妥）",
        "verse": [5, 5, 5, 5],
        "pre": [5, 5],
        "chorus": [7, 7, 7, 7],
        "bridge": [5, 5],
        "outro": [7, 7],
        "layout": "主歌 4×5 字；预副歌 2×5；副歌 4×7；桥 2×5；尾 2×7",
        "rhyme_note": "主歌第 2、4 句押；副歌第 1、2、4 句押；尾句必须押",
        "ci_hint": dict(name="浣溪沙", chars=42, layout="7·7·7／7·7·7", note="双调 42 字，句式对照用（严格平仄谱以《钦定词谱》为准）"),
        "why": "五言叙述密、副歌七言才放得开；国风听众最熟的呼吸感。",
    },
    "P2": {
        "id": "P2",
        "name": "七言主歌 + 长短句副歌（现代国风主流）",
        "verse": [7, 7, 7, 7],
        "pre": [7, 7],
        "chorus": [7, 7, 9, 7],
        "bridge": [7, 7],
        "outro": [9, 7],
        "layout": "主歌 4×7 字；预副歌 2×7；副歌 7·7·9·7；桥 2×7；尾 9·7",
        "rhyme_note": "主歌第 2、4 句押；预副歌第 2 句押；副歌第 1、2、4 句押（第 3 句拉长可不押）",
        "ci_hint": dict(name="蝶恋花", chars=60, layout="7·4·5·7·7／7·4·5·7·7", note="双调 60 字，句式对照用（非严格平仄谱）"),
        "why": "七言能装下叙事细节；副歌第 3 句放到 9 字，正好放金句的长句尾。",
    },
    "P3": {
        "id": "P3",
        "name": "长短句 3·5·7 混（戏腔/古风圈）",
        "verse": [5, 7, 5, 7],
        "pre": [5, 5],
        "chorus": [5, 5, 7, 9],
        "bridge": [3, 7],
        "outro": [7, 9],
        "layout": "主歌 5·7·5·7；预副歌 2×5；副歌 5·5·7·9；桥 3·7；尾 7·9",
        "rhyme_note": "副歌第 1、2、4 句押；桥段可转韵；尾句必须押",
        "ci_hint": dict(name="虞美人", chars=56, layout="7·5·7·9／7·5·7·9", note="双调 56 字，句式对照用（非严格平仄谱）"),
        "why": "长短交替给戏腔留拖腔位置；三字逗是最稳的钩子。",
    },
}

SECTIONS_FN = {
    "主歌A": "建立时空与人物（我在哪、看见什么）",
    "主歌B": "推进一层：把物件与关系说清（发生了什么）",
    "主歌C": "再补一个具体场景（细节而非情绪）",
    "预副歌": "抬升：收短、提问、把镜头推近",
    "副歌": "只抒情，不推进；每句都有一个可看的物",
    "副歌（再现）": "同一韵、同一句式，换 1–2 个物象即可",
    "桥": "转折：否定前面或换视角（对方/旁观者/多年后）",
    "尾": "收束：回到主歌第一句的物象，或留一个空镜",
}


# ================================================================ 结构规划


def plan_structure(total_lines: int) -> list[dict]:
    """按目标总句数给出段落表（段落顺序固定：主歌→预副歌→副歌→桥→副歌→尾）。"""
    n = max(12, min(48, int(total_lines)))
    if n <= 16:
        blocks = [("主歌A", 4, "verse"), ("主歌B", 4, "verse"),
                  ("副歌", 4, "chorus"), ("副歌（再现）", 4, "chorus")]
    elif n <= 22:
        blocks = [("主歌A", 4, "verse"), ("主歌B", 4, "verse"), ("预副歌", 2, "prechorus"),
                  ("副歌", 4, "chorus"), ("桥", 2, "bridge"),
                  ("副歌（再现）", 4, "chorus"), ("尾", 2, "outro")]
    else:
        blocks = [("主歌A", 4, "verse"), ("主歌B", 4, "verse"), ("主歌C", 4, "verse"),
                  ("预副歌", 2, "prechorus"), ("副歌", 4, "chorus"), ("桥", 2, "bridge"),
                  ("副歌（再现）", 4, "chorus"), ("尾", 2, "outro")]
    out: list[dict] = []
    for i, (name, lines, kind) in enumerate(blocks, 1):
        out.append({"index": i, "name": name, "lines": lines, "kind": kind,
                    "function": SECTIONS_FN.get(name, "")})
    return out


def section_char_pattern(pattern: dict, kind: str) -> list[int]:
    key = {"verse": "verse", "prechorus": "pre", "chorus": "chorus",
           "bridge": "bridge", "outro": "outro"}.get(kind, "verse")
    seq = list(pattern[key])
    return seq


def rhyme_positions(kind: str, n_lines: int) -> list[int]:
    """返回段内「必须押韵」的句序号（1 基）。"""
    if kind == "chorus":
        base = [1, 2, 4]
    elif kind == "prechorus":
        base = [2]
    elif kind == "bridge":
        base = [2]
    elif kind == "outro":
        base = [2]
    else:
        base = [2, 4]
    return [x for x in base if x <= n_lines] or [n_lines]


# ================================================================ 需求解析


def _int_of(value, default: int, lo: int, hi: int) -> int:
    try:
        v = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def normalize_theme(raw: str) -> tuple[str, str | None]:
    t = (raw or "").strip()
    if not t:
        return "相思", None
    if t in THEMES:
        return t, None
    if t in THEME_ALIAS:
        return THEME_ALIAS[t], f"题材「{t}」按近义归到「{THEME_ALIAS[t]}」"
    # 模糊：包含关系
    for key in THEMES:
        if key in t:
            return key, f"题材「{t}」按包含关系归到「{key}」"
    return "相思", f"题材「{t}」不在十大题材内，已按「相思」出蓝图（可改 theme 后重跑）"


def normalize_style(raw: str) -> tuple[str, str | None]:
    s = (raw or "").strip()
    if not s:
        return "抒情", None
    if s in STYLES:
        return s, None
    if s in STYLE_ALIAS:
        return STYLE_ALIAS[s], None
    for key in STYLES:
        if key in s:
            return key, f"风格「{s}」按包含关系归到「{key}」"
    return "抒情", f"风格「{s}」不在 5 套风格内（抒情/古风/戏腔/国潮/叙事），已按「抒情」出蓝图"


def normalize_rhyme(raw: str) -> tuple[str | None, str | None]:
    s = (raw or "").strip().lower()
    if not s:
        return None, None
    for zhe in ZHES:
        if zhe in s:
            return zhe, None
    if s in MU_TO_ZHE:
        return MU_TO_ZHE[s], f"韵母「{s}」归到「{MU_TO_ZHE[s]}」辙"
    # 用代表性字猜（用户可能写「天」）
    for zhe, words in RHYME_WORDS.items():
        for w in words:
            if s and s in w:
                return zhe, f"按韵脚字「{s}」归到「{zhe}」辙"
    return None, f"无法识别 rhyme=「{raw}」，已改为自动推荐（可用：{'、'.join(ZHE_ORDER)}）"


def build_brief(raw: dict) -> tuple[dict, list[str]]:
    notes: list[str] = []
    if not isinstance(raw, dict):
        notes.append("输入 JSON 不是对象，已按空需求（{}）处理")
        raw = {}
    known = {"theme", "style", "mood", "voice", "perspective", "duration_lines", "rhyme", "style_hint"}
    for k in raw:
        if k not in known:
            notes.append(f"忽略未知字段「{k}」（可用：{'、'.join(sorted(known))}）")

    theme, n1 = normalize_theme(str(raw.get("theme", "")))
    if n1:
        notes.append(n1)
    style, n2 = normalize_style(str(raw.get("style", "")))
    if n2:
        notes.append(n2)
    rhyme, n3 = normalize_rhyme(str(raw.get("rhyme", "")))
    if n3:
        notes.append(n3)

    voice_raw = str(raw.get("voice", "")).strip() or "女"
    voice = {"男": "男声", "女": "女声", "合唱": "合唱", "男声": "男声", "女声": "女声"}.get(voice_raw, "女声")
    if voice_raw not in ("男", "女", "合唱", "男声", "女声"):
        notes.append(f"voice=「{voice_raw}」不认识，已按女声处理（可选：男/女/合唱）")

    persp_raw = str(raw.get("perspective", "")).strip() or "第一"
    persp = persp_raw if persp_raw in ("第一", "第二", "第三") else "第一"
    if persp_raw not in ("第一", "第二", "第三"):
        notes.append(f"perspective=「{persp_raw}」不认识，已按第一人称处理（可选：第一/第二/第三）")

    duration = _int_of(raw.get("duration_lines", 22), 22, 12, 48)
    if raw.get("duration_lines") not in (None, "") and abs(duration - _int_of(raw.get("duration_lines"), -999, 12, 48)) > 0:
        notes.append(f"duration_lines 已夹到 12–48 区间（当前 {duration} 句）")

    brief = {
        "theme": theme,
        "theme_core": THEMES[theme]["core"],
        "style": style,
        "style_id": STYLES[style]["id"],
        "mood": str(raw.get("mood", "")).strip(),
        "voice": voice,
        "perspective": persp,
        "duration_lines": duration,
        "rhyme_forced": rhyme,
        "style_hint": str(raw.get("style_hint", "")).strip(),
        "pattern_id": STYLES[style]["pattern"],
    }
    return brief, notes


# ================================================================ 推荐逻辑


def recommend_rhyme(theme: str, forced: str | None, pattern: dict) -> dict:
    """1 主 2 备，带理由。"""
    fitted = [z for z in ZHES if theme in ZHES[z]["fit"]]
    order = [z for z in THEMES[theme]["zhe"] if z in ZHES] + [z for z in fitted if z not in THEMES[theme]["zhe"]]
    if forced:
        order = [forced] + [z for z in order if z != forced]
    primary = order[0]
    backups = order[1:3] if len(order) > 1 else [z for z in ZHE_ORDER if z != primary][:2]

    def why(z: str) -> str:
        return (f"代表韵母 {ZHES[z]['mu']}；{ZHES[z]['color']}；题材契合："
                f"{'、'.join(ZHES[z]['fit'])}")

    # 韵脚密度：按句式模板的韵位数量给一句提醒
    n_rhyme = sum(len(rhyme_positions(k, 4)) for k in ("verse", "chorus"))
    return {
        "primary": {"zhe": primary, "mu": ZHES[primary]["mu"], "color": ZHES[primary]["color"],
                    "why": ("【用户指定】" if forced == primary else "") + why(primary)},
        "backups": [{"zhe": z, "mu": ZHES[z]["mu"], "color": ZHES[z]["color"],
                     "why": ("【用户指定】" if forced == z else "") + why(z)} for z in backups],
        "rhyme_density": pattern["rhyme_note"],
        "note": (f"一首词只用一辙；主歌偶句押、副歌 1/2/4 句押。"
                 f"每 4 句至少 {n_rhyme} 个韵脚落在上表辙内。"
                 + ("（跨段转韵可以有，但同段内换辙会被 lint 报 L1 error。）" if not forced else "")),
    }


def pick_patterns(brief: dict) -> list[dict]:
    pid = brief["pattern_id"]
    ordered = [pid] + [p for p in ("P2", "P1", "P3") if p != pid]
    out = []
    for i, key in enumerate(ordered[:3], 1):
        p = dict(PATTERNS[key])
        p["rank"] = i
        p["fit_note"] = ("首选：与当前风格最贴" if i == 1 else
                         ("次选：换五言更古雅" if key == "P1" else
                          ("备选：长短句更像戏腔" if key == "P3" else "备选：七言最好叙事")))
        out.append(p)
    return out


def pick_images(theme: str) -> list[dict]:
    data = THEMES[theme]
    packs = []
    for i, items in enumerate(data["images"]):
        name = data["pack_names"][i] if i < len(data["pack_names"]) else f"意象组 {i + 1}"
        packs.append({
            "index": i + 1,
            "name": name,
            "items": items,
            "count": len(items),
            "usage": ("每句只用 1 个，组内不叠加；同一段最多用 2 个。" if i == 0 else
                      "用来做副歌的听觉记忆点（一声一物，别铺满）。" if i == 1 else
                      "放在句尾或金句里，让抽象情绪有实物可落。"),
        })
    return packs


def pick_allusions(theme: str, limit: int = 5) -> list[dict]:
    names = THEMES[theme]["allusions"][:max(3, min(5, limit))]
    out = []
    for n in names:
        a = ALLUSIONS.get(n)
        if not a:
            continue
        out.append({"name": n, "source": a["source"], "meaning": a["meaning"],
                    "sample": a["sample"], "tip": a["tip"],
                    "quota": ALLUSION_QUOTA_TEXT})
    return out


def plan_card(brief: dict, structure: list[dict], pattern: dict, rhyme: dict) -> dict:
    zhe = rhyme["primary"]["zhe"]
    rows = []
    for sec in structure:
        chars = section_char_pattern(pattern, sec["kind"])
        rp = rhyme_positions(sec["kind"], sec["lines"])
        rows.append({
            "name": sec["name"],
            "kind": sec["kind"],
            "lines": sec["lines"],
            "chars_per_line": chars[:sec["lines"]] if len(chars) >= sec["lines"] else
                              (chars + [chars[-1]] * sec["lines"])[:sec["lines"]],
            "char_range": f"{min(chars)}–{max(chars)} 字",
            "rhyme_lines": rp,
            "rhyme_lines_text": "第 " + "、".join(str(x) for x in rp) + " 句",
            "function": sec["function"],
            "hook": sec["kind"] in ("chorus", "outro"),
        })
    total = sum(r["lines"] for r in rows)
    lo = min(min(r["chars_per_line"]) for r in rows)
    hi = max(max(r["chars_per_line"]) for r in rows)
    return {
        "sections": rows,
        "total_lines": total,
        "total_chars_range": f"{lo * total}–{hi * total} 字（含标题不含标点）",
        "rhyme": zhe,
        "hook_lines": [f"{r['name']} 第 1 句" for r in rows if r["hook"]],
        "note": (f"共 {total} 句。韵脚位置按句式 {pattern['id']}：{pattern['rhyme_note']}。"
                 "副歌第一句与最后一句是金句位，必须含具体物象。"),
    }


def hook_plan(card: dict) -> dict:
    hooks = card["hook_lines"][:3] or ["副歌 第 1 句"]
    return {
        "positions": hooks,
        "requirement": "金句 = 具体物象 + 一个动词 + 一层反常识（把话说反/说小/说具体）。",
        "examples": [
            "器物型：「茶凉了，杯沿还是你咬过的形状」——物 + 痕迹",
            "时间型：「桥数到二十四，月亮还没落」——数字 + 未完成",
            "反常识型：「我衔的石头，海不知道」——徒劳 + 无人知",
        ],
        "check": "写完自检：金句去掉形容词还剩画面吗？只剩情绪词就重写。",
    }


# ================================================================ .lyr 骨架


def _is_common_char(ch: str) -> bool:
    """GB2312 一级常用字判断（与 lint L8 同口径）：占位骨架只用常用字，免得 L8 报生僻。"""
    try:
        b = ch.encode("gb2312")
    except UnicodeEncodeError:
        return False
    return not (len(b) == 2 and b[0] > 0xD7)


GENERIC_WORDS = [
    "灯火", "门窗", "月夜", "风声", "石阶", "竹影", "花枝", "山前",
    "雨后", "江边", "舟中", "灯下", "窗前", "客船", "旧路", "远山",
    "寒水", "长夜", "小院", "半墙", "青瓦", "白露", "门槛", "水边",
]


def _penta_words(theme: str) -> list[str]:
    """占位句用词池：本题材意象（只留常用字、避开典故标志词）+ 通用意象（降低重复率）。"""
    words: list[str] = []
    for group in THEMES[theme]["images"]:
        for w in group:
            if len(w) == 2 and all(_is_common_char(c) for c in w) and not _has_allusion_key(w):
                words.append(w)
    for w in GENERIC_WORDS:
        if w not in words and all(_is_common_char(c) for c in w) and not _has_allusion_key(w):
            words.append(w)
    if not words:
        words = ["灯火", "落叶", "孤舟"]
    return words


def _has_allusion_key(word: str) -> bool:
    """占位词里不要出现典故标志词（否则骨架会被 L13 判「金句位用典」）。"""
    return any(key in word for key in ALLUSION_KEY_WORDS)


def _connector(i: int) -> str:
    return CONNECTORS[i % len(CONNECTORS)]


def _tok(ch: str) -> str:
    return f"{ch}:{TONE.get(ch, 0)}"


def make_line(pick, n: int, rhyme_word: str | None, seed: int) -> str:
    """生成 n 字的占位句（保证字数、声调标注、韵脚归辙；不插气口）。"""
    fills = ["又", "空", "正", "半"]
    chars: list[str] = []

    def push_word(w: str) -> None:
        for c in w:
            chars.append(c)

    if rhyme_word:
        body_len = max(1, n - len(rhyme_word))
    else:
        body_len = n

    i = seed
    while len(chars) < body_len:
        need = body_len - len(chars)
        if need >= 2:
            push_word(pick())
        else:
            chars.append(fills[i % len(fills)])
            i += 1
        if len(chars) < body_len:
            chars.append(_connector(i))
            i += 1
    chars = chars[:body_len]
    if rhyme_word:
        chars.extend(rhyme_word)
    chars = chars[:n]
    return " ".join(_tok(c) for c in chars)


def build_skeleton(brief: dict, structure: list[dict], pattern: dict, rhyme: dict) -> str:
    theme = brief["theme"]
    zhe = rhyme["primary"]["zhe"]
    rw_pool = [w for w in RHYME_WORDS[zhe]
               if all(_is_common_char(c) for c in w) and not _has_allusion_key(w)] or RHYME_WORDS[zhe]
    # 占位用词池：按使用次数均衡取词（先挑用得最少的），降低整篇重复率
    pool = _penta_words(theme)
    uses = {w: 0 for w in pool}
    order = 0

    def pick() -> str:
        nonlocal order
        least = min(uses.values())
        cands = [w for w in pool if uses[w] == least]
        w = cands[order % len(cands)]
        order += 1
        uses[w] += 1
        return w

    lines: list[str] = [
        "# 占位骨架：把字换成你的词；字数、韵位、段落名不要动（声调标号 1 阴平/2 阳平/3 上声/4 去声/0 未知）",
        "# 用典配额：全篇 ≤2 处、同段 ≤1 处、副歌首句不用；宁可少用一个典，也要保住一句自造金句",
    ]
    seed = 0
    for sec in structure:
        lines.append(f"[{sec['name']}]")
        chars = section_char_pattern(pattern, sec["kind"])
        rp = set(rhyme_positions(sec["kind"], sec["lines"]))
        for li in range(1, sec["lines"] + 1):
            n = chars[(li - 1) % len(chars)]
            rw = rw_pool[(seed // 2) % len(rw_pool)] if li in rp else None
            lines.append(make_line(pick, n, rw, seed))
            seed += 1
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ================================================================ 参考案例（只给手法）


CASES = [
    {"work": "青花瓷式·器物叙事", "technique": "以一件器物（瓷）为轴，用工艺细节（釉色、纹样、火候）承担时间与情感推进；副歌回到同一器物。",
     "copyable": ["选一件能写工艺的物（瓷/茶/砚/绣/琴），把工序写成时间线", "主歌工笔、副歌写意", "全曲不离开这件物"]},
    {"work": "东风破式·旧地重游", "technique": "倒叙 + 旧地重游：现在的地点 → 回忆 → 回不到的人；用民乐前奏建立年代感。",
     "copyable": ["先写「现在站在哪」", "第二段进回忆，用同一个地点的旧样子做锚", "副歌不推进故事，只重复情绪峰值"]},
    {"work": "千百度式·化用宋词", "technique": "化用宋词句法与意境（不是抄句），把「寻找」分成三层（眼前—回忆—想象），层与层之间用同一个动作串联。",
     "copyable": ["化用只借句式与意象关系，成句必须自己写", "三层寻找各用一个动作", "结尾落到一个具体的空位（空椅/空巷）"]},
    {"work": "兰亭序式·以艺喻情", "technique": "用书法（落笔、藏锋、临帖）比喻感情里的克制与遗憾；术语当动词用。",
     "copyable": ["选一门手艺的术语表", "术语当动词（藏、收、顿、挑）", "副歌把术语还原成人际动作"]},
    {"work": "烟花易冷式·历史留白", "technique": "叙事视角在古今之间切换，用「听说」制造距离感；关键情节永远不写全。",
     "copyable": ["用「听说/有人说」引入传说", "关键事件只写痕迹不写过程", "结尾留一个无法确认的细节"]},
    {"work": "卷珠帘式·戏腔句式", "technique": "长短句 + 三字逗 + 拖腔字，副歌用连续短句堆到长句爆发。",
     "copyable": ["三字逗做钩子（三字一顿）", "副歌第 3 句放长句（7–9 字）", "拖腔字选开口音（言前/江阳）"]},
]


# 用典配额（与 lint L13 同口径）：写进每条典故候选与骨架注释
ALLUSION_QUOTA_TEXT = "配额：全篇 ≤2 处、同段 ≤1 处、副歌首句不用"
# 典故标志词（与 lint ALLUSION_TABLE 的 key 对齐）：占位骨架不能用它们，否则会被 L13 判「金句位用典」
ALLUSION_KEY_WORDS = {
    "阳关", "青衫湿", "湘妃竹", "桃花源", "二十四桥", "乌衣巷", "铜雀", "洛神",
    "望帝", "鼓盆", "精卫", "易水", "牧羊", "卧薪", "闻鸡", "结草", "流火",
    "抱柱", "破镜", "举案", "豆蔻", "弱冠", "及笄", "而立", "不惑", "耳顺",
    "古稀", "耄耋", "弄瓦", "弄璋", "萧墙", "不刊", "梦蝶", "鲛人", "纸贵",
    "投笔", "空穴来风", "瓜田李下", "高山流水", "青梅竹马", "望穿秋水",
    "知天命", "目无全牛", "危言危行", "差强人意", "首当其冲", "炙手可热",
    "万人空巷", "美轮美奂", "明日黄花", "三人成虎", "望洋兴叹", "文不加点",
    "春风得意", "走马观花", "狗尾续貂", "一鼓作气", "人尽可夫",
}

GLOBAL_PITFALLS = [
    "典故拼贴：一句一个典 = 没有自己的话；宁可少用一个典，也要保住一句自造金句"
    "（lint L13/L14 会报：全篇 >3 处 error、同段 ≥2 处 warn、同典重复 error、金句位用典 warn）。",
    "三件套堆砌：殇、琉璃、浮生当形容词用，没有一个可触物象支撑 → 换成能看见的物件。",
    "副歌全是抽象情绪：没有具体物象，听众记不住 → 金句里至少一个能看见的物件（L14 会查「自造金句」）。",
    "典故当装饰：不知出处就往上放 → 先查「原意」，只放在叙事接得住的位置（lint L7 会报疑似误用）。",
    "句句押韵：韵脚密度过高，副歌反而失重 → 主歌偶句押，副歌 1/2/4 句押。",
    "时空混用：古代场景放进现代词（手机/外卖/朋友圈）→ lint L6 会报；若刻意反差，先确认叙事成立。",
]


def pitfalls_for(theme: str) -> list[str]:
    out = list(THEMES[theme]["pitfalls"])
    out.extend(GLOBAL_PITFALLS[: max(1, 5 - len(out))])
    return out[:5]


# ================================================================ 组装


def build_blueprint(raw: dict) -> tuple[dict, list[str]]:
    brief, notes = build_brief(raw)
    theme = brief["theme"]
    structure = plan_structure(brief["duration_lines"])
    patterns = pick_patterns(brief)
    pattern = PATTERNS[brief["pattern_id"]]
    rhyme = recommend_rhyme(theme, brief["rhyme_forced"], pattern)
    images = pick_images(theme)
    allusions = pick_allusions(theme)
    card = plan_card(brief, structure, pattern, rhyme)
    hooks = hook_plan(card)
    skeleton = build_skeleton(brief, structure, pattern, rhyme)

    bp = {
        "meta": {"skill": SKILL, "version": VERSION,
                 "generated": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "script": "lyric_blueprint.py",
                 "note": "输入 JSON 的全可选字段见脚本 docstring；未知字段已忽略。"},
        "brief": brief,
        "input": raw if isinstance(raw, dict) else {},
        "notes": notes,
        "rhyme_plan": rhyme,
        "patterns": patterns,
        "image_packs": images,
        "allusions": allusions,
        "structure_card": card,
        "hook_plan": hooks,
        "cases": CASES,
        "pitfalls": pitfalls_for(theme),
        "lyr_skeleton": skeleton,
        "allusion_quota": ALLUSION_QUOTA_TEXT,
        "next": [
            "按「结构卡」把每句字数定下来（或先跑 jianpu2lyricslots.py 拿作曲端的槽位）。",
            "把 .lyr 骨架里的占位字换成你的词：韵脚位置别动，字数按卡走。",
            "跑 lint：`python scripts/lint_guofeng_lyric.py --input 你的.lyr`，error 清零。",
            "要成曲：`python scripts/lyric2jianpu.py --input 你的.lyr --key D --mode yu --out 你的.jp`，"
            "再用作曲技能 `jianpu2midi.py` 导 MIDI。",
        ],
    }
    return bp, notes


def build_markdown(bp: dict) -> str:
    brief = bp["brief"]
    theme = brief["theme"]
    rhyme = bp["rhyme_plan"]
    card = bp["structure_card"]
    pattern = next(p for p in bp["patterns"] if p["id"] == brief["pattern_id"])
    L: list[str] = []
    L.append(f"# 中国风作词蓝图 · {theme} · {STYLES[brief['style']]['name']}")
    L.append("")
    L.append(f"> 由 `lyric_blueprint.py` v{VERSION} 生成于 {bp['meta']['generated']}；"
             "照这份蓝图写词，再用 `lint_guofeng_lyric.py` 卡门禁。")
    L.append("")

    L.append("## 一、需求解读")
    L.append("")
    L.append("| 项目 | 取值 | 对写作的影响 |")
    L.append("|---|---|---|")
    L.append(f"| 题材 | {theme} | {brief['theme_core']} |")
    L.append(f"| 风格 | {STYLES[brief['style']]['name']}（`{brief['style_id']}`） | "
             f"{STYLES[brief['style']]['words']} |")
    L.append(f"| 情绪 | {brief['mood'] or '（未填：按题材默认情绪）'} | 决定用词密度与留白 |")
    L.append(f"| 人声 | {brief['voice']} | {'旋律可放中低音区，副歌八度不飙升' if brief['voice'] == '男声' else '副歌可上探，尾音多拖长' if brief['voice'] == '女声' else '副歌可写和声与轮唱句'} |")
    L.append(f"| 视角 | {brief['perspective']}人称 | {'写「我」的动作与物证' if brief['perspective'] == '第一' else '写「你」的动作，我隐在背后' if brief['perspective'] == '第二' else '只写画面与人物，不表态'} |")
    L.append(f"| 目标句数 | {brief['duration_lines']} 句（实际排 {card['total_lines']} 句） | 决定段落是否加桥段 |")
    L.append(f"| 韵辙 | {'【指定】' if brief['rhyme_forced'] else '自动推荐 '}{rhyme['primary']['zhe']} | "
             f"全词一辙，同段内换辙会被 lint 报 L1 |")
    if brief["style_hint"]:
        L.append(f"| 额外提示 | {brief['style_hint']} | 选词时优先满足 |")
    L.append("")
    if bp["notes"]:
        L.append("输入解析提示：")
        L.append("")
        for n in bp["notes"]:
            L.append(f"- {n}")
        L.append("")

    L.append("## 二、韵辙推荐（1 主 2 备）")
    L.append("")
    L.append("| 顺位 | 辙口 | 代表韵母 | 色彩 | 为什么选它 |")
    L.append("|---|---|---|---|---|")
    p = rhyme["primary"]
    L.append(f"| 主 | **{p['zhe']}** | {p['mu']} | {p['color']} | {p['why']} |")
    for i, b in enumerate(rhyme["backups"], 1):
        L.append(f"| 备 {i} | {b['zhe']} | {b['mu']} | {b['color']} | {b['why']} |")
    L.append("")
    L.append(f"韵脚密度：{rhyme['rhyme_density']}")
    L.append("")
    L.append(f"押韵说明：{rhyme['note']}")
    L.append("")
    L.append(f"本辙可用韵脚词（直接抄）：{'、'.join(RHYME_WORDS[p['zhe']])}")
    L.append("")

    L.append("## 三、词牌 / 句式候选（3 套）")
    L.append("")
    for i, pt in enumerate(bp["patterns"], 1):
        L.append(f"### {i}. {pt['name']}（`{pt['id']}`）{pt['fit_note']}")
        L.append("")
        L.append(f"- 句式模板：{pt['layout']}")
        L.append(f"- 每句字数：主歌 {pt['verse']} / 预副歌 {pt['pre']} / 副歌 {pt['chorus']} / "
                 f"桥 {pt['bridge']} / 尾 {pt['outro']}")
        L.append(f"- 韵位：{pt['rhyme_note']}")
        ci = pt["ci_hint"]
        L.append(f"- 可对照词牌：**{ci['name']}**（{ci['chars']} 字，句式 {ci['layout']}）——{ci['note']}")
        L.append(f"- 为什么：{pt['why']}")
        L.append("")
    L.append("> 三套任选一套，全词不要混用；混句式会让句长校验（L2）反复报错。")
    L.append("")

    L.append("## 四、意象包（3 组，每组 6–8 个物象）")
    L.append("")
    for pk in bp["image_packs"]:
        L.append(f"### 组 {pk['index']}：{pk['name']}（{pk['count']} 个）")
        L.append("")
        L.append("| 物象 | 情感/功能 |")
        L.append("|---|---|")
        for it in pk["items"]:
            L.append(f"| {it} | 同一组内只取 1–2 个，避免并列堆叠 |")
        L.append("")
        L.append(f"用法：{pk['usage']}")
        L.append("")
    L.append("意象搭配铁律：一象一情；同一句最多两个物象；物象之间要有空间关系（在窗上、在船头、在檐下）。")
    L.append("")

    L.append("## 五、典故候选（含出处与一句示范）")
    L.append("")
    L.append("| # | 典故 | 出处 | 原意 | 一句示范（自写，可直接改） |")
    L.append("|---|---|---|---|---|")
    for i, a in enumerate(bp["allusions"], 1):
        L.append(f"| {i} | {a['name']} | {a['source']} | {a['meaning']} | {a['sample']} |")
    L.append("")
    for a in bp["allusions"]:
        L.append(f"- **{a['name']}**：{a['quota']}；{a['tip']}")
    L.append("")
    L.append("用法与禁忌：")
    L.append("")
    for a in bp["allusions"]:
        L.append(f"- **{a['name']}**（出处 {a['source']}）：{a['tip']}")
    L.append("")
    L.append("> 用典原则：**全篇 ≤2 处、同段 ≤1 处、副歌首句不用、同一典故不重复**；典故必须服务叙事，"
             "不知原意宁可不写（lint L7 报疑似误用、L13 报密度/堆砌、L14 报缺核心与缺自造金句）。"
             "判断口诀：删掉这个典，这句话还成立吗？成立就删。")
    L.append("")

    L.append("## 六、结构卡")
    L.append("")
    L.append(f"- 总句数：{card['total_lines']} 句；总字数：{card['total_chars_range']}")
    L.append(f"- 主韵：{card['rhyme']}；韵位规则：{pattern['rhyme_note']}")
    L.append("")
    L.append("| 段落 | 句数 | 每句字数 | 字数区间 | 韵位 | 段落任务 | 金句位 |")
    L.append("|---|---|---|---|---|---|---|")
    for r in card["sections"]:
        L.append(f"| {r['name']} | {r['lines']} | {'、'.join(str(x) for x in r['chars_per_line'])} | "
                 f"{r['char_range']} | {r['rhyme_lines_text']} | {r['function']} | "
                 f"{'★ 是' if r['hook'] else '—'} |")
    L.append("")
    L.append(card["note"])
    L.append("")

    L.append("## 七、金句位")
    L.append("")
    L.append(f"- 位置：{'、'.join(bp['hook_plan']['positions'])}")
    L.append(f"- 要求：{bp['hook_plan']['requirement']}")
    L.append("")
    for e in bp["hook_plan"]["examples"]:
        L.append(f"- {e}")
    L.append("")
    L.append(f"- 自检：{bp['hook_plan']['check']}")
    L.append("")

    L.append("## 八、参考案例（只给手法，不抄词）")
    L.append("")
    L.append("| 案例 | 手法 | 可抄的操作 |")
    L.append("|---|---|---|")
    for c in bp["cases"]:
        L.append(f"| {c['work']} | {c['technique']} | {'；'.join(c['copyable'])} |")
    L.append("")
    L.append("> 案例只拆结构与手法；引用原作连续不超过 8 字，且仅用于分析。")
    L.append("")

    L.append("## 九、避坑（5 条）")
    L.append("")
    for i, p_ in enumerate(bp["pitfalls"], 1):
        L.append(f"{i}. {p_}")
    L.append("")

    L.append("## 十、可直接复制的 .lyr 骨架")
    L.append("")
    L.append("> 骨架里的字是**占位**：字数、句长、韵位、声调标注（`字:调`）都已算好，把字换成你的词即可。"
             "`1` 阴平 `2` 阳平 `3` 上声 `4` 去声 `0` 未知；`[...]` 是段落名。"
             "占位句默认不插气口（`|`），需要时自己加。"
             "**用典配额：全篇 ≤2 处、同段 ≤1 处、副歌首句不用；同一典故不重复。**"
             "这份骨架已用 `lint_guofeng_lyric.py` 实测：10 个题材均 **0 error / 0 warn**（只剩少量 info），"
             "换字后若出现 L4 重复或 L8 生僻，是内容问题，按报告「修法」改即可。")
    L.append("")
    L.append("```")
    L.append(bp["lyr_skeleton"].rstrip("\n"))
    L.append("```")
    L.append("")

    L.append("## 十一、下一步")
    L.append("")
    for i, cmd in enumerate(bp["next"], 1):
        L.append(f"{i}. {cmd}")
    L.append("")
    return "\n".join(L)


# ================================================================ CLI


def _demo_out_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "guofeng-lyric-out"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = SCRIPT_DIR
    return d


def resolve_outputs(out_arg: str | None, input_path: Path | None) -> tuple[Path, Path]:
    if out_arg:
        p = Path(out_arg).expanduser()
        if p.suffix.lower() in (".json", ".md"):
            base = p.with_suffix("")
        elif p.is_dir():
            base = p / "作词蓝图"
        else:
            base = p
        return Path(str(base) + ".blueprint.json"), Path(str(base) + ".blueprint.md")
    if input_path is not None:
        return (input_path.with_name(input_path.stem + ".blueprint.json"),
                input_path.with_name(input_path.stem + ".blueprint.md"))
    d = _demo_out_dir()
    return d / "作词蓝图-demo.blueprint.json", d / "作词蓝图-demo.blueprint.md"


def read_input_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise
    except UnicodeDecodeError:
        raw = path.read_text(encoding="gbk", errors="replace")
    data = json.loads(raw) if raw.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("输入 JSON 顶层必须是对象（例如 {}）")
    return data


DEFAULT_DEMO_INPUT = {
    "theme": "相思",
    "style": "抒情",
    "mood": "雨夜、旧巷、哀而不伤",
    "voice": "女",
    "perspective": "第一",
    "duration_lines": 22,
}


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="lyric_blueprint.py",
        description="中国风作词蓝图：需求 → 韵辙 + 句式 + 意象 + 典故 + 结构卡 + .lyr 骨架。纯标准库。",
        epilog=("示例：\n"
                "  python lyric_blueprint.py                     # demo → <临时目录>/guofeng-lyric-out/\n"
                "  python lyric_blueprint.py --input 需求.json   # → 同目录/需求.blueprint.{json,md}\n"
                "  python lyric_blueprint.py --input 需求.json --out 蓝图/江南雨\n"
                "输入最小可写 {}（全用默认值）；theme/style/mood/voice/perspective/duration_lines/rhyme 均可选。"),
    )
    parser.add_argument("--input", help="输入需求 JSON（可省略 = 内置 demo）")
    parser.add_argument("--out", help="输出前缀或目录（默认见上）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 需求生成蓝图")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    json_path, md_path = resolve_outputs(args.out, input_path)

    try:
        if input_path is not None:
            if not input_path.exists():
                print(f"❌ 找不到输入文件：{input_path}", file=sys.stderr)
                print("下一步：确认路径；或直接跑 `python lyric_blueprint.py` 看内置 demo。", file=sys.stderr)
                return 2
            raw = read_input_json(input_path)
            source = str(input_path)
        else:
            raw = dict(DEFAULT_DEMO_INPUT)
            source = "内置 demo（相思·抒情·女声·22 句）"

        bp, notes = build_blueprint(raw)
        md = build_markdown(bp)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(bp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")

        card = bp["structure_card"]
        print("")
        print("=" * 62)
        print(f"📝 作词蓝图已生成：{bp['brief']['theme']} · {STYLES[bp['brief']['style']]['name']}")
        print(f"   来源：{source}")
        print(f"   主韵：{bp['rhyme_plan']['primary']['zhe']}（备 {', '.join(b['zhe'] for b in bp['rhyme_plan']['backups'])}）")
        print(f"   句式：{next(p['name'] for p in bp['patterns'] if p['id'] == bp['brief']['pattern_id'])}")
        print(f"   结构：{card['total_lines']} 句 / {len(card['sections'])} 段 / {card['total_chars_range']}")
        print(f"   意象：3 组共 {sum(p['count'] for p in bp['image_packs'])} 个物象；典故 {len(bp['allusions'])} 条")
        print(f"   JSON：{json_path}")
        print(f"   Markdown：{md_path}")
        print("=" * 62)
        print("下一步：按 Markdown 第十节复制 .lyr 骨架 → 换字 → 跑 lint_guofeng_lyric.py 卡门禁。")
        return 0
    except json.JSONDecodeError as exc:
        print(f"❌ 输入 JSON 解析失败：{exc}", file=sys.stderr)
        print("下一步：① 检查逗号/引号是否为英文半角；② 用 `python -c \"import json;json.load(open('文件','r',encoding='utf-8'))\"` 定位；"
              "③ 也可以直接跑不带 --input 的 demo。", file=sys.stderr)
        return 2
    except Exception as exc:  # 任何输入都不抛 traceback
        print(f"❌ 生成蓝图失败：{exc}", file=sys.stderr)
        print("下一步：① 先跑 `python lyric_blueprint.py` 确认脚本本身正常；② 把需求 JSON 精简到 {} 再试；"
              "③ 仍失败请把这段报错原文发给开发者。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
