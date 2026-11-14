#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""guofeng_blueprint.py —— 中国风创作蓝图生成（JSON + Markdown）

纯标准库（argparse/json/pathlib/datetime，无任何第三方依赖）。
输入 JSON **全部字段可选**，最小必填 = 空对象 `{}`；无参数 / --demo 直接出完整蓝图。

用法：
  python guofeng_blueprint.py
        无参数 = demo，输出到系统临时目录 guofeng-music-out/
                 guofeng-blueprint.json + guofeng-blueprint.md（真实路径见输出）
  python guofeng_blueprint.py --demo
        同上（显式 demo）
  python guofeng_blueprint.py --input 需求.json
        输出 同目录/需求-蓝图.json + 需求-蓝图.md
  python guofeng_blueprint.py --input 需求.json --out-json 蓝图.json --out-md 蓝图.md
  python guofeng_blueprint.py --help

输入字段（全部可选）：
  theme        题材，如「边关」「江南雨」          缺省：空
  style        5 套配方 id：shuqing/gudian/ranxi/guochao/peiyue   缺省：shuqing
  mood         情绪                               缺省：由 style 推
  duration_sec 时长 30–600 秒                     缺省：180（非法值取默认并提示）
  bpm          速度 40–200                        缺省：由 style 推
  key          调，C/D/E/F/G/A/B，可带 #/b         缺省：D
  instrument   主奏乐器 id（见 SPEC §4）           缺省：由 style 推
  vocal        是否含人声（true/false）            缺省：false
  with_xiqu    是否戏腔（true/false）              缺省：false
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # 脚本自身目录：不依赖 cwd（SPEC §7）

VERSION = "1.0.0"
SKILL_ID = "guofeng-music-composer"

# ---------------------------------------------------------------- SPEC §4 乐器表

INSTRUMENTS = {
    "di":       {"name": "笛",      "program": 73,  "range": (0, 21),   "gm": "73 Flute",
                 "persona": "明亮、开阔、田园"},
    "xiao":     {"name": "箫",      "program": 75,  "range": (0, 21),   "gm": "75 Pan Flute",
                 "persona": "幽远、孤独"},
    "sheng":    {"name": "笙",      "program": 71,  "range": (0, 19),   "gm": "71 Bassoon 近似（GM 无笙）",
                 "persona": "和气、和声铺底"},
    "suona":    {"name": "唢呐",    "program": 111, "range": (0, 24),   "gm": "111 Shanai",
                 "persona": "爆、喜庆、悲壮"},
    "guan":     {"name": "管子",    "program": 68,  "range": (2, 21),   "gm": "68 Oboe",
                 "persona": "苍凉"},
    "xun":      {"name": "埙",      "program": 79,  "range": (0, 16),   "gm": "79 Ocarina",
                 "persona": "古朴、呜咽"},
    "dizi_low": {"name": "曲笛",    "program": 73,  "range": (4, 19),   "gm": "73 Flute",
                 "persona": "温润（降八度写法）"},
    "guzheng":  {"name": "古筝",    "program": 107, "range": (0, 28),   "gm": "107 Koto",
                 "persona": "颗粒、刮奏、流水"},
    "guqin":    {"name": "古琴",    "program": 107, "range": (0, 12),   "gm": "107 Koto",
                 "persona": "沉、散、留白"},
    "pipa":     {"name": "琵琶",    "program": 105, "range": (0, 26),   "gm": "105 Banjo（或 104 Sitar）",
                 "persona": "颗粒、轮指、武曲"},
    "erhu":     {"name": "二胡",    "program": 110, "range": (-5, 24),  "gm": "110 Fiddle",
                 "persona": "悲、倾诉、如歌"},
    "zhonghu":  {"name": "中胡",    "program": 110, "range": (0, 19),   "gm": "110 Fiddle",
                 "persona": "厚、苍"},
    "yangqin":  {"name": "扬琴",    "program": 15,  "range": (0, 26),   "gm": "15 Dulcimer",
                 "persona": "清脆、点奏"},
    "ruan":     {"name": "阮",      "program": 105, "range": (0, 14),   "gm": "105 Banjo",
                 "persona": "圆润中声"},
    "daigu":    {"name": "大鼓",    "program": None, "range": None,     "gm": "ch10",
                 "persona": "气势、心跳"},
    "luogu":    {"name": "锣鼓组",  "program": None, "range": None,     "gm": "ch10",
                 "persona": "戏曲、板眼"},
    "strings":  {"name": "弦乐组",  "program": 48,  "range": None,     "gm": "48 String Ensemble",
                 "persona": "托底、电影感"},
    "pad":      {"name": "合成 pad", "program": 89,  "range": None,     "gm": "89 Pad",
                 "persona": "国潮电子氛围"},
    "piano":    {"name": "钢琴",    "program": 1,   "range": None,     "gm": "1 Acoustic Grand",
                 "persona": "现代四大件"},
}

# SPEC §5 打击乐预设
PERC_PRESETS = ["锣鼓-中板", "锣鼓-快板", "散板散点", "堂鼓-推进", "军鼓-4/4", "电子-国潮", "无"]

DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}
PENTA_DEGREES = ["1", "2", "3", "5", "6"]
MODES = {
    "gong": {"name": "宫", "tonic_degree": 1},
    "shang": {"name": "商", "tonic_degree": 2},
    "jue": {"name": "角", "tonic_degree": 3},
    "zhi": {"name": "徵", "tonic_degree": 5},
    "yu": {"name": "羽", "tonic_degree": 6},
}
MODE_COLOR = {
    "gong": "宫调式：明亮、开阔、端正，适合家国/庆典/少年气；落音 1。",
    "shang": "商调式：清冷、锐、带一点悲凉和进行感；落音 2。",
    "jue": "角调式：偏暗、含蓄、疑问感强，古风戏腔常用；落音 3。",
    "zhi": "徵调式：热烈、外放、有民间锣鼓味，燃系首选；落音 5。",
    "yu": "羽调式：柔、哀而不伤、最“中国风”的默认色彩，抒情首选；落音 6。",
}
SCALES = {
    "wusheng": {"name": "五声（无偏音）", "bianyin": [], "semis": [0, 2, 4, 7, 9]},
    "qingyue": {"name": "清乐（加 4、7）", "bianyin": ["4", "7"], "semis": [0, 2, 4, 5, 7, 9, 11]},
    "yayue":   {"name": "雅乐（加 #4、7）", "bianyin": ["#4", "7"], "semis": [0, 2, 4, 6, 7, 9, 11]},
    "yanyue":  {"name": "燕乐（加 4、b7）", "bianyin": ["4", "b7"], "semis": [0, 2, 4, 5, 7, 9, 10]},
}
NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

CHORD_SUFFIX_DISPLAY = {
    "": "", "m": "m", "dim": "dim", "sus2": "sus2", "sus4": "sus4", "7": "7",
    "m7": "m7", "maj7": "maj7", "6": "6", "m6": "m6", "add9": "add9", "add2": "add2",
    "9": "9", "omit3": "omit3",
}
CHORD_RE = re.compile(r"^([#b]?)([1-7])([A-Za-z0-9]*)$")
CHORD_SUFFIXES = sorted(CHORD_SUFFIX_DISPLAY.keys(), key=len, reverse=True)

# ---------------------------------------------------------------- SPEC §6 风格配方（5 套）

STYLE_RECIPES = {
    "shuqing": {
        "name": "抒情国风",
        "modes": ["yu", "gong"],
        "scale": "qingyue",
        "bpm_range": (66, 80),
        "bpm": 72,
        "meter": "4/4",
        "main_instrument": "xiao",
        "sub_instruments": ["guzheng", "strings", "ruan", "daigu", "pad"],
        "mood": "含蓄、思念、雨夜旧巷（哀而不伤）",
        "feel": "散起-入板；长音留白，句子之间有呼吸",
        "perc_preset": "锣鼓-中板",
        "vocal_default": True,
        "structure": [
            ("前奏", 2, "建立音色与动机", "稀疏", "单线条 + 泛音"),
            ("主歌", 4, "叙事铺陈，人声最低音区", "中", "旋律 + 分解和弦"),
            ("预副", 2, "抬升情绪，加低音推进", "中密", "加入弦乐长音"),
            ("副歌", 4, "主题爆发，民乐与弦乐叠奏", "密", "全编制"),
            ("间奏", 2, "留白转场，主奏 solo", "稀疏", "单线条 + 刮奏"),
            ("副歌", 4, "再爆发，加高八度叠奏", "更密", "全编制 + 高八度"),
            ("桥", 2, "转折，换节奏型", "中", "断奏 + 留白"),
            ("副歌", 4, "最高潮，唢呐/笛上翻", "密", "全编制 + 打击加强"),
            ("尾", 2, "收束余韵，回到单线条", "稀疏", "主奏渐弱 + 泛音"),
        ],
        "layers": [
            ("主奏", "xiao", ["前奏", "间奏", "副歌", "尾"], "主题陈述与回应句", "中偏左",
             "副歌用高八度叠奏一层，不要全程铺满"),
            ("副奏", "guzheng", ["主歌", "预副", "副歌", "间奏"], "颗粒点描、刮奏转场", "中偏右",
             "刮奏只用在段落交界，别当填充"),
            ("和声", "strings", ["预副", "副歌", "桥"], "长音托底、情绪推高", "宽（左右）",
             "副歌才进，主歌不要压人声"),
            ("低音", "ruan", ["主歌", "副歌"], "根音/五度走动，稳住和声底座", "中", "与底鼓对齐"),
            ("氛围", "pad", ["前奏", "间奏", "尾"], "空气感、雨声质感", "宽（左右）", "音量低，别抢主奏"),
            ("打击", "daigu", ["预副", "副歌"], "心跳感底鼓 + 轻击", "中", "散板段不用鼓"),
        ],
        "chords": [
            ("4536251 五声化（首选）",
             ["4add9", "5add9", "3m7", "6add9", "2m7", "5sus4", "1add9"], "副歌 / 主歌B",
             "五声化和弦避免 4、7 做和弦音，add9/sus 让色彩“空”而不“洋”"),
            ("6m-1-5-6m 循环",
             ["6m7", "1add9", "5sus4", "6m7"], "主歌", "羽调式最稳的循环，落音回 6，情绪不散"),
            ("1-5-6m-4 叙事",
             ["1add9", "5add9", "6add9", "4add9"], "前奏 / 尾", "宫起羽落，开场明亮、收束微凉"),
        ],
        "mix": [
            "主奏箫：中高频 2–4kHz 略提 2dB 出“气息”，低频 200Hz 以下切掉",
            "古筝：与人声 1–3kHz 打架时 -2dB 让位人声",
            "弦乐组：只做 200–800Hz 的托底，高频衰减 3dB 避免“糊”",
            "底鼓与大鼓错开：底鼓走低频（60–80Hz），大鼓走 100–160Hz",
            "整体：混响 1.8–2.4s 大房间，前奏/尾干湿比更湿",
        ],
        "pitfalls": [
            "主奏乐器全程铺满 → 中国风要“留白”，主奏每句留 1 拍呼吸",
            "偏音 4/7 做落音或长音 → 立刻“洋味/和风味”，用 lint 的 M1/M2 卡住",
            "副歌只靠加音量推 → 要靠加声部与音区（弦乐、高八度叠奏）推",
        ],
    },
    "gudian": {
        "name": "古风戏腔",
        "modes": ["yu", "jue"],
        "scale": "qingyue",
        "bpm_range": (72, 92),
        "bpm": 84,
        "meter": "4/4",
        "main_instrument": "erhu",
        "sub_instruments": ["di", "pipa", "strings", "ruan", "luogu"],
        "mood": "旧梦、戏台、一瞥惊鸿（含拖腔）",
        "feel": "板眼清晰；戏腔段可散起，拖腔处留白",
        "perc_preset": "锣鼓-中板",
        "vocal_default": True,
        "structure": [
            ("前奏", 2, "戏台氛围，锣鼓点题", "稀疏", "锣鼓 + 单线条"),
            ("主歌", 4, "低声区叙事，字多腔少", "中", "旋律 + 琵琶点"),
            ("副歌", 4, "抬升，二胡与笛叠奏", "密", "全编制"),
            ("戏腔段", 4, "戏腔拖腔，人声华彩", "中（疏密对比）", "二胡跟腔 + 锣鼓点缀"),
            ("间奏", 2, "琵琶轮指转场", "稀疏", "单线条 + 轮指"),
            ("副歌", 4, "再爆发，戏腔加花", "密", "全编制"),
            ("尾", 2, "拖腔收尾，留白", "稀疏", "二胡长音渐弱"),
        ],
        "layers": [
            ("主奏", "erhu", ["前奏", "主歌", "副歌", "戏腔段", "尾"], "如歌倾诉，戏腔段跟腔", "中偏左",
             "戏腔段用滑音、揉弦模仿人声拖腔"),
            ("副奏", "di", ["副歌", "戏腔段", "间奏"], "高八度呼应、戏腔对句", "中偏右",
             "戏腔段只在对句进，不要盖住人声"),
            ("点描", "pipa", ["主歌", "间奏"], "轮指、点奏做“戏台”颗粒感", "中偏右", "主歌每句尾点 1–2 下"),
            ("和声", "strings", ["副歌", "戏腔段"], "长音托底", "宽（左右）", "戏腔段压低音量"),
            ("低音", "ruan", ["主歌", "副歌"], "根音走动", "中", "与锣鼓重拍对齐"),
            ("打击", "luogu", ["前奏", "戏腔段", "尾"], "板眼、锣鼓点", "中", "戏腔段只在句读处一击"),
        ],
        "chords": [
            ("6m-4-5-6m 戏腔拖腔",
             ["6m", "4sus2", "5sus4", "6m"], "戏腔段", "羽调式收束，sus 让拖腔有空间不撞音"),
            ("1-6m-4-5 古风四和弦",
             ["1add9", "6m7", "4add9", "5sus4"], "主歌", "最常用的古风循环，宫起羽落"),
            ("6m-5-4-1 下行",
             ["6m", "5sus4", "4sus2", "1add9"], "副歌", "下行级进自带“叹”的语气，配戏腔拖腔"),
        ],
        "mix": [
            "二胡：800Hz–2kHz 提 1.5dB 出“鼻音”，4kHz 以上略降避免刺耳",
            "戏腔人声：混响 2.6–3.2s、预延迟 30ms，做出“戏台空间”",
            "锣鼓：低频收窄，只保留 100–3kHz 的“板眼”感",
            "琵琶：与二胡同频段时，琵琶 -2dB、并做左右分离",
            "人声与二胡同奏时，二胡降 3dB 做“影子声部”",
        ],
        "pitfalls": [
            "戏腔写成普通流行唱 → 必须有拖腔、滑音与句尾甩腔，否则只是“古风词 + 流行曲”",
            "锣鼓从头敲到尾 → 只在板眼、句读与段落交界处用",
            "二胡全程高音区 → 主歌降到中低音区，副歌再上翻",
        ],
    },
    "ranxi": {
        "name": "燃系国风",
        "modes": ["gong", "zhi"],
        "scale": "qingyue",
        "bpm_range": (96, 132),
        "bpm": 120,
        "meter": "4/4",
        "main_instrument": "suona",
        "sub_instruments": ["pipa", "daigu", "strings", "piano", "di"],
        "mood": "战场、鼓阵、少年将军（明亮有冲劲）",
        "feel": "强拍推进，鼓点密；副歌前滚镲渐快",
        "perc_preset": "堂鼓-推进",
        "vocal_default": True,
        "structure": [
            ("前奏", 2, "鼓阵开场，唢呐点题", "中", "鼓 + 短促齐奏"),
            ("主歌", 4, "低声区推进，字正腔圆", "中", "旋律 + 低音切分"),
            ("预副", 2, "滚镲渐快，情绪蓄力", "密", "打击加密 + 弦乐上行"),
            ("副歌", 4, "唢呐主奏爆发，全编制", "密", "全编制"),
            ("间奏", 2, "琵琶轮指 + 鼓 solo", "中密", "节奏型变化"),
            ("桥", 2, "留白一拍再冲，戏剧反转", "中", "断奏 + 停拍"),
            ("副歌", 4, "最高潮，唢呐上翻一层", "密", "全编制 + 高八度"),
            ("尾", 2, "重击收束，一记大锣", "中", "齐奏断句"),
        ],
        "layers": [
            ("主奏", "suona", ["前奏", "副歌", "间奏", "尾"], "主题爆发，副歌上翻高八度", "中偏左",
             "唢呐只在副歌满编，主歌让位人声"),
            ("副奏", "pipa", ["主歌", "副歌", "间奏"], "轮指、扫弦推节奏", "中偏右", "扫弦只落重拍"),
            ("和声", "strings", ["预副", "副歌", "桥"], "上行长音推情绪", "宽（左右）", "预副做上行音阶"),
            ("低音", "piano", ["主歌", "副歌"], "八度低音 + 切分", "中", "与底鼓同点"),
            ("打击", "daigu", ["前奏", "预副", "副歌", "间奏", "尾"], "鼓阵、滚镲渐快", "中", "预副最后一小节滚镲"),
            ("色彩", "di", ["间奏", "副歌"], "高八度对句", "中偏右", "只在副歌后句进"),
        ],
        "chords": [
            ("1-6m-4-5 大调推进",
             ["1", "6m", "4", "5"], "副歌", "宫调式正格进行，最“燃”，和弦用三和弦保持力度"),
            ("6m-4-1-5 战场",
             ["6m", "4", "1", "5"], "主歌", "羽起宫落，推进感强又不太“洋”"),
            ("1-5-6m-4 高潮",
             ["1add9", "5sus4", "6m7", "4add9"], "最高潮 / 尾", "add9/sus 让高潮不老套，保留中国风色彩"),
        ],
        "mix": [
            "唢呐：波形最“炸”，2–5kHz 提 2dB，低频切 200Hz 以下避免与鼓打架",
            "大鼓：60–100Hz 给“胸口”，300Hz 略降避免糊",
            "琵琶：高频 5kHz 略提做“颗粒”，与人声冲突时侧链压缩",
            "弦乐：副歌做宽（左右 80%），主歌收窄",
            "整体：鼓组压缩比 4:1，副歌响度比主歌高 2–3dB",
        ],
        "pitfalls": [
            "全程满编制轰炸 → 主歌必须减声部，副歌才有爆发空间",
            "唢呐与人声同音区硬碰 → 副歌人声降三度或唢呐升八度",
            "鼓点密但没重音 → 重拍必须有低频（底鼓/大鼓）落地",
        ],
    },
    "guochao": {
        "name": "国潮电子",
        "modes": ["zhi", "gong"],
        "scale": "qingyue",
        "bpm_range": (88, 110),
        "bpm": 100,
        "meter": "4/4",
        "main_instrument": "di",
        "sub_instruments": ["guzheng", "pad", "daigu", "pipa", "piano"],
        "mood": "赛博、霓虹、国潮酷感",
        "feel": "四踩底鼓 + 电子律动；drop 要有“空一拍再进”",
        "perc_preset": "电子-国潮",
        "vocal_default": False,
        "structure": [
            ("前奏", 2, "电子氛围 + 民乐采样点题", "中", "pad + 单线条"),
            ("drop", 4, "四踩底鼓进，民乐主题炸开", "密", "全编制电子"),
            ("主歌", 4, "留出人声空间，律动为主", "中", "鼓 + 低音 + 点描"),
            ("副歌", 4, "民乐主题 + 电子编曲", "密", "全编制"),
            ("间奏", 2, "滤波扫频转场", "中", "电子音效"),
            ("drop", 4, "第二次 drop，加高八度民乐", "更密", "全编制 + 高八度"),
            ("尾", 2, "抽掉鼓，留 pad 与单线条", "稀疏", "氛围收束"),
        ],
        "layers": [
            ("主奏", "di", ["前奏", "drop", "副歌", "尾"], "民乐主题 hook", "中偏左",
             "drop 段用短促断奏，不要长音"),
            ("循环", "guzheng", ["主歌", "drop", "副歌"], "五声琶音循环，国潮招牌", "中偏右",
             "琶音用五声音阶，避免半音"),
            ("氛围", "pad", ["前奏", "主歌", "间奏", "尾"], "铺底与滤波扫频", "宽（左右）", "侧链跟着底鼓呼吸"),
            ("打击", "daigu", ["drop", "副歌"], "四踩底鼓 + 电子鼓", "中", "drop 前空一拍"),
            ("低音", "piano", ["主歌", "副歌"], "808 式低音走动", "中", "与底鼓同步"),
            ("色彩", "pipa", ["间奏", "drop"], "轮指采样切片", "中偏右", "做 stutter 切片"),
        ],
        "chords": [
            ("6m-1-4-5 drop",
             ["6m7", "1add9", "4add9", "5sus4"], "drop", "羽起宫落，drop 段最有冲击力"),
            ("1-5-6m-4 循环",
             ["1add9", "5sus4", "6m7", "4add9"], "副歌", "电子循环最顺，配五声琶音不冲突"),
            ("4-5-6m-1 上行",
             ["4add9", "5sus4", "6m7", "1add9"], "主歌", "上行蓄力，接 drop 更顺"),
        ],
        "mix": [
            "笛：电子编曲里要“亮”，3–6kHz 提 2dB，加短延迟做空间",
            "古筝琶音：高通 300Hz，避免与 808 低频打架",
            "pad：侧链压缩跟随底鼓（-4dB，release 80ms）",
            "808/低音：60–90Hz 集中，做饱和增加二次谐波",
            "整体：drop 段低频提升 3dB，主歌收窄做对比",
        ],
        "pitfalls": [
            "电子音色盖住民乐 → 民乐必须留在 1–4kHz 的“身份频段”",
            "五声旋律配半音化电子和声 → 和弦也用五声化（add9/sus/omit3）",
            "drop 前没有留白 → drop 前一拍抽掉鼓，落点才有劲",
        ],
    },
    "peiyue": {
        "name": "新民乐配乐",
        "modes": ["gong", "yu"],
        "scale": "qingyue",
        "bpm_range": (60, 90),
        "bpm": 76,
        "meter": "4/4",
        "main_instrument": "dizi_low",
        "sub_instruments": ["erhu", "pipa", "guzheng", "strings", "daigu"],
        "mood": "大气、叙事、画面感（纪录片/游戏配乐）",
        "feel": "慢起，层层叠加；段落之间有明确画面转场",
        "perc_preset": "堂鼓-推进",
        "vocal_default": False,
        "structure": [
            ("引子", 4, "单线条点题，留白", "稀疏", "单线条 + 泛音"),
            ("主题", 8, "主题完整陈述，民乐群奏", "中", "旋律 + 支声复调"),
            ("发展", 8, "主题拆解、模进、转调准备", "中密", "加入低音与打击"),
            ("变奏", 8, "换配器/换节奏变奏", "中", "换主奏乐器"),
            ("高潮", 8, "全编制，主题以卡农叠奏", "密", "全编制 + 弦乐"),
            ("收束", 4, "主题碎片回响，渐弱收尾", "稀疏", "单线条渐弱"),
        ],
        "layers": [
            ("主奏", "dizi_low", ["引子", "主题", "变奏"], "主题陈述（曲笛温润）", "中偏左",
             "变奏段换二胡或琵琶主奏，形成音色对比"),
            ("副奏", "erhu", ["主题", "发展", "高潮"], "对句、支声复调", "中偏右", "与主奏错开 1–2 拍"),
            ("点描", "pipa", ["发展", "变奏", "高潮"], "颗粒推进、轮指", "中偏右", "发展段用轮指做密度"),
            ("色彩", "guzheng", ["主题", "变奏", "高潮"], "刮奏转场、琶音铺底", "宽（左右）", "刮奏用在段落交界"),
            ("和声", "strings", ["发展", "高潮", "收束"], "弦乐托底与卡农叠奏", "宽（左右）", "高潮做卡农"),
            ("打击", "daigu", ["发展", "高潮"], "堂鼓推进、定音鼓式重音", "中", "高潮加镲"),
        ],
        "chords": [
            ("1-4-5-1 主题",
             ["1add9", "4add9", "5sus4", "1add9"], "主题", "宫调式正格，大气、稳定"),
            ("6m-4-1-5 发展",
             ["6m7", "4add9", "1add9", "5sus4"], "发展", "羽起宫落，推动叙事"),
            ("4-5-3m-6m 变奏",
             ["4add9", "5sus4", "3m7", "6m7"], "变奏 / 高潮", "下行带来“辽阔转苍凉”的画面感"),
        ],
        "mix": [
            "曲笛：留出 2–6kHz 空间，混响 2.2s 做厅堂感",
            "二胡与曲笛对句时，二胡做 1.5dB 衰减让位",
            "弦乐组：低音区（150–400Hz）不要堆，避免与阮打架",
            "打击：堂鼓做 room 混响，镲片高频 8kHz 略降",
            "整体：动态范围留大（不要过度压缩），高潮与引子差 6dB 以上",
        ],
        "pitfalls": [
            "配乐写成歌曲结构 → 用“引子-主题-发展-变奏-高潮-收束”的叙事结构",
            "群奏没有主次 → 每个段落只有一个主奏，其他做支声",
            "全程一个力度 → 引子极弱、高潮极强，才有画面",
        ],
    },
}


# ---------------------------------------------------------------- 基础工具


def _setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _warn(msg: str) -> None:
    print(f"⚠️  {msg}", file=sys.stderr)


def parse_key(text: str) -> tuple[int, str]:
    s = (text or "D").strip().replace("♯", "#").replace("♭", "b")
    if not s:
        s = "D"
    acc, letter = 0, ""
    if len(s) >= 2 and s[0] in "#b" and s[1].upper() in "ABCDEFG":
        acc = 1 if s[0] == "#" else -1
        letter = s[1].upper()
    elif len(s) >= 2 and s[1] in "#b" and s[0].upper() in "ABCDEFG":
        acc = 1 if s[1] == "#" else -1
        letter = s[0].upper()
    elif s.upper() in ("A", "B", "C", "D", "E", "F", "G"):
        letter = s.upper()
    if not letter:
        return 2, "D"
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter]
    pc = (base + acc) % 12
    names = NOTE_NAMES_FLAT if acc < 0 else NOTE_NAMES_SHARP
    return pc, names[pc]


def note_name(midi: int, flat: bool = False) -> str:
    names = NOTE_NAMES_FLAT if flat else NOTE_NAMES_SHARP
    return f"{names[midi % 12]}{midi // 12 - 1}"


def degree_pc(tonic_pc: int, degree: int, acc: int = 0) -> int:
    return (tonic_pc + DEGREE_SEMITONES[degree] + acc) % 12


def parse_chord_token(token: str) -> tuple[int, int, str] | None:
    """'4add9' / '#4dim' / '6m' → (级数, 临时记号半音, 后缀)；失败返回 None。"""
    t = (token or "").strip()
    m = CHORD_RE.match(t)
    if not m:
        return None
    acc = 1 if m.group(1) == "#" else (-1 if m.group(1) == "b" else 0)
    degree = int(m.group(2))
    raw_suffix = m.group(3) or ""
    suffix = raw_suffix
    if suffix not in CHORD_SUFFIX_DISPLAY:
        low = raw_suffix.lower()
        if low in CHORD_SUFFIX_DISPLAY:
            suffix = low
        else:
            return None
    return degree, acc, suffix


def chord_absolute(token: str, tonic_pc: int, flat: bool) -> str:
    parsed = parse_chord_token(token)
    if parsed is None:
        return token
    degree, acc, suffix = parsed
    pc = degree_pc(tonic_pc, degree, acc)
    names = NOTE_NAMES_FLAT if flat else NOTE_NAMES_SHARP
    return f"{names[pc]}{CHORD_SUFFIX_DISPLAY[suffix]}"


def range_text(inst_id: str, tonic_pc: int, flat: bool) -> str:
    inst = INSTRUMENTS.get(inst_id)
    r = inst.get("range") if inst else None
    if not r:
        return "—"
    lo = 60 + tonic_pc + r[0]
    hi = 60 + tonic_pc + r[1]
    return f"{note_name(lo, flat)}–{note_name(hi, flat)}（首调 {r[0]:+d}–{r[1]:+d} 半音）"


def plan_structure(sections: list[tuple], raw_bars: int) -> tuple[list[dict], int, list[str]]:
    """按「4 小节整句」规划结构时间轴，返回 (structure, 对齐后总小节, 调整说明)。

    sections: [(段落名, 权重, 段落任务, 密度, 织体), ...]（SPEC §6 配方模板）
    raw_bars: 按 时长 × BPM 推算出的小节数

    规则（Lead 2026-10-25 定）：
      1) 每段小节数一律取 4 的倍数，且每段至少 4 小节（中国风段落是 4/8 小节整句）；
      2) 总小节 = round(raw_bars / 4) × 4；
      3) 按配方权重分配后向下取整到 4 的倍数，差额优先补「最后一支副歌」与「尾」；
      4) 总小节不足「4 小节 × 段落数」时，先删「桥」「预副」，再合并相邻权重最小的两段，
         而不是把段落压到 4 小节以下。
    """
    notes: list[str] = []
    units = max(1, int(round(raw_bars / 4.0)))
    work = [{"name": name, "weight": w, "role": role, "density": density, "texture": texture}
            for (name, w, role, density, texture) in sections]

    dropped: list[str] = []
    for dropout in ("桥", "预副"):  # 段落太多时先精简可选段
        if len(work) > units:
            idx = next((i for i, s in enumerate(work) if s["name"] == dropout), None)
            if idx is not None:
                dropped.append(work[idx]["name"])
                del work[idx]
    while len(work) > units and len(work) > 1:  # 还不够就合并权重最小的相邻两段
        best = min(range(len(work) - 1),
                   key=lambda i: (work[i]["weight"] + work[i + 1]["weight"], i))
        a, b = work[best], work[best + 1]
        a["role"] = f"{a['role']} → {b['role']}"
        a["weight"] += b["weight"]
        a["density"] = b["density"]
        a["texture"] = b["texture"]
        dropped.append(f"{a['name']}+{b['name']}")
        del work[best + 1]

    total_units = max(units, len(work))
    total_bars = total_units * 4
    if dropped:
        notes.append(f"总小节按 4 小节整句对齐后为 {total_bars} 小节，不足 {len(sections)} 段 × 4 小节，"
                     f"已精简/合并段落：{'、'.join(dropped)}")

    n = len(work)
    wsum = float(sum(s["weight"] for s in work)) or 1.0
    exact = [s["weight"] / wsum * total_units for s in work]
    alloc = [max(1, int(x)) for x in exact]  # 向下取整到 4 小节单位，每段至少 1 个单位
    guard = 0
    while sum(alloc) > total_units and guard < 10000:
        guard += 1
        cand = [i for i in range(n) if alloc[i] > 1]
        if not cand:
            break
        i = max(cand, key=lambda k: (alloc[k] - exact[k], alloc[k]))
        alloc[i] -= 1

    chorus_idx = [i for i, s in enumerate(work) if "副歌" in s["name"]]
    priority: list[int] = []
    # 差额补到「最后一支副歌」与「尾」：先补尾（4→8 小节收尾最自然），再补末段副歌，
    # 这样 3 分钟左右的歌各段能落在 4 或 8 小节的整句上。
    priority += [i for i, s in enumerate(work) if s["name"] == "尾"]
    if chorus_idx:
        priority.append(chorus_idx[-1])
    priority += [i for i in range(n) if i not in priority]
    k = 0
    guard = 0
    while sum(alloc) < total_units and guard < 100000:
        guard += 1
        alloc[priority[k % len(priority)]] += 1
        k += 1

    structure = []
    start = 1
    for sec, u in zip(work, alloc):
        structure.append({
            "name": sec["name"], "start_bar": start, "bars": u * 4,
            "seconds": 0, "role": sec["role"], "density": sec["density"],
            "texture": sec["texture"],
        })
        start += u * 4
    return structure, total_bars, notes


def _bool_of(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "是", "含", "要")
    if isinstance(value, (int, float)):
        return bool(value)
    return False


def _int_of(value, default: int) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- 需求解析


def build_blueprint(raw: dict) -> tuple[dict, dict]:
    """raw 需求 dict → (蓝图 JSON dict, 解析过程记录 dict)。"""
    notes: list[str] = []
    known = {"theme", "style", "mood", "duration_sec", "bpm", "key", "instrument", "vocal", "with_xiqu"}
    for k in raw:
        if k not in known:
            notes.append(f"忽略未知字段「{k}」（可用字段：{', '.join(sorted(known))}）")

    style_id = str(raw.get("style") or "shuqing").strip().lower()
    if style_id not in STYLE_RECIPES:
        notes.append(f"style「{style_id}」不在 5 套配方内，已回退 shuqing；可选：{', '.join(STYLE_RECIPES)}")
        style_id = "shuqing"
    recipe = STYLE_RECIPES[style_id]

    theme = str(raw.get("theme") or "").strip()
    mood = str(raw.get("mood") or "").strip() or recipe["mood"]

    duration = _int_of(raw.get("duration_sec", 180), 180)
    if not (30 <= duration <= 600):
        notes.append(f"duration_sec={raw.get('duration_sec')} 超出 30–600 秒，已取默认 180 秒；"
                     f"要别的长度请给 30–600 的整数")
        duration = 180

    bpm_in = raw.get("bpm")
    bpm = _int_of(bpm_in, recipe["bpm"]) if bpm_in is not None else recipe["bpm"]
    if not (40 <= bpm <= 200):
        notes.append(f"bpm={bpm_in} 超出 40–200，已取配方默认 {recipe['bpm']} BPM")
        bpm = recipe["bpm"]

    key_in = str(raw.get("key") or "D").strip()
    tonic_pc, key_name = parse_key(key_in)

    inst_in = str(raw.get("instrument") or "").strip().lower()
    if inst_in and inst_in not in INSTRUMENTS:
        notes.append(f"instrument「{inst_in}」不在 SPEC §4 乐器表内，已用配方主奏 "
                     f"{INSTRUMENTS[recipe['main_instrument']]['name']}；"
                     f"可选：{', '.join(INSTRUMENTS)}")
        inst_in = ""
    instrument = inst_in or recipe["main_instrument"]
    if inst_in and inst_in not in (recipe["main_instrument"],) + tuple(recipe["sub_instruments"]):
        notes.append(f"instrument「{INSTRUMENTS[inst_in]['name']}」不是本配方的主/副奏，"
                     f"仍按你指定执行（配方推荐 {INSTRUMENTS[recipe['main_instrument']]['name']}）")

    vocal = _bool_of(raw.get("vocal", False))
    with_xiqu = _bool_of(raw.get("with_xiqu", False))

    mode_id = recipe["modes"][0]
    scale_id = recipe["scale"]
    meter = recipe["meter"]
    bar_beats = 4.0
    raw_bars = int(round(duration * bpm / 60.0 / bar_beats))
    structure, bars, struct_notes = plan_structure(recipe["structure"], raw_bars)
    notes.extend(struct_notes)
    for sec in structure:
        sec["seconds"] = int(round(sec["bars"] * bar_beats * 60.0 / bpm))
    notes.append(f"时长 {duration} 秒 ÷ {bpm} BPM → 约 {raw_bars} 小节 → "
                 f"按 4 小节整句对齐取 {bars} 小节（≈{round(bars * bar_beats * 60.0 / bpm)} 秒）")

    # 结构时间轴（同名段落自动编号：副歌 → 副歌1/副歌2/副歌3，避免 @marks 重名）
    base_names = [s["name"] for s in structure]
    base_counts: dict[str, int] = {}
    for b in base_names:
        base_counts[b] = base_counts.get(b, 0) + 1
    seen: dict[str, int] = {}
    for s in structure:
        base = s["name"]
        if base_counts[base] > 1:
            seen[base] = seen.get(base, 0) + 1
            s["name"] = f"{base}{seen[base]}"
    display_names = [s["name"] for s in structure]
    alias: dict[str, list[str]] = {}
    for base, disp in zip(base_names, display_names):
        alias.setdefault(base, []).append(disp)
    section_names: list[str] = list(dict.fromkeys(display_names))

    # 音阶（音名与偏音分开算，避免在报告里错位）
    scale_meta = SCALES.get(scale_id, SCALES["qingyue"])
    degrees = list(PENTA_DEGREES)
    bianyin = list(scale_meta["bianyin"])
    flat_key = len(key_name) > 1 and key_name[1] == "b"
    name_of_pc = (lambda pc: NOTE_NAMES_FLAT[pc % 12]) if flat_key else (lambda pc: NOTE_NAMES_SHARP[pc % 12])
    absolute = [name_of_pc(tonic_pc + DEGREE_SEMITONES[int(d)]) for d in degrees]
    scale_rows: list[tuple[str, str, bool, str]] = [
        (d, name_of_pc(tonic_pc + DEGREE_SEMITONES[int(d)]), False, "骨架音，可作落音")
        for d in degrees
    ]
    bian_parts = []
    for b in bianyin:
        acc = 1 if b.startswith("#") else (-1 if b.startswith("b") else 0)
        d = int(b[-1])
        nm = name_of_pc(tonic_pc + DEGREE_SEMITONES[d] + acc)
        bian_parts.append(f"{b}={nm}")
        scale_rows.append((b, nm, True, "只做经过/辅助音，不做落音、不做长音"))
    tuning_note = (f"以 {key_name} 为宫（1={key_name}）；{MODES[mode_id]['name']}调式落音为 "
                   f"{MODES[mode_id]['tonic_degree']}；"
                   + (f"偏音 {'、'.join(bian_parts)} 只做经过/辅助音，不可做落音或长音。" if bian_parts
                      else "五声无偏音，旋律更“纯”。"))
    if with_xiqu:
        tuning_note += " 戏腔段落音可临时借 b7（燕乐色彩）做哭腔，但落音要回正音。"

    # 配器
    lead_inst = instrument
    arrangement = []
    layer_defs = list(recipe["layers"])
    replaced = False
    for layer, inst_id, secs, role, pan, note in layer_defs:
        use_inst = inst_id
        if layer == "主奏" and not replaced:
            use_inst = lead_inst
            replaced = True
        inst_meta = INSTRUMENTS[use_inst]
        sec_list = [d for base in secs for d in alias.get(base, [])]
        sec_list = [d for d in sec_list if d in section_names] or section_names[:2]
        row = {
            "layer": layer,
            "instrument": inst_meta["name"],
            "range": range_text(use_inst, tonic_pc, flat_key),
            "sections": sec_list,
            "role": role,
            "pan": pan,
            "note": note,
        }
        if layer == "主奏" and use_inst != inst_id:
            row["note"] = (row["note"] + f"（你指定主奏为{inst_meta['name']}，"
                           f"配方原推荐{INSTRUMENTS[inst_id]['name']}）").strip()
        arrangement.append(row)

    if vocal:
        vocal_sections = [disp for base, disp in zip(base_names, display_names)
                          if base in ("主歌", "副歌", "预副", "桥", "尾", "戏腔段")]
        arrangement.insert(0, {
            "layer": "人声",
            "instrument": "戏腔人声" if with_xiqu else "人声（男/女声）",
            "range": "—（按歌手音域定，建议副歌最高音 ≤ A4）",
            "sections": vocal_sections or section_names[:3],
            "role": "戏腔拖腔与甩腔" if with_xiqu else "主叙事、副歌情感",
            "pan": "中",
            "note": "人声是主角，其他声部让出 1–3kHz",
        })
    if with_xiqu and "戏腔段" not in base_names:
        notes.append("with_xiqu=true 但本配方结构里没有「戏腔段」：建议在副歌后插入 4 小节戏腔段，"
                     "或改用 gudian 配方。")

    # 和弦候选
    chord_plans = []
    for name, degrees_, fit, why in recipe["chords"]:
        c_abs = [chord_absolute(d, tonic_pc, flat_key) for d in degrees_]
        chord_plans.append({
            "name": name, "degrees": degrees_, "c_absolute": c_abs, "fit": fit, "why": why,
        })

    # 节奏
    rhythm_notes = [
        "句尾留白 1 拍，别把每一拍填满",
        "副歌前一小节滚镲/堂鼓渐快（密度递进）",
        f"打击预设「{recipe['perc_preset']}」：散板/前奏段落可关掉鼓",
    ]
    if with_xiqu:
        rhythm_notes.append("戏腔段可散起（rubato），拖腔处不落鼓")
    if style_id == "guochao":
        rhythm_notes.append("drop 前一拍抽掉鼓，落点更炸")

    # 避坑
    pitfalls = list(recipe["pitfalls"])
    pitfalls.append("九大误区逐条过门禁：跑 `python scripts/lint_guofeng.py --input 你的谱.jp`")
    pitfalls.append("偏音 4/7 不做落音、不做长音（lint M1/M2 会卡）")

    # 下一步
    safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "", theme) or style_id
    next_actions = [
        f"python scripts/jianpu2midi.py --input {safe}.jp --out {safe}.mid",
        f"python scripts/lint_guofeng.py --input {safe}.jp --report {safe}-校验.md",
    ]

    blueprint = {
        "meta": {"skill": SKILL_ID, "version": VERSION,
                 "generated": _dt.date.today().isoformat()},
        "brief": {
            "theme": theme,
            "style": style_id,
            "style_name": recipe["name"],
            "mood": mood,
            "key": key_name,
            "mode": mode_id,
            "scale": scale_id,
            "bpm": bpm,
            "duration_sec": duration,
            "meter": meter,
            "instrument": instrument,
            "instrument_name": INSTRUMENTS[instrument]["name"],
            "vocal": vocal,
        },
        "scale_notes": {
            "degrees": degrees,
            "bianyin": bianyin,
            "absolute": " ".join(absolute),
            "tuning_note": tuning_note,
        },
        "structure": structure,
        "arrangement": arrangement,
        "chord_plans": chord_plans,
        "rhythm": {
            "feel": recipe["feel"],
            "perc_preset": recipe["perc_preset"],
            "notes": rhythm_notes,
        },
        "mix": list(recipe["mix"]),
        "pitfalls": pitfalls,
        "next_actions": next_actions,
        "selftest": {"passed": False, "checks": []},
    }

    # selftest：真跑字段/数值自检
    checks = []
    req_top = ["meta", "brief", "scale_notes", "structure", "arrangement", "chord_plans",
               "rhythm", "mix", "pitfalls", "next_actions", "selftest"]
    checks.append(("JSON 顶层字段齐全（SPEC §2）", all(k in blueprint for k in req_top)))
    brief_req = ["theme", "style", "style_name", "mood", "key", "mode", "scale", "bpm",
                 "duration_sec", "meter", "instrument", "instrument_name", "vocal"]
    checks.append(("brief 字段齐全", all(k in blueprint["brief"] for k in brief_req)))
    checks.append(("小节数合计 = 对齐后总小节", sum(s["bars"] for s in structure) == bars))
    checks.append(("每段小节数均为 4 的倍数且 ≥4",
                   all(s["bars"] % 4 == 0 and s["bars"] >= 4 for s in structure)))
    total_sec = sum(s["seconds"] for s in structure)
    checks.append((f"结构时长合计 {total_sec}s 与目标 {duration}s 误差 ≤ 20%",
                   abs(total_sec - duration) <= max(20, duration * 0.2)))
    checks.append(("和弦候选 ≥3 套且级数与绝对音名等长",
                   len(chord_plans) >= 3 and all(len(p["degrees"]) == len(p["c_absolute"]) for p in chord_plans)))
    checks.append(("五声音级 = 1 2 3 5 6", degrees == ["1", "2", "3", "5", "6"]))
    checks.append(("BPM 在 40–200", 40 <= bpm <= 200))
    checks.append(("时长在 30–600 秒", 30 <= duration <= 600))
    checks.append(("next_actions 含 MIDI 与 lint 两条命令",
                   len(next_actions) == 2 and "jianpu2midi" in next_actions[0]
                   and "lint_guofeng" in next_actions[1]))
    checks.append(("配器表含主奏且音域可读", any(a["layer"] == "主奏" for a in arrangement)
                   and all(a["range"] for a in arrangement)))
    checks.append(("打击预设名在 SPEC §5 名单内", recipe["perc_preset"] in PERC_PRESETS))
    blueprint["selftest"] = {
        "passed": all(ok for _, ok in checks),
        "checks": [f"{'✅' if ok else '❌'} {name}" for name, ok in checks],
    }
    return blueprint, {"notes": notes, "style_id": style_id, "recipe": recipe,
                       "bar_beats": bar_beats, "bars": bars,
                       "section_names": section_names, "scale_rows": scale_rows,
                       "base_names": base_names}


# ---------------------------------------------------------------- Markdown 报告


def _dsl_skeleton(bp: dict, ctx: dict) -> str:
    brief = bp["brief"]
    plan = bp["chord_plans"][0]["degrees"]
    key = brief["key"]
    inst = brief["instrument"]
    perc = bp["rhythm"]["perc_preset"]
    mode = brief["mode"]
    scale = brief["scale"]
    return "\n".join([
        "@title " + (brief["theme"] or "我的中国风"),
        f"@key {key}",
        f"@mode {mode}",
        f"@scale {scale}",
        f"@meter {brief['meter']}",
        f"@tempo {brief['bpm']}",
        f"@instrument {inst}",
        f"@style {brief['style']}",
        f"@mood {brief['mood']}",
        "",
        "@marks",
        f"1={bp['structure'][0]['name']}",
        f"{bp['structure'][1]['start_bar']}={bp['structure'][1]['name']}",
        "",
        "@melody",
        "# 4/4：每小节 token 时值合计必须 = 4 拍；时值写 音级:拍数（也可用斜杠）",
        "6:2 1:1 2:1 | 3:2 5:1 6:1 | 1':2 6:1 5:1 | 6:4 |",
        "",
        "@chords",
        "# 级数 + 后缀；逗号可写两个和弦各占半小节；转位写 5/7",
        f"{plan[0]} | {plan[1]} | {plan[2]} | {plan[3]} |",
        "",
        "@perc",
        f"style={perc}",
        "",
        "# 骨架先用 4 小节跑通 lint + 导出 MIDI，再按第三节时间轴扩写",
        "# 校验：python scripts/lint_guofeng.py --input 我的谱.jp --report 我的谱-校验.md",
        "# 导出：python scripts/jianpu2midi.py --input 我的谱.jp --out 我的谱.mid",
    ])


def build_markdown(bp: dict, ctx: dict) -> str:
    brief = bp["brief"]
    style_id = ctx["style_id"]
    recipe = ctx["recipe"]
    mode = MODES[brief["mode"]]
    scale_meta = SCALES.get(brief["scale"], SCALES["qingyue"])
    L: list[str] = []
    L.append(f"# 中国风创作蓝图 · {brief['style_name']}"
             + (f"《{brief['theme']}》" if brief["theme"] else ""))
    L.append("")
    L.append(f"> 由 `guofeng_blueprint.py` v{bp['meta']['version']} 生成于 {bp['meta']['generated']}；"
             f"对应 SPEC §6 配方 `{style_id}`。照这份蓝图写谱，再用 lint 卡门禁。")
    L.append("")

    # 一、需求解读
    L.append("## 一、需求解读")
    L.append("")
    L.append("| 项目 | 取值 | 说明 |")
    L.append("|---|---|---|")
    L.append(f"| 题材 | {brief['theme'] or '（未填，按配方通用情绪写）'} | 决定意象与主奏乐器性格 |")
    L.append(f"| 风格配方 | {brief['style_name']}（`{style_id}`） | SPEC §6 五套配方之一 |")
    L.append(f"| 情绪 | {brief['mood']} | 影响调式、速度、留白密度 |")
    L.append(f"| 调 / 调式 | {brief['key']} / {mode['name']}调式 | 落音 {mode['tonic_degree']}；"
             f"{MODE_COLOR[brief['mode']]} |")
    L.append(f"| 音阶 | {scale_meta['name']}（`{brief['scale']}`） | 偏音："
             f"{'、'.join(bp['scale_notes']['bianyin']) or '无'} |")
    L.append(f"| 速度 / 拍号 | {brief['bpm']} BPM / {brief['meter']} | 配方区间 {recipe['bpm_range'][0]}–{recipe['bpm_range'][1]} |")
    L.append(f"| 时长 | {brief['duration_sec']} 秒 ≈ {ctx['bars']} 小节 | 4/4 每小节 {ctx['bar_beats']:g} 拍 |")
    L.append(f"| 主奏 | {brief['instrument_name']}（`{brief['instrument']}`） | "
             f"{INSTRUMENTS[brief['instrument']]['persona']} |")
    L.append(f"| 人声 | {'含' if brief['vocal'] else '纯器乐'} | 影响声部安排与混音让位 |")
    L.append("")
    if ctx["notes"]:
        L.append("输入解析提示：")
        L.append("")
        for n in ctx["notes"]:
            L.append(f"- {n}")
        L.append("")
    L.append("**一句话开工指令**：" +
             (f"写一首 {brief['duration_sec']} 秒左右的{brief['style_name']}，{brief['key']}调{mode['name']}调式，"
              f"{brief['bpm']} BPM，{brief['instrument_name']}主奏"
              + (f"，题材「{brief['theme']}」" if brief["theme"] else "")
              + ("，含人声" if brief["vocal"] else "，纯器乐")
              + "。"))
    L.append("")

    # 二、调式音阶
    L.append("## 二、调式音阶")
    L.append("")
    L.append(f"调式色彩：{MODE_COLOR[brief['mode']]}")
    L.append("")
    L.append("| 级数 | 音名 | 五声正音？ | 用法 |")
    L.append("|---|---|---|---|")
    for deg_label, nm, is_bian, usage in ctx.get("scale_rows", []):
        flag = "⚠️ 偏音" if is_bian else "✅ 正音"
        L.append(f"| {deg_label} | {nm} | {flag} | {usage} |")
    L.append("")
    if ctx.get("scale_rows"):
        L.append("注：级数 1/2/3/5/6 是五声骨架；偏音（4/7 等）按调式音阶列在末尾，只做经过/辅助音。")
        L.append("")
    L.append(f"定调说明：{bp['scale_notes']['tuning_note']}")
    L.append("")

    # 三、结构时间轴
    L.append("## 三、结构时间轴")
    L.append("")
    L.append("| # | 段落 | 起始小节 | 小节数 | 约秒数 | 段落任务 | 密度 | 织体 |")
    L.append("|---|---|---|---|---|---|---|---|")
    for i, s in enumerate(bp["structure"], 1):
        L.append(f"| {i} | {s['name']} | {s['start_bar']} | {s['bars']} | {s['seconds']} | "
                 f"{s['role']} | {s['density']} | {s['texture']} |")
    L.append("")
    total_bars = sum(s["bars"] for s in bp["structure"])
    total_sec = sum(s["seconds"] for s in bp["structure"])
    L.append(f"合计：{total_bars} 小节 / 约 {total_sec} 秒（目标 {brief['duration_sec']} 秒）。")
    L.append("")
    L.append("> 段落按 4 小节整句对齐（每段都是 4 的倍数）；若你要 8 小节大乐句，"
             "直接把主歌/副歌各写两遍（或把该段小节数 ×2）。")
    base_names = ctx.get("base_names") or []
    if len(set(base_names)) < len(base_names):
        L.append("")
        L.append("注：同名段落已自动编号（副歌1/副歌2/副歌3…），直接抄 `@marks` 不会重名；"
                 "不想要编号可自己改成「副歌（再现）」等写法。")
    L.append("")
    L.append("段落标记直接抄进 `.jp` 的 `@marks`：")
    L.append("")
    L.append("```")
    L.append("@marks")
    for s in bp["structure"]:
        L.append(f"{s['start_bar']}={s['name']}")
    L.append("```")
    L.append("")

    # 四、配器表
    L.append("## 四、配器表")
    L.append("")
    L.append("| 层 | 乐器 | 建议音域 | 出现的段落 | 角色 | 声像 | 备注 |")
    L.append("|---|---|---|---|---|---|---|")
    for a in bp["arrangement"]:
        L.append(f"| {a['layer']} | {a['instrument']} | {a['range']} | "
                 f"{'、'.join(a['sections'])} | {a['role']} | {a['pan']} | {a['note']} |")
    L.append("")
    L.append("配器原则：每个段落只有一个主奏；主歌减声部，副歌才全编制；民乐留在 1–4kHz 的“身份频段”。")
    L.append("")

    # 五、和弦候选
    L.append("## 五、和弦候选（3 套，`c_absolute` 已按当前调算好）")
    L.append("")
    for i, p in enumerate(bp["chord_plans"], 1):
        L.append(f"### {i}. {p['name']}（用于：{p['fit']}）")
        L.append("")
        L.append("| 级数 | " + " | ".join(p["degrees"]) + " |")
        L.append("|---|" + "|".join(["---"] * len(p["degrees"])) + "|")
        L.append("| 实际和弦 | " + " | ".join(p["c_absolute"]) + " |")
        L.append("")
        L.append(f"为什么：{p['why']}")
        L.append("")
    L.append("五声化改造速查：优先 `add9 / sus2 / sus4 / add2 / omit3`；七和弦（m7/maj7/7）只在"
             "高潮或转位处偶尔用；避免在偏音上叠三和弦。")
    L.append("")

    # 六、节奏与打击
    L.append("## 六、节奏与打击")
    L.append("")
    L.append(f"- 律动感觉：{bp['rhythm']['feel']}")
    L.append(f"- 打击预设：`{bp['rhythm']['perc_preset']}`（SPEC §5 名单，可直接写进 `@perc`）")
    L.append("")
    L.append("节奏要点：")
    L.append("")
    for n in bp["rhythm"]["notes"]:
        L.append(f"- {n}")
    L.append("")

    # 七、混音
    L.append("## 七、混音")
    L.append("")
    for m in bp["mix"]:
        L.append(f"- {m}")
    L.append("")

    # 八、避坑
    L.append("## 八、避坑（写之前先看）")
    L.append("")
    for p in bp["pitfalls"]:
        L.append(f"- {p}")
    L.append("")

    # 九、下一步
    L.append("## 九、下一步")
    L.append("")
    L.append("按顺序执行：")
    L.append("")
    for i, cmd in enumerate(bp["next_actions"], 1):
        L.append(f"{i}. `{cmd}`")
    L.append("3. 看校验报告里的「门禁清单」，把 error 归零、warn 尽量清；")
    L.append("4. 把 `.mid` 拖进 DAW 换真实音源，按第七节混音。")
    L.append("")
    L.append("### 可直接复制的 DSL 骨架（先跑通 4 小节再扩写）")
    L.append("")
    L.append("```")
    L.append(_dsl_skeleton(bp, ctx))
    L.append("```")
    L.append("")
    L.append("写满整首时：`@melody` 每小节一行，token 时值合计必须等于 "
             f"{ctx['bar_beats']:g} 拍（4/4）；段落起点写进 `@marks`。")
    L.append("")
    L.append("### 自检（脚本生成时实际跑过）")
    L.append("")
    for c in bp["selftest"]["checks"]:
        L.append(f"- {c}")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------- CLI


def _demo_out_dir() -> Path:
    """demo 产物写到系统临时目录，避免污染上架包（scripts/ 会被打包扫描）。"""
    d = Path(tempfile.gettempdir()) / "guofeng-music-out"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = SCRIPT_DIR  # 临时目录不可写时退回脚本目录
    return d


def _default_paths(input_path: Path | None) -> tuple[Path, Path]:
    if input_path is not None:
        base = input_path.with_name(input_path.stem + "-蓝图")
        return base.with_suffix(".json"), base.with_suffix(".md")
    d = _demo_out_dir()
    return d / "guofeng-blueprint.json", d / "guofeng-blueprint.md"


DEMO_INPUT = {
    "theme": "江南雨·旧巷思念",
    "style": "shuqing",
    "mood": "雨夜、旧巷、思念（哀而不伤）",
    "duration_sec": 180,
    "key": "D",
    "instrument": "xiao",
    "vocal": True,
}


def read_input_json(path: Path) -> dict:
    data = path.read_bytes()
    text = None
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise ValueError(f"文件编码无法识别（既不是 UTF-8 也不是 GBK）：{path}")
    if not text.strip():
        return {}
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 格式错误：第 {exc.lineno} 行第 {exc.colno} 列附近 —— {exc.msg}")
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError("JSON 顶层必须是对象（{...}），不能是数组或字符串")
    return obj


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="guofeng_blueprint.py",
        description="中国风创作蓝图生成：需求 JSON（全部可选，最小必填为空对象）→ 蓝图 JSON + Markdown 报告。纯标准库。",
        epilog=("示例：\n"
                "  python guofeng_blueprint.py                  # demo → <临时目录>/guofeng-blueprint.{json,md}\n"
                "  python guofeng_blueprint.py --demo\n"
                "  python guofeng_blueprint.py --input 需求.json --out-json 蓝图.json --out-md 蓝图.md\n"
                "默认输出名：demo/无参数 → <临时目录>/guofeng-blueprint.json/.md；\n"
                "            --input 无 --out-* → 同目录/<输入名>-蓝图.json 与 -蓝图.md"),
    )
    parser.add_argument("--input", help="输入需求 JSON（所有字段可选，空对象也合法）")
    parser.add_argument("--out-json", help="输出蓝图 JSON 路径（默认见上）")
    parser.add_argument("--out-md", help="输出 Markdown 报告路径（默认见上）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 需求生成蓝图")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    default_json, default_md = _default_paths(input_path)
    out_json = Path(args.out_json).expanduser() if args.out_json else default_json
    out_md = Path(args.out_md).expanduser() if args.out_md else default_md

    try:
        if input_path is not None:
            if not input_path.exists():
                print(f"❌ 找不到输入文件：{input_path}", file=sys.stderr)
                print("下一步：确认路径；或直接跑 `python guofeng_blueprint.py --demo` 看输出样式。",
                      file=sys.stderr)
                return 2
            raw = read_input_json(input_path)
            source = str(input_path)
        else:
            raw = dict(DEMO_INPUT)
            source = "内置 demo 需求"

        blueprint, ctx = build_blueprint(raw)
        for note in ctx.get("notes", []):
            mark = "⚠️ " if any(k in note for k in ("回退", "超出", "不在", "忽略", "非法", "不一致")) else "ℹ️ "
            print(f"{mark} {note}", file=sys.stderr)
        md = build_markdown(blueprint, ctx)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(blueprint, ensure_ascii=False, indent=2), encoding="utf-8")
        out_md.write_text(md, encoding="utf-8")

        brief = blueprint["brief"]
        print("")
        print("=" * 62)
        print(f"✅ 蓝图已生成：{brief['style_name']}"
              + (f"《{brief['theme']}》" if brief["theme"] else ""))
        print(f"   {brief['key']} · {MODES[brief['mode']]['name']}调式 · {brief['scale']} · "
              f"{brief['bpm']} BPM · {brief['meter']} · {brief['duration_sec']} 秒 ≈ {ctx['bars']} 小节")
        print(f"   主奏：{brief['instrument_name']}（{INSTRUMENTS[brief['instrument']]['persona']}）"
              f" · 打击：{blueprint['rhythm']['perc_preset']} · 人声：{'含' if brief['vocal'] else '无'}")
        print(f"   结构：{' → '.join(s['name'] for s in blueprint['structure'])}")
        print(f"   和弦候选：{len(blueprint['chord_plans'])} 套；配器层：{len(blueprint['arrangement'])}")
        print(f"   JSON：{out_json}")
        print(f"   Markdown：{out_md}")
        print(f"   自检：{'全部通过' if blueprint['selftest']['passed'] else '有未通过项，见报告末尾'}")
        print("=" * 62)
        print("下一步：复制 Markdown 第九节的 DSL 骨架写成 .jp → 跑 lint 清 error → 用 jianpu2midi 导出 MIDI。")
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"❌ 生成蓝图失败：{exc}", file=sys.stderr)
        print("下一步：① 先用 --demo 确认脚本正常；② 检查输入 JSON 是否是合法对象（{}）；"
              "③ 不确定字段就全删掉，最小输入可用空对象 {}。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
