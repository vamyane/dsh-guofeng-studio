#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_guofeng_lyric.py —— 中国风歌词校验（L1–L14）+ 门禁清单

纯标准库实现。解析 .lyr（PLAN-LYRIC §4.2），输出 Markdown 报告：
每条发现含「级别 / 位置 / 规则 / 说明 / 修法」，末尾给 14 条门禁清单与结论行。

规则：L1 押韵 / L2 句长 / L3 倒字 / L4 重复 / L5 伪古风 / L6 时空 /
      L7 典故正误 / L8 生僻字 / L9 结构 / L10 AI 味 / L11 金句 /
      L12 断韵 / L13 用典密度与堆砌 / L14 核心表达。

用法：
  python lint_guofeng_lyric.py
        无参数 = 内置 demo 词，报告写到系统临时目录 guofeng-lyric-out/lint-guofeng-lyric.md
  python lint_guofeng_lyric.py --demo
        同上（显式 demo）
  python lint_guofeng_lyric.py --input 我的词.lyr
        报告写到 同目录/我的词-校验.md
  python lint_guofeng_lyric.py --input 我的词.lyr --report 校验.md
  python lint_guofeng_lyric.py --input 我的词.lyr --slots 江南雨.slots.json
        按填词槽位的 syllables ±2 校验句长（L2）
  python lint_guofeng_lyric.py --input 我的词.lyr --jp 江南雨.jp
        把歌词与旋律对齐，按四声走向查句尾/重音字倒字（L3）
  python lint_guofeng_lyric.py --allow-change-rhyme --allow-modern
        允许跨段转韵（同段换辙仍报 error）；允许现代词（降为 info）
  python lint_guofeng_lyric.py --help

.lyr 格式：
  [段落名]                 一行一段
  江:1 南:2 雨:3 | 落:4   字:调（1 阴平 2 阳平 3 上声 4 去声 0 未知/轻声）
  | 为句内气口；# 开头为注释；标点会被忽略（不计字数）

退出码：0 = 无 error（可交付）；1 = 有 error（需修改）；2 = 参数/文件层面无法继续。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # 不依赖 cwd

VERSION = "1.0.1"

# ================================================================ 十三辙

ZHE_INFO: dict[str, str] = {
    "发花": "a / ia / ua",
    "梭波": "o / e / uo",
    "乜斜": "ie / üe",
    "一七": "i / ü / -i",
    "姑苏": "u",
    "怀来": "ai / uai",
    "灰堆": "ei / ui",
    "遥条": "ao / iao",
    "油求": "ou / iu",
    "言前": "an / ian / uan / üan",
    "人辰": "en / in / un / ün",
    "江阳": "ang / iang / uang",
    "中东": "eng / ing / ong / iong",
}

# 每辙常用字表（收字原则：歌词韵脚高频字；多音字按常见读音可入多辙）
ZHE_CHARS_RAW: dict[str, str] = {
    "发花": "花华家加佳嘉霞瑕涯崖牙芽茶麻马打大他她它呀啊把爸怕爬瓜挂卦夸跨瓦娃蛙洼话画化下夏吓亚雅鸦沙纱叉差傻撒洒拔八巴疤搭答达发法罚乏伐拉啦妈骂拿那纳掐卡刷耍抓爪袜",
    "梭波": "歌河何荷和合盒喝渴科棵颗可客刻个各饿鹅蛾恶乐勒色特则泽得德的若弱多拖脱夺托罗锣洛落锁索错措火货活或获波玻播泊薄坡婆破摸磨魔抹末莫漠我卧握涡窝左坐座做昨佐说硕着桌捉过国果裹锅郭阔扩括惑霍勺呵热惹渴",
    "乜斜": "月雪别灭蝶叠结节接解界借谢写斜些且切窃铁贴页叶夜也野爷业杰捷洁诀绝决缺却雀鹊血学约跃越悦阅靴姐撇蔑瞥蹩碟谍迭跌爹猎烈裂列劣掠略虐薛削懈械泄泻卸蟹谐携鞋邪胁协挟冶掖椰噎谒",
    "一七": "衣依移疑遗意忆已以倚椅里理离力立丽利李梨栗你泥呢西溪喜洗细席昔息七期起其奇骑气去曲取娶女雨语玉与予余鱼渔须需许序绪时诗事是十世石只知之至纸子字自次词此思丝似死四市视试日记计寄极及急集迹机几己季迷米蜜笔比必毕皮疲匹低底地第弟题提替体梯尼腻漓璃篱犁黎礼鲤历厉励例隶姬基鸡积激饥肌绩击即疾嫉籍挤纪技既继祭寂系细居局举句巨拒距具剧据聚趣区驱屈趋渠旅律绿虑滤驴吕屡缕愚娱宇羽育域遇寓誉预欲愈芋吁迂淤榆逾愉瑜舆痴迟持池翅齿耻尺炽匙",
    "姑苏": "无五午舞武屋物雾露路陆树数书输疏湖户护呼虎苦哭骨古故孤姑渡度独读都图途土吐兔步不布补母木目牧暮慕墓幕富父付复福服处出除初楚住主竹助祝入如儒粗组租祖速素诉苏酥怒奴突秃徒涂屠努忽狐胡糊壶蝴互沪库裤枯辜咕估鼓固顾雇殊舒蔬属鼠竖述术束阻醋促卒族足",
    "怀来": "来爱哀白百拜采彩才猜台太抬代待带孩海害开凯卖买埋奶拍排牌塞赛晒外歪快块淮怀坏帅甩衰拽揣乖怪拐裁材财菜蔡踩睬戴贷怠该改盖概钙骸骇咳慨赖莱迈麦脉奈耐乃派湃态汰摘窄债宅斋寨载在再灾栽宰摆败牌",
    "灰堆": "泪雷累谁水睡岁随碎醉最追归鬼贵回会灰挥飞非肥美妹眉每背北被悲杯备黑给内陪配委未味位微唯维违围威推退腿对队吹垂锤催遂虽税瑞罪媒煤莓霉玫梅魅寐媚髓穗巍危韦伟纬尾慰蔚谓渭喂胃魏卫为惟帷蕊锐睿堆兑脆翠崔摧萃嘴隧",
    "遥条": "了老好高告到道刀岛倒朝潮抄超草曹烧少小笑霄宵晓潇萧箫桥翘巧敲樵蕉焦娇交叫教角飘漂票苗描庙妙鸟尿挑条跳遥摇药要腰邀妖桃逃陶涛抱报保宝造早枣招昭找照兆号豪毫浩皓劳牢唠涝猫毛矛冒帽贸脑恼闹抛跑泡炮瓢绕扰扫嫂哨稍绍韶滔淘讨套肖消销孝效校嚣瑶谣咬舀耀糟遭灶皂燥噪躁嘲巢吵炒罩掉调吊雕叼钓疗聊料撩燎缭辽",
    "油求": "秋求球酒九久旧救就愁稠收手首守受瘦头投偷透楼漏流柳留六舟州洲周后厚候猴走奏狗够沟勾扣口否有又右友幼忧幽悠游由邮油犹秀绣袖修羞休丢斗豆兜抽臭丑仇柔肉欧偶呕藕剖谋某搜艘嗽搂篓陋邹揍凑侯喉吼揪玖舅咎丘囚泅邱谬扭纽牛朽嗅优尤佑诱柚釉",
    "言前": "山三天年前边变面见间关还寒烟雁燕掩眼沿言颜岸安暗案半伴班般搬万晚弯湾玩完挽干甘敢感看刊堪含汉汗谈弹叹滩南难男蓝栏兰懒澜乱船川穿传转换欢缓环团暖断短段端酸算蒜圆远愿元园原源缘冤卷倦现先线县献险显鲜闲咸贤弦嫌陷限仙掀丸顽碗宛婉惋腕专砖赚撰锻缎卵峦恋联连莲怜廉帘脸练炼链篇偏便片骗遍棉免眠绵勉缅点店电垫殿淀奠甜田填添舔拈念碾辇尖肩坚奸监兼煎拣减检简件建剑健渐箭践键溅荐牵千迁签谦钱前潜浅遣欠嵌歉潜羡宪眠边檐严岩炎延研盐艳验宴慢珊删衫扇闪陕善膳擅赡禅蝉婵缠颤沾粘展斩盏栈占战站绽湛染冉然燃赞暂咱攒簪",
    "人辰": "云春人心深身神晨尘沉陈真珍针枕阵门们问闻分份纷焚根跟肯痕很恨恩温稳魂昏婚孙损存寸村尊遵群裙军均俊君熏训寻旬巡迅信新欣音因阴银引印宾滨贫品拼民敏临林淋邻尽进近亲侵寝秦琴勤今金津筋襟仅紧锦劲禁沁芯辛薪讯逊纯唇蠢醇蹲顿盾钝遁敦墩氛坟粉奋愤粪跟狠混荤浑钧菌峻竣骏郡匀允陨孕运晕韵蕴酝瘟纹蚊吻紊樽忖笋隼准谆蠢鹑顺瞬舜吮伦轮沦论纶抡仑滚棍昆坤困捆阍馄文",
    "江阳": "光江长场唱常尝裳厂昌窗床创霜双爽黄皇荒慌晃望忘王往网航方房芳放防坊舫香乡相想向湘箱厢象像良凉亮量两梁粮浪朗狼郎塘堂唐糖趟广逛阳扬杨洋羊养样娘酿枪墙强抢妆装庄壮状伤商上尚赏张章掌涨藏苍舱帮绑榜棒傍磅膀仓沧偿敞畅倡肠嫦疮闯挡党荡档妨仿访纺刚钢岗港杠恍谎煌惶蝗凰姜将浆疆讲奖桨匠降康糠抗扛亢廊琅榔忙芒盲茫莽旁庞乓胖腔蔷让壤嚷桑丧嗓汪亡妄橡央殃秧仰恙脏葬丈仗帐账障幢响享项巷",
    "中东": "风中空红洪东冬钟终从松送梦灯等城成程声生胜明鸣名命星行形影应英迎营京经精惊井景静情请清轻倾听停庭亭令铃零冷更耕曾层增逢缝丰峰锋封蜂同铜童洞动通痛龙笼弄宫工公功共弓穷兄胸雄永用涌容荣融崇虫冲重众孔控冰兵丙病并平评瓶屏凭丁顶定订厅挺宁凝灵岭领另兴幸性姓硬鹰婴樱盈蝇赢铭敬竟境镜净颈晴卿醒省盛圣升绳承乘诚澄撑称扔赠憎僧恒横衡哼棱愣坑吭盟蒙萌猛孟争征挣睁筝政证症整忠种充宠懂冻栋桐瞳筒桶浓脓隆咙垄拢攻恭躬巩贡供恐凶熊穹琼溶绒茸蓉",
}


def _build_zhe_map() -> dict[str, set[str]]:
    m: dict[str, set[str]] = {}
    for zhe, chars in ZHE_CHARS_RAW.items():
        for ch in chars:
            m.setdefault(ch, set()).add(zhe)
    return m


ZHE_CHARS = _build_zhe_map()


# ================================================================ 伪古风词库（L5，≥20）

PSEUDO_GUFENG = [
    "殇", "琉璃", "浮生", "红颜", "白衣", "青衫", "执念", "流年", "岁月",
    "浅笑", "缱绻", "葳蕤", "翩跹", "陌上", "天涯", "海角", "红尘", "清欢",
    "宿命", "离殇", "绝恋", "薄凉", "烟火", "未央", "斑驳", "倾尽天下", "盛世",
    "荒芜", "雪月", "风华", "指尖", "三生", "执手", "千年", "忘川", "孟婆",
    "断肠", "生死相许", "浮华", "红妆", "霓裳", "金戈", "寂灭", "孤城",
]  # 44 个

# ================================================================ 现代词黑名单（L6，≥30）

MODERN_WORDS = [
    "手机", "微信", "朋友圈", "红包", "高铁", "地铁", "外卖", "奶茶", "咖啡",
    "酒吧", "视频", "直播", "点赞", "网红", "流量", "快递", "打车", "导航",
    "空调", "冰箱", "沙发", "电梯", "超市", "便利店", "加班", "打卡", "共享单车",
    "密码", "下载", "上线", "更新", "耳机", "自拍", "刷屏", "网购", "二维码",
    "小程序", "支付", "会员", "弹幕", "面试", "简历", "上班", "下班", "工资",
    "房贷", "社保", "微博", "抖音", "表情包", "聊天记录", "WiFi", "电脑", "键盘",
]  # 54 个

# ================================================================ 典故正误表（L7，≥40）

# 字段：name 典故名 / source 出处 / key 触发词 / wrong 误用信号词 / right 正解 / fix 修法
ALLUSION_TABLE: list[dict] = [
    {"name": "七月流火", "source": "《诗经·豳风·七月》", "key": "流火",
     "wrong": ["炎热", "酷暑", "暑气", "天热", "盛夏", "烈阳", "热浪"],
     "right": "大火星向西下沉，指天气转凉", "fix": "写炎夏改用「暑气/伏天」；按原意写秋凉才用「流火」"},
    {"name": "尾生抱柱", "source": "《庄子·盗跖》", "key": "抱柱",
     "wrong": ["背信", "失约", "爽约", "负心", "骗我"],
     "right": "守信至死（痴守）", "fix": "写「背约」另找词；用「抱柱」必须落在等待与守信上"},
    {"name": "人尽可夫", "source": "《左传·桓公十五年》", "key": "人尽可夫",
     "wrong": ["放荡", "随便", "不检点", "水性"],
     "right": "「丈夫可人人做」——原指亲情重于夫妻，非贬女子",
     "fix": "贬义场景删掉此语；这是典型误用，lint 会拦"},
    {"name": "空穴来风", "source": "宋玉《风赋》", "key": "空穴来风",
     "wrong": ["毫无根据", "纯属造谣", "无中生有"],
     "right": "有洞穴才进风——事出有因", "fix": "要表达「毫无根据」用「无稽之谈」"},
    {"name": "瓜田李下", "source": "《乐府诗集·君子行》", "key": "瓜田李下",
     "wrong": ["田园", "瓜果", "乡下", "种地"],
     "right": "避嫌疑的处境", "fix": "写田园风光别用此典；要写避嫌才用"},
    {"name": "高山流水", "source": "《列子·汤问》（亦见《吕氏春秋·本味》）", "key": "高山流水",
     "wrong": ["风景", "游玩", "山水画", "游山玩水"],
     "right": "伯牙子期知音难遇", "fix": "写风景用「青山绿水」；此典只写「懂」"},
    {"name": "破镜重圆", "source": "唐·孟棨《本事诗·情感》", "key": "破镜",
     "wrong": ["镜子碎了", "残破", "破碎", "旧镜"],
     "right": "夫妻离散后重逢", "fix": "只写器物破损别用此典；要写重逢才用"},
    {"name": "举案齐眉", "source": "《后汉书·梁鸿传》", "key": "举案",
     "wrong": ["举着桌子", "案发现场", "书案"],
     "right": "夫妻相敬如宾", "fix": "此典专指夫妻相敬；写别人用「敬重」"},
    {"name": "青梅竹马", "source": "李白《长干行》", "key": "青梅竹马",
     "wrong": ["水果", "竹林", "梅子"],
     "right": "童年相伴的男女", "fix": "写梅子/竹林别连用四字；要写童年伴侣才用"},
    {"name": "望穿秋水", "source": "王实甫《西厢记》", "key": "望穿秋水",
     "wrong": ["秋天", "江水", "看水", "秋水"],
     "right": "盼望至极（眼都望穿）", "fix": "写秋景别用；要写盼望才用"},
    {"name": "豆蔻年华", "source": "杜牧《赠别》", "key": "豆蔻",
     "wrong": ["中年", "男子", "少年郎", "老人"],
     "right": "十三四岁少女", "fix": "写男子用「少年」；年龄不符会闹笑话"},
    {"name": "弱冠之年", "source": "《礼记·曲礼上》", "key": "弱冠",
     "wrong": ["女子", "少女", "十岁", "少年十"],
     "right": "男子二十岁", "fix": "女子二十用「桃李年华」；男子二十才用弱冠"},
    {"name": "及笄之年", "source": "《礼记·内则》", "key": "及笄",
     "wrong": ["男子", "少年", "二十"],
     "right": "女子十五岁（束发插簪）", "fix": "男子十五用「束发」；女子十五才用及笄"},
    {"name": "而立之年", "source": "《论语·为政》", "key": "而立",
     "wrong": ["四十", "二十", "五十"],
     "right": "三十岁", "fix": "四十用「不惑」，别混"},
    {"name": "不惑之年", "source": "《论语·为政》", "key": "不惑",
     "wrong": ["三十", "五十", "二十"],
     "right": "四十岁", "fix": "三十用「而立」，别混"},
    {"name": "知天命", "source": "《论语·为政》", "key": "知天命",
     "wrong": ["四十", "六十", "三十"],
     "right": "五十岁", "fix": "六十用「耳顺」"},
    {"name": "耳顺", "source": "《论语·为政》", "key": "耳顺",
     "wrong": ["七十", "五十", "四十"],
     "right": "六十岁", "fix": "七十用「古稀」"},
    {"name": "古稀", "source": "杜甫《曲江》", "key": "古稀",
     "wrong": ["六十", "八十", "五十"],
     "right": "七十岁", "fix": "八九十用「耄耋」"},
    {"name": "耄耋", "source": "《礼记·曲礼上》", "key": "耄耋",
     "wrong": ["三十", "少年", "四十"],
     "right": "八九十岁高龄", "fix": "年轻别用；写高龄才用"},
    {"name": "弄瓦之喜", "source": "《诗经·小雅·斯干》", "key": "弄瓦",
     "wrong": ["生男孩", "男孩", "儿子"],
     "right": "生女孩", "fix": "生男用「弄璋」"},
    {"name": "弄璋之喜", "source": "《诗经·小雅·斯干》", "key": "弄璋",
     "wrong": ["生女孩", "女孩", "女儿"],
     "right": "生男孩", "fix": "生女用「弄瓦」"},
    {"name": "祸起萧墙", "source": "《论语·季氏》", "key": "萧墙",
     "wrong": ["城墙", "篱笆", "院墙", "城门"],
     "right": "祸患起于内部", "fix": "写建筑别用；要写内乱才用"},
    {"name": "目无全牛", "source": "《庄子·养生主》", "key": "目无全牛",
     "wrong": ["粗心", "看不见牛", "眼里没牛"],
     "right": "技艺纯熟到不见整牛", "fix": "褒义；别当贬义词用"},
    {"name": "危言危行", "source": "《论语·宪问》", "key": "危言危行",
     "wrong": ["危险的言论", "危险行为", "冒险"],
     "right": "说正直的话、做正直的事（危＝正）", "fix": "要写冒险用「铤而走险」"},
    {"name": "差强人意", "source": "《后汉书·吴汉传》", "key": "差强人意",
     "wrong": ["不满意", "很差", "勉强", "失望"],
     "right": "大体还能让人满意", "fix": "要表达不满意用「不尽如人意」"},
    {"name": "首当其冲", "source": "《汉书·五行志》", "key": "首当其冲",
     "wrong": ["首先", "第一名", "带头", "第一个"],
     "right": "最先受到冲击", "fix": "要写「首先」用「首屈一指/率先」"},
    {"name": "炙手可热", "source": "杜甫《丽人行》", "key": "炙手可热",
     "wrong": ["热门", "抢手", "受欢迎", "火爆"],
     "right": "权势极盛（含贬义）", "fix": "要写流行用「风靡一时」"},
    {"name": "万人空巷", "source": "苏轼《八月十七日复登望海楼》", "key": "万人空巷",
     "wrong": ["没人", "冷清", "空房子", "空无一人"],
     "right": "家家出来看，街巷空无一人（形容轰动）", "fix": "写冷清别用；这是「热闹」的典"},
    {"name": "不刊之论", "source": "扬雄《答刘歆书》", "key": "不刊",
     "wrong": ["不能刊登", "不能发表", "禁书"],
     "right": "不可改动的定论（刊＝削改）", "fix": "写「不能发表」另找词"},
    {"name": "美轮美奂", "source": "《礼记·檀弓下》", "key": "美轮美奂",
     "wrong": ["美女", "美景", "美不胜收", "好看的人"],
     "right": "建筑高大华美", "fix": "形容人/景用「美不胜收」「明艳」"},
    {"name": "明日黄花", "source": "苏轼《九日次韵王巩》", "key": "明日黄花",
     "wrong": ["未来", "希望", "明天", "前程"],
     "right": "过时之物", "fix": "写未来用「明日之星」；此典是「过时」"},
    {"name": "三人成虎", "source": "《战国策·魏策二》", "key": "三人成虎",
     "wrong": ["三个人", "力量大", "团结", "人多"],
     "right": "谣言重复多了就被当真", "fix": "写团结用「众志成城」"},
    {"name": "望洋兴叹", "source": "《庄子·秋水》", "key": "望洋兴叹",
     "wrong": ["看海", "海洋", "望着海", "海景"],
     "right": "面对宏大而自叹渺小/无能为力", "fix": "写看海别连用；要写无能为力才用"},
    {"name": "文不加点", "source": "《后汉书·祢衡传》", "key": "文不加点",
     "wrong": ["不加标点", "没标点", "标点"],
     "right": "写文章一气呵成无需修改（点＝涂改）", "fix": "写标点问题别用此典"},
    {"name": "春风得意", "source": "孟郊《登科后》", "key": "春风得意",
     "wrong": ["天气好", "春风", "春天来了"],
     "right": "科举及第/心愿达成的畅快", "fix": "写天气别用；要写得意才用"},
    {"name": "走马观花", "source": "孟郊《登科后》", "key": "走马观花",
     "wrong": ["骑马", "赏花", "看花", "游春"],
     "right": "粗略地看（贬义）", "fix": "写赏花用「踏青赏花」"},
    {"name": "洛阳纸贵", "source": "《晋书·左思传》", "key": "纸贵",
     "wrong": ["物价", "纸涨价", "买不起纸"],
     "right": "作品风行传抄", "fix": "写物价别用；要写作品流行才用"},
    {"name": "狗尾续貂", "source": "《晋书·赵王伦传》", "key": "狗尾续貂",
     "wrong": ["狗尾巴", "续写", "接着写"],
     "right": "续作远不如原作（自谦/贬）", "fix": "中性写续写别用此典"},
    {"name": "一鼓作气", "source": "《左传·庄公十年》", "key": "一鼓作气",
     "wrong": ["打鼓", "鼓励", "加油"],
     "right": "趁劲头一次做成", "fix": "写打鼓别用；要写趁势做事才用"},
    {"name": "投笔从戎", "source": "《后汉书·班超传》", "key": "投笔",
     "wrong": ["写字", "书法", "弃学", "不读书"],
     "right": "弃文从军", "fix": "写书法别用；要写转行从军才用"},
    {"name": "苏武牧羊", "source": "《汉书·李广苏建传》", "key": "牧羊",
     "wrong": ["放羊", "牧羊人", "羊群"],
     "right": "持节十九年不改其志", "fix": "写放牧别用；要写持守才用"},
    {"name": "精卫填海", "source": "《山海经·北山经》", "key": "精卫",
     "wrong": ["填海造陆", "工程", "鸟很可爱"],
     "right": "明知不可为而为之的执念", "fix": "写工程/鸟类别用；要写执念才用"},
    {"name": "庄周梦蝶", "source": "《庄子·齐物论》", "key": "梦蝶",
     "wrong": ["蝴蝶很美", "花丛", "梦到蝴蝶"],
     "right": "物我难辨、真假不分", "fix": "只写蝴蝶别用典；要写恍惚才用"},
    {"name": "桃花源", "source": "陶渊明《桃花源记》", "key": "桃花源",
     "wrong": ["景点", "旅游", "桃花林", "赏桃花"],
     "right": "避世理想地，再寻不得", "fix": "写赏花别用；要写理想之地才用"},
    {"name": "二十四桥", "source": "杜牧《寄扬州韩绰判官》", "key": "二十四桥",
     "wrong": ["二十四座桥", "桥的数量", "数桥"],
     "right": "扬州月夜名景（非实数考据）", "fix": "别写「正好二十四座」；当专名用"},
    {"name": "乌衣巷", "source": "刘禹锡《乌衣巷》", "key": "乌衣巷",
     "wrong": ["乌衣", "黑衣服", "衣服"],
     "right": "王谢旧宅，门第兴衰", "fix": "写衣服别用；要写兴衰才用"},
    {"name": "铜雀台", "source": "曹操建于邺；杜牧《赤壁》", "key": "铜雀",
     "wrong": ["鸟", "铜做的雀", "雀鸟"],
     "right": "胜利者收藏权力与美人的象征", "fix": "别写成鸟/器物；要写征服与囚禁才用"},
    {"name": "阳关三叠", "source": "王维《送元二使安西》", "key": "阳关",
     "wrong": ["关口", "边关", "阳关道"],
     "right": "反复不舍的送别", "fix": "写边关别用；要写送别才用"},
    {"name": "青衫湿", "source": "白居易《琵琶行》", "key": "青衫湿",
     "wrong": ["下雨", "淋湿", "青色的衣服"],
     "right": "同是天涯沦落人的共感之泪", "fix": "写淋雨别用；要写共感才用"},
    {"name": "湘妃竹", "source": "晋·张华《博物志》", "key": "湘妃竹",
     "wrong": ["竹子品种", "斑竹很漂亮", "园林"],
     "right": "泪染成斑，至哀至贞", "fix": "写植物别用；要写丧偶之痛才用"},
    {"name": "鲛人泣珠", "source": "晋·张华《博物志》（亦见《搜神记》）", "key": "鲛人",
     "wrong": ["鱼尾", "美人鱼", "海底"],
     "right": "泪落成珠，代价沉重", "fix": "写人鱼形象别用典；要写「以泪换珠」才用"},
    {"name": "望帝啼鹃", "source": "晋·常璩《华阳国志·蜀志》", "key": "望帝",
     "wrong": ["皇帝", "帝王", "皇位"],
     "right": "失国化鹃、哀思不绝", "fix": "写帝王别用；要写哀思才用"},
    {"name": "庄周鼓盆", "source": "《庄子·至乐》", "key": "鼓盆",
     "wrong": ["敲盆", "打鼓", "乐器", "玩闹"],
     "right": "以通达消解丧妻之痛", "fix": "写乐器别用；要写悼亡的通达才用"},
    {"name": "卧薪尝胆", "source": "《史记·越王勾践世家》", "key": "卧薪",
     "wrong": ["睡觉", "尝菜", "吃苦", "美食"],
     "right": "忍辱图强", "fix": "写生活苦别用；要写复仇/图强才用"},
    {"name": "荆轲易水", "source": "《史记·刺客列传》（《易水歌》）", "key": "易水",
     "wrong": ["游泳", "河水", "渡河", "风景"],
     "right": "一去不返的决绝", "fix": "写河流别用；要写决绝告别才用"},
    {"name": "闻鸡起舞", "source": "《晋书·祖逖传》", "key": "闻鸡",
     "wrong": ["鸡叫", "公鸡", "跳舞", "农家"],
     "right": "及时奋发", "fix": "写农事别用；要写奋发才用"},
    {"name": "结草衔环", "source": "《左传·宣公十五年》/《续齐谐记》", "key": "结草",
     "wrong": ["草地", "草绳", "花草"],
     "right": "受恩必报", "fix": "写草木别用；要写报恩才用"},
]

# ================================================================ AI 味词表（L10）

AI_FOUR_CHAR = [
    "繁华落尽", "岁月静好", "时光荏苒", "白驹过隙", "物是人非", "沧海桑田",
    "一眼万年", "三生三世", "似水流年", "岁月如歌", "光阴似箭", "往事如烟",
    "繁华似锦", "花开半夏", "时光不老", "地老天荒", "海枯石烂", "流年似水",
    "眉眼如初", "岁月无痕", "若如初见", "人生若只如初见", "岁月无恙", "静好如初",
]

ADJ_ABSTRACT = [
    "唯美", "绝美", "忧伤", "落寞", "凄凉", "孤寂", "寂寥", "苍凉", "悲凉",
    "柔情", "深情", "温柔", "缱绻", "薄凉", "清冷", "孤傲", "洒脱", "迷离",
    "朦胧", "缥缈", "空灵", "优雅", "婉约", "凄美", "落拓", "阑珊",
]

# 具体物象（L11 金句检测；含常见物象字/词）
CONCRETE_IMAGE = [
    "灯", "花", "月", "雪", "雨", "窗", "桥", "舟", "船", "柳", "雁", "燕",
    "蝶", "酒", "茶", "琴", "剑", "马", "门", "墙", "阶", "井", "台", "楼",
    "帘", "帐", "镜", "钗", "簪", "帕", "笺", "信", "书", "墨", "砚", "纸",
    "盏", "杯", "炉", "香", "钟", "鼓", "笛", "箫", "弦", "衣", "袖", "裙",
    "巷", "街", "岸", "汀", "帆", "橹", "桨", "烛", "瓦", "檐", "苔", "竹",
    "松", "梅", "兰", "荷", "莲", "菊", "枫", "芦", "沙", "石", "城", "关",
    "烽", "旗", "印", "符", "弓", "刀", "甲", "车", "针", "线", "米", "盐",
    "糖", "饼", "伞", "秤", "钱", "箱", "匣", "珠", "玉", "瓷", "鼎", "磬",
    "笙", "筝", "瑟", "琵琶", "楼阁", "长亭", "渡口", "石阶", "灯花",
]

# 高频虚字/功能字（L4 实词统计时排除）
STOP_CHARS = set(
    "的了在是我你他她它们着过又也就都还很没有一和与而且却只把被让给对从向到上下里中外汇来去会能要这那些什么谁哪呢吧吗啊呀之乎者也矣兮其以于为因如若似将已曾但或再更最太"
)

# 句内气口后常见虚词（断韵 L12 不把这些当韵脚）
WEAK_END = set("的了着过是吗呢吧啊呀之乎者也矣兮来去又就都还在和与")

# ================================================================ 用典配额 / 核心表达（L13 / L14）

# 用典配额（写死）：全篇 ≤2 处；同一段 ≤1 处；副歌首句/金句位不用典；同一典故不得重复
ALLUSION_QUOTA_TOTAL = 2      # 建议上限
ALLUSION_QUOTA_WARN_AT = 3    # =3 处 warn
ALLUSION_QUOTA_ERROR_AT = 4   # ≥4 处（>3）error
ALLUSION_SECTION_MAX = 2      # 同一段 ≥2 处 warn

# 题旨词（L14 核心贯穿：除具体物象外，情绪/主题词也算核心）
TOPIC_WORDS = [
    "故人", "旧年", "从前", "归期", "归人", "相思", "离别", "重逢", "乡音",
    "旧事", "往事", "少年", "江湖", "故里", "长安", "江南", "旧梦", "前尘",
    "人间", "客途", "天涯", "归途", "旧约", "姓名", "灯火",
]

# 动词字表（L14 自造金句：至少有一个动作，不能全是名词/典故）
VERB_CHARS = set(
    "落过照掩映生满坐站走开挑提放收折数等望听看问说笑哭醉醒睡燃点吹换负骗"
    "学争唱写读画煮斟捧递敲推拉背抱追藏遮系解挂乘骑踏涉渡归回送迎借寻记忘"
    "成化湿冷暖锁隔拾擦抹洗缝绣织剪烧熄灭偷借留去来入出关开"
)

# ================================================================ 句长基准（L2）

SECTION_KIND_BOUNDS = {
    "verse": (5, 12),
    "chorus": (6, 14),
    "prechorus": (5, 12),
    "bridge": (5, 12),
    "outro": (5, 12),
    "unknown": (5, 14),
    "intro": (0, 0),  # 前奏无词
}

KIND_KEYWORDS = [
    ("预副歌", "prechorus"), ("副歌", "chorus"), ("叠歌", "chorus"), ("主歌", "verse"),
    ("桥", "bridge"), ("尾", "outro"), ("尾声", "outro"), ("结束", "outro"),
    ("前奏", "intro"), ("间奏", "intro"), ("chorus", "chorus"), ("verse", "verse"),
    ("bridge", "bridge"), ("outro", "outro"), ("pre", "prechorus"),
]

# ================================================================ 内置 demo（应「可交付」）

DEFAULT_DEMO_LYR = """# lint_guofeng_lyric.py 内置 demo：相思 · 言前辙 · 22 句
# 结构：主歌A/B → 预副歌 → 副歌 → 桥 → 副歌（再现）→ 尾；偶句押，副歌 1/2/4 句押
[主歌A]
灯:1 花:1 落:4 了:0 | 窗:1 前:2
雨:3 声:1 敲:1 到:4 | 石:2 阶:1 前:2
信:4 纸:3 压:1 在:4 | 灯:1 影:3 里:3
等:3 一:1 句:4 | 迟:2 来:2 的:0 团:2 圆:2

[主歌B]
铜:2 镜:4 蒙:2 灰:1 | 照:4 不:4 见:4 人:2 间:1
你:3 留:2 下:4 的:0 | 针:1 线:4 还:2 在:4 枕:3 边:1
燕:4 子:3 南:2 飞:1 | 又:4 飞:1 回:2 来:2
我:3 数:3 到:4 | 第:4 九:3 个:4 秋:1 天:1

[预副歌]
别:2 让:4 等:3 待:4 | 成:2 了:0 习:2 惯:4
一:1 句:4 话:4 | 说:1 三:1 遍:4

[副歌]
你:3 若:4 回:2 头:2 旧:4 门:2 前:2
灯:1 还:2 亮:4 着:0 等:3 团:2 圆:2
灯:1 点:3 到:4 你:3 说:1 的:0 那:4 一:1 年:2
别:2 忘:4 了:0 回:2 家:1 门:2 前:2

[桥]
把:3 旧:4 信:4 折:2 成:2 小:3 船:2
放:4 进:1 雨:3 里:3 漂:1 远:3

[副歌（再现）]
你:3 若:4 回:2 头:2 旧:4 门:2 前:2
灯:1 还:2 亮:4 着:0 等:3 团:2 圆:2
灯:1 点:3 到:4 你:3 说:1 的:0 那:4 一:1 年:2
别:2 忘:4 了:0 回:2 家:1 门:2 前:2

[尾]
你:3 若:4 来:2 了:0 把:3 灯:1 挑:1 亮:4 一:1 点:3
别:2 让:4 雨:3 声:1 替:4 我:3 说:1 完:2
"""


# ================================================================ 基础工具


def _setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def read_text_file(path: Path) -> str:
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"文件编码无法识别（既不是 UTF-8 也不是 GBK）：{path}")


def is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


# ================================================================ .lyr 解析

PUNCT = set("，。、；：！？…—·「」『』（）()《》〈〉“”‘’,.;:!?\"' \t")


def section_kind(name: str) -> str:
    low = name.lower()
    for kw, kind in KIND_KEYWORDS:
        if kw.lower() in low:
            return kind
    return "unknown"


def parse_lyr(text: str) -> tuple[list[dict], list[str]]:
    """→ (sections, notes)。section = {name, kind, lines:[line]}；
    line = {chars:[{ch,tone}], text, segments:[str], index, line_no}。"""
    sections: list[dict] = []
    notes: list[str] = []
    cur = {"name": "未命名段", "kind": "unknown", "lines": [], "order": 0}
    sections.append(cur)
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        if s.startswith("[") and s.endswith("]"):
            name = s[1:-1].strip() or "未命名段"
            cur = {"name": name, "kind": section_kind(name), "lines": [], "order": len(sections)}
            sections.append(cur)
            continue
        # 解析一行：把 | 单独成词，其余按空白切
        norm = s.replace("|", " | ")
        chars: list[dict] = []
        raw_chars: list[str] = []
        segments: list[str] = []
        seg_buf: list[str] = []
        annotated = 0
        for tok in norm.split():
            if tok == "|":
                segments.append("".join(seg_buf))
                seg_buf = []
                continue
            if ":" in tok:
                body, tone_part = tok.split(":", 1)
            else:
                body, tone_part = tok, ""
            tone_part = tone_part.strip()
            tones = [int(x) for x in tone_part if x.isdigit()]
            for i, ch in enumerate(body):
                if is_cjk(ch) or ch.isalnum():
                    raw_chars.append(ch)
                if ch in PUNCT or not is_cjk(ch):
                    continue
                if tones:
                    annotated += 1
                if len(tones) == len(body) and len(body) > 1:
                    tone = tones[i]
                elif len(tones) == 1:
                    tone = tones[0]
                else:
                    tone = 0
                chars.append({"ch": ch, "tone": tone if tone in (0, 1, 2, 3, 4) else 0})
                seg_buf.append(ch)
        if not chars:
            continue
        segments.append("".join(seg_buf))
        cur["lines"].append({
            "chars": chars,
            "text": "".join(c["ch"] for c in chars),
            "raw": "".join(raw_chars),
            "segments": segments,
            "annotated": annotated,
            "line_no": len([l for sec in sections for l in sec["lines"]]) + 1,
        })
    sections = [sec for sec in sections if sec["lines"]]
    annotated_total = sum(ln.get("annotated", 0) for sec in sections for ln in sec["lines"])
    if not sections:
        notes.append("没有解析到任何歌词行：请检查 .lyr 是否用 `字:调` 写法（例如 `江:1 南:2 雨:3`）。")
    elif annotated_total == 0:
        notes.append("全篇没有 `字:调` 声调标注（声调一律按未知处理）：L3 倒字无法校验，"
                     "旋律会退化成同音；建议按 `江:1 南:2 雨:3` 补标注。")
    return sections, notes


# ================================================================ 填词槽位 / 简谱解析


def load_slots(path: Path) -> dict:
    """→ {"lines": [...], "sections": [段落名...]}；段落名用于 L9 判断曲式是否自带多段副歌。"""
    data = json.loads(read_text_file(path))
    lines: list[dict] = []
    names: list[str] = []
    for sec in data.get("sections", []):
        name = sec.get("name", "")
        if name:
            names.append(name)
        for ln in sec.get("lines", []):
            lines.append({
                "section": name,
                "line": ln.get("line"),
                "syllables": int(ln.get("syllables") or 0),
                "min_syllables": int(ln.get("min_syllables") or 0),
                "rhyme": bool(ln.get("rhyme")),
            })
    return {"lines": lines, "sections": names}


def parse_jp_notes(text: str) -> tuple[list[dict], dict]:
    """解析 .jp 的 @melody → (音符列表, 头部)。自己实现，不 import 作曲脚本。"""
    headers: dict[str, str] = {}
    block = ""
    notes: list[dict] = []
    bar = 0
    token_re = re.compile(r"^([#b]?)([0-7])([',]*)(?:[:/](\d+(?:\.\d+)?))?$")
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("@"):
            body = s[1:].strip()
            parts = body.split(None, 1)
            name = parts[0].lower() if parts else ""
            rest = parts[1].strip() if len(parts) > 1 else ""
            if name in ("marks", "melody", "chords", "bass", "perc"):
                block = name
            else:
                block = ""
                headers[name] = rest
            continue
        if block != "melody":
            continue
        for part in s.split("|"):
            part = part.strip()
            if not part:
                continue
            bar += 1
            for tok in part.split():
                m = token_re.match(tok)
                if not m:
                    continue
                deg = int(m.group(2))
                dur = float(m.group(4)) if m.group(4) else 1.0
                oct_shift = m.group(3).count("'") - m.group(3).count(",")
                if deg == 0:
                    continue
                semis = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}[deg] + 12 * oct_shift
                if m.group(1) == "#":
                    semis += 1
                elif m.group(1) == "b":
                    semis -= 1
                notes.append({"bar": bar, "deg": deg, "semis": semis, "dur": dur})
    return notes, headers


# ================================================================ 报告数据结构


class Findings:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, level: str, loc: str, rule: str, msg: str, fix: str) -> None:
        self.rows.append({"level": level, "loc": loc, "rule": rule, "msg": msg, "fix": fix})

    def count(self, level: str) -> int:
        return len([r for r in self.rows if r["level"] == level])

    def for_rules(self, rules: list[str]) -> list[dict]:
        return [r for r in self.rows if r["rule"] in rules]

    def sorted_rows(self) -> list[dict]:
        order = {"error": 0, "warn": 1, "info": 2}
        return sorted(self.rows, key=lambda r: order.get(r["level"], 3))


# ================================================================ 工具函数


def flatten_lines(sections: list[dict]) -> list[dict]:
    out: list[dict] = []
    for sec in sections:
        if sec["kind"] == "intro":
            continue
        for pos, ln in enumerate(sec["lines"], 1):
            ln["section"] = sec["name"]
            ln["kind"] = sec["kind"]
            ln["_pos"] = pos
            out.append(ln)
    return out


def rhyme_line_numbers(sec: dict) -> list[int]:
    """段内必须押韵的句序号（1 基）：偶句 + 段末句；副歌再加第 1 句。

    段末若是 ≤2 字的拖腔句（如「痴」「啊」），不算韵位——那是气口字，不是韵脚。
    """
    lines = sec["lines"]
    n = len(lines)
    if sec["kind"] == "intro" or n == 0:
        return []
    pos = [i for i in range(2, n + 1, 2)]
    if n not in pos and len(lines[n - 1]["chars"]) > 2:
        pos.append(n)
    if sec["kind"] == "chorus" and 1 not in pos:
        pos = [1] + pos
    return sorted(pos)


def resolve_zhe(ch: str, prefer: str | None = None) -> str | None:
    zs = ZHE_CHARS.get(ch)
    if not zs:
        return None
    if prefer and prefer in zs:
        return prefer
    if len(zs) == 1:
        return next(iter(zs))
    return None


# ================================================================ 规则实现


def rule_l1(sections: list[dict], f: Findings, allow_change: bool) -> dict:
    """L1 韵脚一致性（十三辙）。"""
    info = {"section_zhe": {}, "rhyme_rows": []}
    sec_zhe: dict[str, str] = {}
    for sec in sections:
        if sec["kind"] == "intro" or not sec["lines"]:
            continue
        pos = rhyme_line_numbers(sec)
        resolved: list[tuple[int, str, str]] = []  # (句号, 字, 辙)
        for i in sorted(pos):
            if i > len(sec["lines"]):
                continue
            ln = sec["lines"][i - 1]
            ch = ln["chars"][-1]["ch"]
            z = resolve_zhe(ch)
            if z:
                resolved.append((i, ch, z))
        # 段内多数票定本段辙
        if resolved:
            votes: dict[str, int] = {}
            for _, _, z in resolved:
                votes[z] = votes.get(z, 0) + 1
            main = sorted(votes.items(), key=lambda kv: -kv[1])[0][0]
            sec_zhe[sec["name"]] = main
            info["section_zhe"][sec["name"]] = main
        for i in sorted(pos):
            if i > len(sec["lines"]):
                continue
            ln = sec["lines"][i - 1]
            ch = ln["chars"][-1]["ch"]
            z = resolve_zhe(ch)
            loc = f"{sec['name']} 第 {i} 句"
            if z is None:
                if ch in ZHE_CHARS:
                    f.add("info", loc, "L1",
                          f"韵脚字「{ch}」是十三辙里的多音字，无法自动判辙，请人工确认。",
                          "若本段主韵已在报告第四节列出，按主韵读即可。")
                else:
                    f.add("info", loc, "L1",
                          f"韵脚字「{ch}」不在内置十三辙字表，无法自动归辙。",
                          "换一个同辙常用字（报告第四节有各辙常用韵脚），或人工确认。")
                continue
            info["rhyme_rows"].append({"section": sec["name"], "line": i, "char": ch, "zhe": z})
            main = sec_zhe.get(sec["name"])
            if main and z != main:
                if allow_change:
                    f.add("info", loc, "L1",
                          f"韵脚「{ch}」归「{z}」辙，与本节主韵「{main}」不同（已 --allow-change-rhyme 放行）。",
                          "转韵处建议加一句过渡，让听众有换的气口。")
                else:
                    f.add("error", loc, "L1",
                          f"同段换辙：韵脚「{ch}」归「{z}」辙，本节主韵是「{main}」辙。",
                          f"把「{ch}」换成本辙韵脚；或整段统一到「{main}」辙；确要转韵加 --allow-change-rhyme。")
    # 跨段
    names = list(sec_zhe.keys())
    if len(names) > 1:
        first = sec_zhe[names[0]]
        for nm in names[1:]:
            z = sec_zhe[nm]
            if z != first:
                lvl = "info" if allow_change else "warn"
                f.add(lvl, f"{nm}", "L1",
                      f"跨段换辙：本段主韵「{z}」，首段主韵「{first}」。" +
                      ("（已 --allow-change-rhyme 放行）" if allow_change else "跨段换辙可以有，但要给过渡句。"),
                      f"若无意转韵，把「{nm}」韵脚统一到「{first}」辙；有意转韵则副歌前留一句气口。")
    info["section_zhe"] = sec_zhe
    return info


def rule_l2(sections: list[dict], f: Findings, slots: list[dict] | None) -> dict:
    info = {"slot_used": bool(slots), "slot_mismatch": 0}
    lines = flatten_lines(sections)
    if slots:
        if len(slots) != len(lines):
            f.add("warn", "全篇", "L2",
                  f"填词槽位共 {len(slots)} 句，歌词有 {len(lines)} 句，数量不一致，L2 按前 {min(len(slots), len(lines))} 句对照。",
                  "确认是不是漏抄/多写了句；或重新跑 jianpu2lyricslots.py 生成槽位。")
        for i, ln in enumerate(lines):
            if i >= len(slots):
                break
            sl = slots[i]
            n = len(ln["text"])
            syl = sl["syllables"]
            loc = f"{ln['section']} 第 {ln['_pos']} 句（全局第 {ln['line_no']} 行）"
            if syl and abs(n - syl) > 2:
                f.add("error", loc, "L2",
                      f"这句 {n} 字，槽位音节数 {syl}（允许 ±2），差 {n - syl:+d} 字。",
                      f"按旋律改成 {max(1, syl - 2)}–{syl + 2} 字；或重新断句（一字一音为准）。")
                info["slot_mismatch"] += 1
            elif syl and n < sl["min_syllables"]:
                f.add("warn", loc, "L2",
                      f"这句 {n} 字，少于槽位最少 {sl['min_syllables']} 字，会把整句挤成拖腔。",
                      f"补到 {sl['min_syllables']}–{syl} 字，让每个字都有落点。")
        return info
    for ln in lines:
        lo, hi = SECTION_KIND_BOUNDS.get(ln["kind"], SECTION_KIND_BOUNDS["unknown"])
        n = len(ln["text"])
        loc = f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）"
        if n > hi:
            f.add("error", loc, "L2",
                  f"这句 {n} 字，超过{kind_name(ln['kind'])}上限 {hi} 字（建议 {lo}–{hi}）。",
                  f"拆成两句或删到 {hi} 字以内；长句只留在副歌第 3 句。")
        elif n < lo:
            f.add("warn", loc, "L2",
                  f"这句 {n} 字，少于{kind_name(ln['kind'])}下限 {lo} 字，容易撑不满一小节。",
                  f"补到 {lo} 字以上，或把两句并成一句。")
    return info


def section_line_index(ln: dict) -> int:
    return ln.get("_pos", 1)


def kind_name(kind: str) -> str:
    return {"verse": "主歌", "chorus": "副歌", "prechorus": "预副歌",
            "bridge": "桥段", "outro": "尾声", "intro": "前奏"}.get(kind, "段落")


def rule_l3(sections: list[dict], f: Findings, jp_notes: list[dict] | None) -> dict:
    """L3 倒字：按四声走向表查句尾与重音字（需要 --jp）。

    对齐方式：按句、按拍（每字 1 拍）。一字多音时（如句尾「经过音 + 落音」、
    上声两音）把这两个音归到同一个字，取落音判走向；这样与
    jianpu2lyricslots.py 的「syllables = 音符数、允许一字多音」口径一致。
    """
    info = {"executed": False, "aligned_lines": 0, "notes": 0}
    if not jp_notes:
        return info
    info["executed"] = True
    info["notes"] = len(jp_notes)
    lines = flatten_lines(sections)
    idx = 0
    truncated = False
    for ln in lines:
        n = len(ln["chars"])
        if n == 0:
            continue
        need = float(n)  # 每字 1 拍
        group: list[dict] = []
        acc = 0.0
        while idx < len(jp_notes) and acc < need - 1e-9:
            group.append(jp_notes[idx])
            acc += jp_notes[idx]["dur"]
            idx += 1
        if len(group) < n:
            truncated = True
            break
        # 按 1 拍窗口把音符分给每个字
        char_notes: list[list[dict]] = []
        wi = 0
        pos = 0.0
        for i in range(n):
            bucket: list[dict] = []
            while wi < len(group) and pos < (i + 1) - 1e-9:
                bucket.append(group[wi])
                pos += group[wi]["dur"]
                wi += 1
            if not bucket:
                bucket = [group[min(wi, len(group) - 1)]]
            char_notes.append(bucket)
        pitches = [b[-1]["semis"] for b in char_notes]      # 每字落音
        firsts = [b[0]["semis"] for b in char_notes]        # 每字起音
        durs = [max(x["dur"] for x in b) for b in char_notes]
        info["aligned_lines"] += 1
        # 重音字：时值最长优先，并列取音更高者（旋律重音）
        best = 0
        for k in range(1, len(durs)):
            if (durs[k], pitches[k]) > (durs[best], pitches[best]):
                best = k
        loc_base = f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）"
        for k, chd in enumerate(ln["chars"]):
            tone = chd["tone"]
            if tone not in (1, 2, 3, 4):
                continue
            # 走向 = 这个字自己的音高变化：一字多音（经过音/上声两音）取「起音→落音」，
            # 一字一音时取「前一字落音 → 本字落音」，这才是听众听到的「腔」
            if len(char_notes[k]) >= 2:
                intra = pitches[k] - firsts[k]
            elif k > 0:
                intra = pitches[k] - pitches[k - 1]
            else:
                intra = None
            if k == n - 1:
                interval = intra if intra is not None else 0
                why = tone_conflict(tone, interval, is_final=True)
                if why:
                    f.add("error", loc_base, "L3",
                          f"句尾倒字：「{chd['ch']}」是{why[0]}，旋律却{why[1]}（{interval:+d} 半音）。",
                          f"句尾改成{why[2]}的字，或把句尾落音改成与「{chd['ch']}」同向的音。")
            elif k == best and intra is not None:
                why = tone_conflict(tone, intra, is_final=False)
                if why:
                    f.add("warn", loc_base, "L3",
                          f"重音字倒字：「{chd['ch']}」（本句重音）是{why[0]}，旋律却{why[1]}（{intra:+d} 半音）。",
                          f"把重音换到{why[2]}的字上，或把这个字的起音改成同向。")
    if truncated:
        f.add("info", "全篇", "L3",
              f"旋律音符不足：只对齐校验了 {info['aligned_lines']} 句（共 {len(lines)} 句）。",
              "确认 --jp 与歌词句数匹配；或先跑 jianpu2lyricslots.py 看每句音节数。")
    return info


def tone_conflict(tone: int, interval: int, is_final: bool) -> tuple[str, str, str] | None:
    """(字调名, 旋律走向描述, 修法建议) 或 None。"""
    if tone == 1:  # 阴平 55：平或微升
        if is_final and interval <= -3:
            return ("阴平（应平、可拖）", f"向下大跳 {interval}", "阴平或上声")
        if not is_final and interval <= -3:
            return ("阴平（应平或微升）", f"向下大跳 {interval}", "阴平")
    elif tone == 2:  # 阳平 35：上行
        if is_final and interval <= -3:
            return ("阳平（应上行）", f"向下大跳 {interval}", "去声")
        if not is_final and interval <= -2:
            return ("阳平（应上行）", f"向下走 {interval}", "去声")
    elif tone == 4:  # 去声 51：下行
        if is_final and interval >= 3:
            return ("去声（应下行）", f"向上大跳 {interval:+d}", "阴平或阳平")
        if not is_final and interval >= 3:
            return ("去声（应下行）", f"向上大跳 {interval:+d}", "阴平或阳平")
    elif tone == 3:  # 上声 214：先降后升
        if not is_final and interval >= 5:
            return ("上声（应先降后升）", f"直接向上大跳 {interval:+d}", "阳平")
    return None


def rule_l4(sections: list[dict], f: Findings) -> dict:
    """L4 重复字词：同句重字 >2、全篇二字词 ≥4 次、单字实词 ≥6 次。

    副歌再现等「整段重复」按设计处理：文本完全相同的段落只统计一次，
    避免把重复段的设计当成重复病。
    """
    info = {"top": [], "words": []}
    lines = flatten_lines(sections)
    for ln in lines:
        cnt: dict[str, int] = {}
        for c in ln["chars"]:
            cnt[c["ch"]] = cnt.get(c["ch"], 0) + 1
        for ch, k in cnt.items():
            if k > 2 and ch not in WEAK_END:
                f.add("warn", f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）", "L4",
                      f"同句里「{ch}」出现 {k} 次，读起来打结。",
                      "删一个或用近义字替换；叠字只留一处。")

    # 整段去重（副歌再现只算一次）：按段文本签名过滤
    def unique_sections() -> list[dict]:
        out: list[dict] = []
        seen: set[tuple[str, ...]] = set()
        for sec in sections:
            sig = tuple(ln["text"] for ln in sec["lines"])
            if sig in seen:
                continue
            seen.add(sig)
            out.append(sec)
        return out

    uniq_sections = unique_sections()
    final_chars = {ln["chars"][-1]["ch"] for sec in sections for ln in sec["lines"]}

    # 二字词频率（实词重复的主要形态；含句尾韵脚字的组合不统计）
    word_freq: dict[str, int] = {}
    for sec in uniq_sections:
        for ln in sec["lines"]:
            t = ln["text"]
            for i in range(len(t) - 1):
                w = t[i:i + 2]
                if all(ch in STOP_CHARS or ch in WEAK_END for ch in w):
                    continue
                if any(ch in final_chars for ch in w):
                    continue
                word_freq[w] = word_freq.get(w, 0) + 1
    for w, k in sorted(word_freq.items(), key=lambda kv: -kv[1]):
        if k >= 4:
            f.add("warn", "全篇", "L4",
                  f"二字词「{w}」全篇出现 {k} 次（阈值 4），意象/动词被重复消耗。",
                  f"把其中 {k - 3} 处换成同功能的其他词；副歌重复段只算一次。")
    info["words"] = sorted(word_freq.items(), key=lambda kv: -kv[1])[:5]

    # 单字实词（排除句尾韵脚字与虚字）
    freq: dict[str, int] = {}
    for sec in uniq_sections:
        for ln in sec["lines"]:
            for c in ln["chars"]:
                ch = c["ch"]
                if ch in STOP_CHARS or ch in final_chars or ch in WEAK_END:
                    continue
                freq[ch] = freq.get(ch, 0) + 1
    top = sorted(freq.items(), key=lambda kv: -kv[1])
    for ch, k in top:
        if k >= 6:
            f.add("warn", "全篇", "L4",
                  f"单字实词「{ch}」全篇出现 {k} 次（阈值 6），意象被重复消耗。",
                  f"把其中 {k - 5} 处换成同功能的其他字；副歌重复段只算一次。")
    info["top"] = [(ch, k) for ch, k in top[:5]]
    return info


def rule_l5(sections: list[dict], f: Findings) -> dict:
    """L5 伪古风词汇堆砌。"""
    info = {"distinct": 0, "total": 0, "words": []}
    lines = flatten_lines(sections)
    all_text = "".join(ln["raw"] for ln in lines)
    found: dict[str, int] = {}
    for w in PSEUDO_GUFENG:
        c = all_text.count(w)
        if c:
            found[w] = c
    total = sum(found.values())
    info.update({"distinct": len(found), "total": total,
                 "words": sorted(found.items(), key=lambda kv: -kv[1])})
    if len(found) >= 6:
        f.add("error", "全篇", "L5",
              f"伪古风词堆砌：出现 {len(found)} 个（{'、'.join(w for w, _ in info['words'][:8])}…），共 {total} 处。",
              "这些词只有在具体叙事里才成立：一象一情，删到 3 个以内，且每个都要被一个动作接住。")
    elif len(found) >= 4:
        f.add("warn", "全篇", "L5",
              f"伪古风词偏多：出现 {len(found)} 个（{'、'.join(w for w, _ in info['words'])}），共 {total} 处。",
              "留 2–3 个最贴题的，其余换成可触物象。")
    for ln in lines:
        hits = [w for w in PSEUDO_GUFENG if w in ln["raw"]]
        if len(hits) >= 3:
            f.add("warn", f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）", "L5",
                  f"同一句里堆了 {len(hits)} 个伪古风词（{'、'.join(hits)}），句子没有画面。",
                  "只留 1 个，其余位置换成具体物象 + 动词。")
    return info


def rule_l6(sections: list[dict], f: Findings, allow_modern: bool) -> dict:
    """L6 时空错乱（现代词黑名单）。"""
    info = {"hits": []}
    lines = flatten_lines(sections)
    for ln in lines:
        hits = [w for w in MODERN_WORDS if w in ln["raw"]]
        if not hits:
            continue
        info["hits"].extend(hits)
        lvl = "info" if allow_modern else "warn"
        loc = f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）"
        f.add(lvl, loc, "L6",
              f"出现现代词：{'、'.join(hits)}" + ("（已 --allow-modern 放行）" if allow_modern else "，与古代场景冲突。"),
              "确认是有意的今昔对照；否则换成同时代的物件（如「手机」→「信笺」）。")
    if len(set(info["hits"])) >= 3 and not allow_modern:
        f.add("error", "全篇", "L6",
              f"现代词共 {len(set(info['hits']))} 种（{'、'.join(sorted(set(info['hits'])))}），时空明显错乱。",
              "整段换成古代场景；若写国潮，把这些词集中在一段做「今」的对照。")
    return info


def rule_l7(sections: list[dict], f: Findings) -> dict:
    """L7 典故（内置正误表）。"""
    info = {"used": [], "misused": 0}
    lines = flatten_lines(sections)
    texts = [ln["raw"] for ln in lines]
    for i, ln in enumerate(lines):
        text = ln["raw"]
        ctx = text + (texts[i + 1] if i + 1 < len(texts) else "")
        for item in ALLUSION_TABLE:
            if item["key"] not in text:
                continue
            if item["name"] not in info["used"]:
                info["used"].append(item["name"])
            bad = [w for w in item["wrong"] if w in ctx]
            if bad:
                info["misused"] += 1
                loc = f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）"
                f.add("warn", loc, "L7",
                      f"疑似误用典故「{item['name']}」（{item['source']}）：原意是「{item['right']}」，"
                      f"但句中出现「{'、'.join(bad)}」，语义相抵。",
                      item["fix"])
    # 密度/堆砌交给 L13（这里只管「用得对不对」）
    return info


def rule_l8(sections: list[dict], f: Findings) -> dict:
    """L8 生僻字（GB2312 一级字表判断）。"""
    info = {"rare": []}
    lines = flatten_lines(sections)
    seen: set[str] = set()
    for ln in lines:
        for c in ln["chars"]:
            ch = c["ch"]
            if ch in seen:
                continue
            seen.add(ch)
            try:
                b = ch.encode("gb2312")
            except UnicodeEncodeError:
                info["rare"].append((ch, "不在 GB2312"))
                f.add("warn", f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）", "L8",
                      f"「{ch}」不在 GB2312 字集，属生僻字，听众可能不认识也唱不出。",
                      "换成常用同义字；确要保留请加注音说明。")
                continue
            if len(b) == 2 and b[0] > 0xD7:  # 一级字区：B0A1–D7F9
                info["rare"].append((ch, "GB2312 二级字"))
                f.add("warn", f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）", "L8",
                      f"「{ch}」属 GB2312 二级字（非一级常用字），偏生僻。",
                      "换成一级常用字；若是专名/地名，保留但要在文案里注音。")
    return info


def rule_l9(sections: list[dict], f: Findings, slot_sections: list[str] | None = None) -> dict:
    """L9 结构（段落齐全、副歌重复、hook 位置、段落顺序）。

    副歌次数：给了 --slots 时以「曲式自带的副歌段数」为准——
    曲只有一遍副歌时，填词者无法凭空加段，那段 warn 降为 info（曲式设定，不是词稿缺陷）；
    曲里有 ≥2 段副歌但词稿只填了 1 段，才报 warn（漏填）。
    """
    info = {"kinds": [], "chorus_count": 0, "verse_count": 0, "slot_chorus": None}
    kinds = [sec["kind"] for sec in sections]
    info["kinds"] = kinds
    info["chorus_count"] = kinds.count("chorus")
    info["verse_count"] = kinds.count("verse")
    if slot_sections is not None:
        info["slot_chorus"] = sum(
            1 for nm in slot_sections if ("副歌" in nm) or ("chorus" in nm.lower()))
    if info["verse_count"] == 0:
        f.add("error", "全篇", "L9", "没有主歌段落，歌词缺少叙事铺垫。",
              "补 4 句主歌（交代时间、地点、人物、正在发生的事）。")
    if info["chorus_count"] == 0:
        f.add("error", "全篇", "L9", "没有副歌段落（段落名需含「副歌」或 chorus），歌词没有记忆点。",
              "补 4 句副歌：只抒情不推进，每句一个具体物象，1/2/4 句押韵。")
    elif info["chorus_count"] == 1:
        slot_n = info["slot_chorus"]
        if slot_n is not None and slot_n <= 1:
            f.add("info", "全篇", "L9",
                  f"该曲式只含一遍副歌（槽位副歌段数 {slot_n}），属曲式设定，不算词稿缺陷。",
                  "如需副歌再现，让作曲端在 @marks 里加一段副歌；填词阶段保持与曲式一致。")
        elif slot_n is not None and slot_n >= 2:
            f.add("warn", "全篇", "L9",
                  f"槽位里有 {slot_n} 段副歌，词稿只填了 1 段，有一遍副歌被漏掉了。",
                  "把副歌（同一韵、同句式）按槽位再填一遍；重复段只换 1–2 个物象。")
        else:
            f.add("warn", "全篇", "L9",
                  "副歌只出现 1 次，没有重复再现，听众记不住。",
                  "把副歌（同一韵、同句式）再现一次；换 1–2 个物象即可，不要整段改写。")
    if "chorus" in kinds and "verse" in kinds and kinds.index("chorus") < kinds.index("verse"):
        f.add("warn", kinds[kinds.index("chorus")], "L9",
              "副歌出现在主歌之前，结构上先给结论再铺垫，容易泄气。",
              "把副歌移到主歌之后；或改成短副歌前置（只 2 句）做引子。")
    for sec in sections:
        n = len(sec["lines"])
        if sec["kind"] != "intro" and n > 8:
            f.add("info", sec["name"], "L9",
                  f"这一段 {n} 句，篇幅偏长（建议 2–8 句一段）。",
                  "把长段拆开（如主歌A1/A2），或在第 8 句后加预副歌抬升。")
        if sec["kind"] == "verse" and n == 1:
            f.add("warn", sec["name"], "L9",
                  "主歌只有 1 句，撑不起叙事。",
                  "主歌至少 2–4 句：一句定场景、一句给动作、两句铺情绪。")
    return info


def rule_l10(sections: list[dict], f: Findings) -> dict:
    """L10 AI 味（四字词密度、同义堆叠、空泛形容词）。"""
    info = {"phrases": {}, "density": 0.0}
    lines = flatten_lines(sections)
    all_text = "".join(ln["raw"] for ln in lines)
    n_chars = max(1, len(all_text))
    for w in AI_FOUR_CHAR:
        c = all_text.count(w)
        if c:
            info["phrases"][w] = c
    total = sum(info["phrases"].values())
    info["density"] = round(total * 100.0 / n_chars, 2)
    if total:
        f.add("warn", "全篇", "L10",
              f"出现 {total} 个套话四字词（{'、'.join(info['phrases'])}），密度 {info['density']} 个/百字。",
              "这些词等于没写：换成一个具体动作或物象（如「岁月静好」→「茶凉了没人添」）。")
    for ln in lines:
        adjs = [w for w in ADJ_ABSTRACT if w in ln["raw"]]
        if len(adjs) >= 3:
            f.add("warn", f"{ln['section']} 第 {section_line_index(ln)} 句（全局第 {ln['line_no']} 行）", "L10",
                  f"同句堆了 {len(adjs)} 个抽象形容词（{'、'.join(adjs)}），只有情绪没有画面。",
                  "抽象形容词全删，只留一个动词；情绪靠动作与物件暗示。")
    adjs_all = [w for w in ADJ_ABSTRACT if w in all_text]
    if len(adjs_all) >= 6:
        f.add("warn", "全篇", "L10",
              f"抽象形容词共 {len(adjs_all)} 种（{'、'.join(adjs_all[:6])}…），偏空泛。",
              "留下最贴题的 2 个，其余换成行为/物件描写。")
    return info


def rule_l11(sections: list[dict], f: Findings) -> dict:
    """L11 金句（副歌首句/段末是否含具体物象；只提示不判错）。

    口径：只看字数 ≥5 的副歌/尾声首句与末句——单字/双字长音句是拖腔字（如「痴」「烟」），
    不是金句位，跳过；字数 3–4 的句子信息量不足，也不判。
    """
    info = {"checked": 0, "with_image": 0, "skipped": 0, "hook_positions": []}
    for sec in sections:
        if sec["kind"] not in ("chorus", "outro"):
            continue
        for i, ln in enumerate(sec["lines"], 1):
            if i != 1 and i != len(sec["lines"]):
                continue
            n = len(ln["chars"])
            if n <= 2:
                info["skipped"] += 1
                continue
            if n < 5:
                info["skipped"] += 1
                continue
            info["checked"] += 1
            info["hook_positions"].append((sec["name"], i))
            hits = [w for w in CONCRETE_IMAGE if w in ln["raw"]]
            if hits:
                info["with_image"] += 1
            else:
                f.add("info", f"{sec['name']} 第 {i} 句", "L11",
                      f"金句位（{sec['name']} 第 {i} 句，{n} 字）没有具体物象：「{ln['text']}」。",
                      "金句 = 具体物象 + 一个动词 + 一层反常识；先把一个物件放进句子里。")
    return info


def rule_l12(sections: list[dict], f: Findings, zhe_info: dict) -> dict:
    """L12 断韵（句内气口处意外押上别的辙）。"""
    info = {"checked": 0}
    for sec in sections:
        main = zhe_info.get(sec["name"])
        if not main:
            continue
        for i, ln in enumerate(sec["lines"], 1):
            if len(ln["segments"]) < 2:
                continue
            final_ch = ln["chars"][-1]["ch"]
            final_z = resolve_zhe(final_ch, main) or resolve_zhe(final_ch)
            for seg in ln["segments"][:-1]:
                if len(seg) < 2:
                    continue
                mid = seg[-1]
                if mid in WEAK_END:
                    continue
                z = resolve_zhe(mid)
                # 真正的断韵：气口处落在本段主韵（听众以为要押），句尾却跑辙
                if z == main and final_z and final_z != main:
                    info["checked"] += 1
                    f.add("warn", f"{sec['name']} 第 {i} 句（全局第 {ln['line_no']} 行）", "L12",
                          f"句内气口落在「{mid}」（本段主韵「{main}」），句尾却是「{final_ch}」（{final_z} 辙），"
                          f"听众在气口处等到了韵，句尾却没接住，读起来断韵。",
                          f"把气口前的「{mid}」换成虚词，或把句尾改回「{main}」辙；"
                          "气口前不要出现主韵字。")
                    break
    return info


def collect_allusion_hits(sections: list[dict]) -> tuple[list[dict], list[dict]]:
    """→ (用典命中列表, 全部句子)。命中项 = 行号/段落/段内句号/典故名/出处/标志词。"""
    lines = flatten_lines(sections)
    hits: list[dict] = []
    for ln in lines:
        for item in ALLUSION_TABLE:
            if item["key"] in ln["raw"]:
                hits.append({
                    "line_no": ln["line_no"],
                    "section": ln["section"],
                    "pos": ln["_pos"],
                    "name": item["name"],
                    "source": item["source"],
                    "key": item["key"],
                    "text": ln["text"],
                })
    return hits, lines


def _hit_list_text(hits: list[dict], limit: int = 8) -> str:
    bits = [f"第 {h['line_no']} 行「{h['name']}」（{h['source']}）" for h in hits[:limit]]
    more = f"…共 {len(hits)} 处" if len(hits) > limit else ""
    return "、".join(bits) + more


def rule_l13(sections: list[dict], f: Findings, l11: dict) -> dict:
    """L13 用典密度与堆砌（可执行的配额门禁）。

    配额（写死）：全篇 ≤2 处；>3 处 error、=3 处 warn；同一段 ≥2 处 warn；
    连续两句都用典 warn；副歌首句/金句位用典 warn；同一典故重复 ≥2 次 error。
    """
    hits, lines = collect_allusion_hits(sections)
    by_line_no = {ln["line_no"]: ln for ln in lines}
    info = {"hits": hits, "total": len(hits), "by_section": {}, "repeats": [],
            "hook_hits": [], "consecutive": []}
    if not hits:
        return info

    # ① 全篇密度
    if len(hits) >= ALLUSION_QUOTA_ERROR_AT:
        f.add("error", "全篇", "L13",
              f"全篇用典 {len(hits)} 处（>3，配额 ≤2）：{_hit_list_text(hits)}。"
              "这会读成「典故拼贴」——每句都在借古人的话，没有自己的表达。",
              f"删到 ≤2 处（最好 1 处）：保留最能服务叙事的那一个，其余换成具体动作或物象；"
              f"每删一个先自问：删掉这个典，这句话还成立吗？成立就删。")
    elif len(hits) == ALLUSION_QUOTA_WARN_AT:
        f.add("warn", "全篇", "L13",
              f"全篇用典 3 处（建议 ≤2）：{_hit_list_text(hits)}。",
              "再删 1 处。三个典已经会互相抢注意力，听众记不住你到底想说什么。")

    # ② 同一段 ≥2 处
    sec_counts: dict[str, list[dict]] = {}
    for h in hits:
        sec_counts.setdefault(h["section"], []).append(h)
    info["by_section"] = {k: len(v) for k, v in sec_counts.items()}
    for sec_name, hs in sec_counts.items():
        if len(hs) >= ALLUSION_SECTION_MAX:
            f.add("warn", sec_name, "L13",
                  f"这一段用了 {len(hs)} 处典（配额：同段 ≤1）：{_hit_list_text(hs)}。"
                  "一段内连用两个典，听众会出戏。",
                  "这一段只留 1 个典；另一个改成直写——把典故那层意思用自己的话讲一遍。")

    # ③ 连续两句都用典（按「连续用典段」合并成一条，避免刷屏）
    hit_line_nos = sorted({h["line_no"] for h in hits})
    runs: list[list[int]] = []
    cur_run: list[int] = []
    for n in hit_line_nos:
        if cur_run and n == cur_run[-1] + 1:
            cur_run.append(n)
        else:
            if len(cur_run) >= 2:
                runs.append(cur_run)
            cur_run = [n]
    if len(cur_run) >= 2:
        runs.append(cur_run)
    for run in runs:
        a, b = run[0], run[-1]
        info["consecutive"].append((a, b))
        f.add("warn", f"第 {a}–{b} 行", "L13",
              f"连续 {len(run)} 句都用典（第 {a}–{b} 行）："
              + "；".join(f"第 {n} 行「{by_line_no[n]['text']}」" for n in run)
              + "。连着借古人的话，听众会出戏。",
              "把其中至少一句改成白描：写眼前这个人正在做什么，不要借古人的故事。")

    # ④ 副歌首句 / 金句位用典
    hook_pos = set(l11.get("hook_positions", []))
    for sec in sections:
        if sec["kind"] == "chorus":
            hook_pos.add((sec["name"], 1))
    for h in hits:
        if (h["section"], h["pos"]) in hook_pos:
            info["hook_hits"].append(h)
            f.add("warn", f"{h['section']} 第 {h['pos']} 句", "L13",
                  f"金句位用典：「{h['name']}」（{h['source']}）——副歌首句/金句位必须是你自己的话。",
                  "把典挪到主歌或桥，金句位改成「具体物象 + 动词」的自造句；"
                  "先问：删掉这个典，这句还有没有画面？")

    # ⑤ 同一典故重复
    name_counts: dict[str, list[dict]] = {}
    for h in hits:
        name_counts.setdefault(h["name"], []).append(h)
    for name, hs in name_counts.items():
        if len(hs) >= 2:
            info["repeats"].append((name, len(hs)))
            f.add("error", f"第 {'、'.join(str(x['line_no']) for x in hs)} 行", "L13",
                  f"同一典故「{name}」（{hs[0]['source']}）重复用了 {len(hs)} 次——重复用典＝没词了。",
                  "只保留一次；第二次出现的地方说明你没想清楚要表达什么，换成一个动作或实物。")
    return info


def rule_l14(sections: list[dict], f: Findings, hits: list[dict]) -> dict:
    """L14 核心表达：①核心贯穿（至少 1 个物象/题旨词 ≥2 次）；②至少 1 句自造金句。

    另给 info「删典测试」清单：逐个列出含典的句子，自动粗判删典后是否还成立，供人复核。
    """
    lines = flatten_lines(sections)
    info = {"core_words": [], "core_max": 0, "self_made": [], "hook_checked": 0}

    # ① 核心贯穿
    counts: dict[str, int] = {}
    for w in CONCRETE_IMAGE + TOPIC_WORDS:
        c = sum(ln["raw"].count(w) for ln in lines)
        if c:
            counts[w] = c
    top = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0])))
    info["core_words"] = top[:8]
    info["core_max"] = top[0][1] if top else 0
    if not top or top[0][1] < 2:
        seen = "、".join(w for w, _ in top[:6]) or "无"
        f.add("warn", "全篇", "L14",
              f"没有贯穿全篇的核心：具体物象/题旨词最高频只出现 {info['core_max']} 次（{seen}），"
              "每一句在写各的东西，全篇没有「核心表达」。",
              "选一个物象（灯/雨/信/门…）或一个题旨词（故人/归期/旧年…）让它出现 ≥2 次，"
              "首段埋、副歌回扣；它就是听众记住这首歌的钩子。")

    # ② 自造金句（副歌/尾声的首句与末句，≥5 字）
    hit_lines = {h["line_no"] for h in hits}
    hook_lines: list[tuple[str, int, dict]] = []
    for sec in sections:
        if sec["kind"] not in ("chorus", "outro"):
            continue
        for i, ln in enumerate(sec["lines"], 1):
            if i != 1 and i != len(sec["lines"]):
                continue
            if len(ln["chars"]) < 5:
                continue
            hook_lines.append((sec["name"], i, ln))
    info["hook_checked"] = len(hook_lines)
    for sec_name, i, ln in hook_lines:
        if ln["line_no"] in hit_lines:
            continue
        has_image = any(w in ln["raw"] for w in CONCRETE_IMAGE)
        has_verb = any(ch in VERB_CHARS for ch in ln["text"])
        if has_image and has_verb:
            info["self_made"].append(f"{sec_name} 第 {i} 句「{ln['text']}」")
    if hook_lines and not info["self_made"]:
        f.add("warn", "全篇", "L14",
              "金句位全靠典故/名词：副歌与尾声的首末句里，没有一句是「≥5 字 + 不含典 + 有物象 + 有动词」的自造句。",
              "写一句自己的话压副歌首句：具体物象 + 一个动词 + 一层反常识"
              "（例：「茶凉了，杯沿还是你咬过的形状」）。")

    # ③ info：删典测试
    line_map = {ln["line_no"]: ln for ln in lines}
    for h in hits[:12]:
        ln = line_map.get(h["line_no"])
        if not ln:
            continue
        rest = ln["text"].replace(h["key"], "")
        ok = len(rest) >= 3 and (
            any(w in rest for w in CONCRETE_IMAGE) or any(ch in VERB_CHARS for ch in rest))
        f.add("info", f"第 {h['line_no']} 行", "L14",
              f"删典测试：「{ln['text']}」删掉「{h['key']}」后 → "
              f"{'仍成立（可以删）' if ok else '不成立（这句只靠典撑着，需重写）'}。",
              "成立就删掉这个典；不成立说明这句没有自己的动作/物象，先把它写成具体的事。")
    return info


# ================================================================ 门禁清单

GATES: list[tuple[str, list[str]]] = [
    ("① 韵脚一致（十三辙）", ["L1"]),
    ("② 句长合规（槽位 ±2 / 段落区间）", ["L2"]),
    ("③ 无倒字（句尾与重音字）", ["L3"]),
    ("④ 重复可控（同句重字/全篇高频实词）", ["L4"]),
    ("⑤ 无伪古风堆砌", ["L5"]),
    ("⑥ 无时空错乱（现代词）", ["L6"]),
    ("⑦ 典故无误用", ["L7"]),
    ("⑧ 无生僻字（GB2312 一级字内）", ["L8"]),
    ("⑨ 结构完整（主歌+副歌+副歌再现）", ["L9"]),
    ("⑩ 无 AI 味（四字套话/同义堆叠）", ["L10"]),
    ("⑪ 金句有具体物象", ["L11"]),
    ("⑫ 无断韵（句中气口）", ["L12"]),
    ("⑬ 用典密度与堆砌（≤3 处、同段 ≤1、金句位不用、不重复）", ["L13"]),
    ("⑭ 核心表达（核心贯穿 + 自造金句）", ["L14"]),
]

RULE_BRIEF = {
    "L1": "韵脚按十三辙归辙；同段换辙 error，跨段换辙 warn",
    "L2": "句长：有 --slots 按 syllables±2；无槽位按段落区间",
    "L3": "倒字：有 --jp 时按四声走向表查句尾/重音字",
    "L4": "重复：同句重字 >2、二字词 ≥4 次、单字实词 ≥6 次（重复段只算一次）",
    "L5": "伪古风词库（44 词）计数与同句堆叠",
    "L6": "现代词黑名单（54 词）时空校验",
    "L7": "典故正误表（57 条）疑似误用（密度见 L13）",
    "L8": "生僻字：GB2312 一级字表外报 warn",
    "L9": "结构：主歌/副歌/副歌再现（有 --slots 时按曲式判定副歌段数）",
    "L10": "AI 味：四字套话、抽象形容词、同义堆叠",
    "L11": "金句：副歌/尾声首末句（≥5 字）是否含具体物象（仅提示）",
    "L12": "断韵：句内气口意外押上别的辙",
    "L13": "用典配额：全篇 >3 error、=3 warn；同段 ≥2 warn；连续两句 warn；金句位 warn；同典重复 error",
    "L14": "核心表达：物象/题旨词至少 1 个 ≥2 次；副歌/尾至少有 1 句自造金句；附删典测试",
}


def gate_result(f: Findings, rules: list[str], executed: dict) -> tuple[str, str]:
    if any(not executed.get(code, True) for code in rules):
        return "⏭️", "未执行（缺 --jp）"
    rows = [r for r in f.for_rules(rules) if r["level"] in ("error", "warn")]
    if not rows:
        return "✅", "无问题"
    errs = [r for r in rows if r["level"] == "error"]
    wrs = [r for r in rows if r["level"] == "warn"]
    bits = []
    if errs:
        bits.append(f"error {len(errs)} 条")
    if wrs:
        bits.append(f"warn {len(wrs)} 条")
    first = rows[0]
    return "❌", f"{'、'.join(bits)}；首条：{first['rule']} {first['loc']}"


# ================================================================ 报告


def build_report(sections: list[dict], f: Findings, ctx: dict) -> tuple[str, bool]:
    errors = f.count("error")
    warns = f.count("warn")
    infos = f.count("info")
    n_modify = errors + warns
    executed = ctx["executed"]
    marks = [gate_result(f, rules, executed) for _, rules in GATES]
    all_pass = all(m != "❌" for m, _ in marks)  # 未执行（⏭️）不算失败
    deliverable = (errors == 0 and all_pass)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = flatten_lines(sections)

    L: list[str] = []
    L.append("# 中国风作词校验报告（lint_guofeng_lyric.py）")
    L.append("")
    L.append(f"- 词稿：{ctx['title']}")
    L.append(f"- 来源：{ctx['source']}")
    L.append(f"- 生成时间：{now}")
    L.append(f"- 段落：{len(sections)} 段；句数：{len(lines)} 句；"
             f"字数：{sum(len(ln['text']) for ln in lines)} 字")
    L.append(f"- 填词槽位：{ctx['slots_desc']}")
    L.append(f"- 旋律对照：{ctx['jp_desc']}")
    L.append("")
    if ctx["parse_notes"]:
        L.append("解析提示：")
        L.append("")
        for n in ctx["parse_notes"]:
            L.append(f"- {n}")
        L.append("")

    L.append("## 一、结论概览")
    L.append("")
    L.append("| 级别 | 条数 | 含义 |")
    L.append("|---|---|---|")
    L.append(f"| error | {errors} | 必须改，否则不可交付 |")
    L.append(f"| warn | {warns} | 建议改，影响质量 |")
    L.append(f"| info | {infos} | 仅提示，不影响判定 |")
    L.append("")
    if deliverable:
        L.append("**结论：可交付** —— 无 error，门禁全部通过（未执行的规则见第六节）。")
    elif errors:
        L.append(f"**结论：需修改 {n_modify} 处** —— 其中 error {errors} 条必须修。")
    else:
        L.append(f"**结论：需修改 {n_modify} 处** —— 无 error，但仍有 warn 未清。")
    L.append("")

    L.append("## 二、段落结构")
    L.append("")
    L.append("| # | 段落 | 类型 | 句数 | 每句字数 | 韵位（段内句号） |")
    L.append("|---|---|---|---|---|---|")
    for i, sec in enumerate(sections, 1):
        ns = [len(ln["text"]) for ln in sec["lines"]]
        rp = rhyme_line_numbers(sec)
        L.append(f"| {i} | {sec['name']} | {kind_name(sec['kind'])} | {len(ns)} | "
                 f"{'、'.join(str(x) for x in ns)} | "
                 f"{'第 ' + '、'.join(str(x) for x in rp) + ' 句' if rp else '—'} |")
    L.append("")
    L.append("> 韵位假设：主歌/桥/尾看偶句与段末句；副歌看第 1、2、4 句；句中 `|` 为气口。")
    L.append("")

    L.append("## 三、逐条发现")
    L.append("")
    rows = f.sorted_rows()
    if not rows:
        L.append("未发现任何问题（error/warn/info 均为 0）。可以直接定稿或进入 `lyric2jianpu.py` 谱曲。")
    else:
        L.append("| 级别 | 位置 | 规则 | 说明 | 修法 |")
        L.append("|---|---|---|---|---|")
        for r in rows:
            lvl = {"error": "error ❌", "warn": "warn ⚠️", "info": "info ℹ️"}.get(r["level"], r["level"])
            msg = str(r["msg"]).replace("|", "\\|")
            fix = str(r["fix"]).replace("|", "\\|")
            L.append(f"| {lvl} | {r['loc']} | {r['rule']} | {msg} | {fix} |")
    L.append("")

    L.append("## 四、韵脚与辙")
    L.append("")
    L.append("| 段落 | 句号 | 韵脚字 | 归辙 | 本节主韵 |")
    L.append("|---|---|---|---|---|")
    zhe_info = ctx["l1"]
    rows_z = zhe_info.get("rhyme_rows", [])
    if rows_z:
        for r in rows_z:
            main = zhe_info["section_zhe"].get(r["section"], "—")
            L.append(f"| {r['section']} | 第 {r['line']} 句 | {r['char']} | {r['zhe']} | {main} |")
    else:
        L.append("| — | — | — | — | — |")
    L.append("")
    if zhe_info.get("section_zhe"):
        L.append("各段主韵：" + "；".join(f"{k} → {v}" for k, v in zhe_info["section_zhe"].items()))
        L.append("")
    L.append("十三辙代表韵母速查：")
    L.append("")
    L.append("| 辙口 | 代表韵母 |")
    L.append("|---|---|")
    for z, mu in ZHE_INFO.items():
        L.append(f"| {z} | {mu} |")
    L.append("")

    L.append("## 五、规则执行明细（L1–L14）")
    L.append("")
    L.append("| 编号 | 规则摘要 | 结果 |")
    L.append("|---|---|---|")
    for code in [f"L{i}" for i in range(1, 15)]:
        if not executed.get(code, True):
            L.append(f"| {code} | {RULE_BRIEF[code]} | ⏭️ 未执行（未提供 --jp） |")
            continue
        hits = f.for_rules([code])
        if not hits:
            res = "✅ 通过"
        else:
            e = len([h for h in hits if h["level"] == "error"])
            w = len([h for h in hits if h["level"] == "warn"])
            i_ = len([h for h in hits if h["level"] == "info"])
            bits = []
            if e:
                bits.append(f"error {e}")
            if w:
                bits.append(f"warn {w}")
            if i_:
                bits.append(f"info {i_}")
            res = ("❌ " if (e or w) else "ℹ️ ") + " / ".join(bits)
        L.append(f"| {code} | {RULE_BRIEF[code]} | {res} |")
    L.append("")
    L.append("辅助统计：")
    L.append("")
    l5 = ctx["l5"]
    L.append(f"- L5 伪古风词：{l5['distinct']} 种 / {l5['total']} 处"
             + (f"（{'、'.join(w for w, _ in l5['words'][:8])}）" if l5["words"] else ""))
    L.append(f"- L7 典故：{len(ctx['l7']['used'])} 个"
             + (f"（{'、'.join(ctx['l7']['used'])}）" if ctx["l7"]["used"] else "")
             + f"；疑似误用 {ctx['l7']['misused']} 处")
    rare = ctx["l8"]["rare"]
    L.append(f"- L8 生僻字：{len(rare)} 个" + (f"（{'、'.join(ch for ch, _ in rare)}）" if rare else ""))
    top4 = ctx["l4"]["top"]
    L.append(f"- L4 高频实词 Top5：" + ("、".join(f"{ch}×{k}" for ch, k in top4) if top4 else "无"))
    L.append(f"- L10 套话密度：{ctx['l10']['density']} 个/百字"
             + (f"（{'、'.join(ctx['l10']['phrases'])}）" if ctx["l10"]["phrases"] else ""))
    if executed.get("L3"):
        L.append(f"- L3 对齐：{ctx['l3']['aligned_lines']} 句 / 旋律 {ctx['l3']['notes']} 音")
    l13 = ctx["l13"]
    L.append(f"- L13 用典：{l13['total']} 处"
             + ("（" + "、".join(f"{h['name']}@第{h['line_no']}行" for h in l13["hits"][:8]) + "）"
                if l13["hits"] else "")
             + f"；配额 ≤2 处 / 同段 ≤1 处；同典重复 {len(l13['repeats'])} 个")
    l14 = ctx["l14"]
    core = l14["core_words"]
    L.append(f"- L14 核心贯穿：" + ("、".join(f"{w}×{k}" for w, k in core[:6]) if core else "无重复物象")
             + f"；最高频 {l14['core_max']} 次；自造金句 {len(l14['self_made'])} 句"
             + (f"（{l14['self_made'][0]}）" if l14["self_made"] else ""))
    L.append("")

    L.append("## 六、门禁清单")
    L.append("")
    L.append("| # | 门禁 | 判定 | 依据 |")
    L.append("|---|---|---|---|")
    for (title, rules), (mark, why) in zip(GATES, marks):
        L.append(f"| {title.split(' ', 1)[0]} | {title.split(' ', 1)[1]} | {mark} | {why} |")
    L.append("")
    passed = sum(1 for m, _ in marks if m == "✅")
    skipped = sum(1 for m, _ in marks if m == "⏭️")
    L.append(f"门禁通过数：**{passed}/{len(GATES) - skipped}**（跳过 {skipped} 条）；"
             f"error **{errors}** 条 / warn **{warns}** 条。")
    L.append("")
    if deliverable:
        L.append("**结论：可交付**")
    else:
        L.append(f"**结论：需修改 {n_modify} 处**")
    L.append("")

    L.append("---")
    L.append("")
    L.append("下一步：")
    L.append("")
    L.append("1. 按第三节「修法」先清 error，再清 warn；")
    L.append("2. 重跑：`python scripts/lint_guofeng_lyric.py --input 你的词.lyr`，直到结论变成「可交付」；")
    L.append("3. 要成曲：`python scripts/lyric2jianpu.py --input 你的词.lyr --key D --mode yu --out 你的.jp`；")
    L.append("4. 要把词唱进现成旋律：先 `python scripts/jianpu2lyricslots.py --input 曲.jp`，"
             "再 `--slots` 校验句长。")
    L.append("")
    return "\n".join(L), deliverable


# ================================================================ CLI


def _demo_out_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "guofeng-lyric-out"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = SCRIPT_DIR
    return d


def default_report(input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path.with_name(input_path.stem + "-校验.md")
    return _demo_out_dir() / "lint-guofeng-lyric.md"


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="lint_guofeng_lyric.py",
        description="中国风作词校验：L1–L14 + 门禁清单。纯标准库。",
        epilog=("示例：\n"
                "  python lint_guofeng_lyric.py                        # demo → <临时目录>/guofeng-lyric-out/\n"
                "  python lint_guofeng_lyric.py --input 我的词.lyr     # → 同目录/我的词-校验.md\n"
                "  python lint_guofeng_lyric.py --input 我的词.lyr --slots 江南雨.slots.json\n"
                "  python lint_guofeng_lyric.py --input 我的词.lyr --jp 江南雨.jp\n"
                "退出码：0 无 error；1 有 error；2 参数/文件问题"),
    )
    parser.add_argument("--input", help="输入歌词文件（.lyr）")
    parser.add_argument("--report", help="输出 Markdown 报告路径（默认见上）")
    parser.add_argument("--slots", help="填词槽位 JSON（.slots.json），用于 L2 句长校验")
    parser.add_argument("--jp", help="简谱 DSL（.jp），用于 L3 倒字校验")
    parser.add_argument("--allow-change-rhyme", action="store_true", help="允许跨段转韵（同段换辙仍报 error）")
    parser.add_argument("--allow-modern", action="store_true", help="允许现代词（L6 降为 info）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 词校验")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    report_path = Path(args.report).expanduser() if args.report else default_report(input_path)
    slots_path = Path(args.slots).expanduser() if args.slots else None
    jp_path = Path(args.jp).expanduser() if args.jp else None

    try:
        for p, what in ((input_path, "歌词"), (slots_path, "槽位 JSON"), (jp_path, "简谱")):
            if p is not None and not p.exists():
                print(f"❌ 找不到{what}文件：{p}", file=sys.stderr)
                print("下一步：确认路径；或先跑不带参数的 `python lint_guofeng_lyric.py` 看 .lyr 格式。", file=sys.stderr)
                return 2

        if input_path is not None:
            text = read_text_file(input_path)
            source = str(input_path)
            title = input_path.stem
        else:
            text = DEFAULT_DEMO_LYR
            source = "内置 demo（相思 · 言前辙 · 22 句）"
            title = "demo-相思"

        sections, parse_notes = parse_lyr(text)
        if not sections:
            print("❌ 没有解析到歌词：", file=sys.stderr)
            for n in parse_notes:
                print(f"   {n}", file=sys.stderr)
            print("下一步：确认每行是 `字:调` 写法（如 `江:1 南:2 雨:3`），段名用 `[主歌A]`。", file=sys.stderr)
            return 2

        slots = None
        slot_sections: list[str] | None = None
        slots_desc = "未提供（L2 按段落区间校验）"
        if slots_path is not None:
            try:
                loaded = load_slots(slots_path)
                slots = loaded["lines"]
                slot_sections = loaded["sections"]
                slots_desc = f"{slots_path.name}（{len(slots)} 句 / {len(slot_sections)} 段）"
            except Exception as exc:
                print(f"❌ 槽位 JSON 解析失败：{exc}", file=sys.stderr)
                print("下一步：槽位应由 `jianpu2lyricslots.py` 生成；不要手改字段名。", file=sys.stderr)
                return 2

        jp_notes = None
        jp_desc = "未提供（L3 跳过）"
        if jp_path is not None:
            try:
                jp_notes, _headers = parse_jp_notes(read_text_file(jp_path))
                if not jp_notes:
                    raise ValueError("没有解析到 @melody 音符")
                jp_desc = f"{jp_path.name}（{len(jp_notes)} 个旋律音）"
            except Exception as exc:
                print(f"❌ 简谱解析失败：{exc}", file=sys.stderr)
                print("下一步：确认 .jp 有 @melody 块（写法 `6:2 1':1 | 3':2 ...`）。", file=sys.stderr)
                return 2

        f = Findings()
        l1 = rule_l1(sections, f, args.allow_change_rhyme)
        l2 = rule_l2(sections, f, slots)
        l3 = rule_l3(sections, f, jp_notes)
        l4 = rule_l4(sections, f)
        l5 = rule_l5(sections, f)
        l6 = rule_l6(sections, f, args.allow_modern)
        l7 = rule_l7(sections, f)
        l8 = rule_l8(sections, f)
        l9 = rule_l9(sections, f, slot_sections)
        l10 = rule_l10(sections, f)
        l11 = rule_l11(sections, f)
        l12 = rule_l12(sections, f, l1["section_zhe"])
        l13 = rule_l13(sections, f, l11)
        l14 = rule_l14(sections, f, l13["hits"])

        executed = {f"L{i}": True for i in range(1, 15)}
        if not jp_notes:
            executed["L3"] = False

        ctx = {
            "title": title, "source": source, "parse_notes": parse_notes,
            "slots_desc": slots_desc, "jp_desc": jp_desc,
            "l1": l1, "l2": l2, "l3": l3, "l4": l4, "l5": l5, "l6": l6,
            "l7": l7, "l8": l8, "l9": l9, "l10": l10, "l11": l11, "l12": l12,
            "l13": l13, "l14": l14,
            "executed": executed,
        }
        report, deliverable = build_report(sections, f, ctx)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")

        errors = f.count("error")
        warns = f.count("warn")
        infos = f.count("info")
        print("")
        print("=" * 62)
        print(f"📋 歌词校验完成：{title}")
        print(f"   来源：{source}")
        print(f"   error {errors} 条 / warn {warns} 条 / info {infos} 条")
        for r in f.sorted_rows():
            if r["level"] == "error":
                print(f"   ❌ {r['rule']} {r['loc']}：{r['msg'][:52]}")
        print(f"   报告：{report_path}")
        print(f"   结论：{'可交付' if deliverable else f'需修改 {errors + warns} 处'}")
        print("=" * 62)
        print("下一步：按报告「修法」改词 → 重跑本脚本 → 结论「可交付」后再谱曲/填槽位。")
        return 1 if errors else 0
    except SystemExit:
        raise
    except Exception as exc:  # 任何输入都不抛 traceback
        print(f"❌ 校验失败：{exc}", file=sys.stderr)
        print("下一步：① 先用 --demo 确认脚本正常；② 检查 .lyr 是否为 `字:调` 写法、"
              "段名是否用 `[主歌A]`；③ 把这段报错原文发给开发者。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
