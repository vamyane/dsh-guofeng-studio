#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jianpu2midi.py —— 简谱 DSL（.jp）→ 多轨 MIDI（format 1 / PPQ 480）

纯标准库实现（不用 mido / numpy / PIL）。四轨固定顺序：
  0 指挥轨（tempo、time signature、key signature、段落 marker）
  1 旋律（program 按 SPEC §4 乐器表）
  2 和声（89 pad 或 1 piano）
  3 低音（33 finger bass；未写 @bass 时按和弦根音/转位自动生成）
  4 打击（GM channel 10）

用法：
  python jianpu2midi.py
        无参数 = 内置 demo，输出到系统临时目录 guofeng-music-out/guofeng-demo.mid
        （demo 产物放临时目录，避免污染上架包；真实路径见脚本输出）
  python jianpu2midi.py --demo
        同上（显式 demo）
  python jianpu2midi.py --input 我的谱.jp
        输出 我的谱.mid（与输入同目录）
  python jianpu2midi.py --input 我的谱.jp --out 输出.mid
  python jianpu2midi.py --help

时值写法：`音级:时值` 或 `音级/时值` 都合法（如 `1:2`、`4:0.5`、`6,/2`），单位「拍」。
默认输出文件名：demo/无参数 → <临时目录>/guofeng-demo.mid；
不给 --out 且给了 --input 时：输出与输入同目录、同名的 .mid。
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- 常量（SPEC §4/§5）

SCRIPT_DIR = Path(__file__).resolve().parent  # 脚本自身目录：不依赖 cwd（SPEC §7）

PPQ = 480  # 每四分音符 tick 数（SPEC §7：固定 480）

# SPEC §4 乐器表：program 直接取表内数字（0 基 GM 编号），range 为首调音域（相对主音的半音数）
INSTRUMENTS = {
    "di":       {"name": "笛",      "program": 73,  "range": (0, 21),   "gm": "Flute"},
    "xiao":     {"name": "箫",      "program": 75,  "range": (0, 21),   "gm": "Pan Flute"},
    # 笙：GM 无笙，按 SPEC §4 注释统一用 71 Bassoon 近似，演播时按 DAW 音源替换
    "sheng":    {"name": "笙",      "program": 71,  "range": (0, 19),   "gm": "Bassoon（GM 无笙，近似）"},
    "suona":    {"name": "唢呐",    "program": 111, "range": (0, 24),   "gm": "Shanai"},
    "guan":     {"name": "管子",    "program": 68,  "range": (2, 21),   "gm": "Oboe"},
    "xun":      {"name": "埙",      "program": 79,  "range": (0, 16),   "gm": "Ocarina"},
    "dizi_low": {"name": "曲笛",    "program": 73,  "range": (4, 19),   "gm": "Flute"},
    "guzheng":  {"name": "古筝",    "program": 107, "range": (0, 28),   "gm": "Koto"},
    "guqin":    {"name": "古琴",    "program": 107, "range": (0, 12),   "gm": "Koto"},
    "pipa":     {"name": "琵琶",    "program": 105, "range": (0, 26),   "gm": "Banjo"},
    "erhu":     {"name": "二胡",    "program": 110, "range": (-5, 24),  "gm": "Fiddle"},
    "zhonghu":  {"name": "中胡",    "program": 110, "range": (0, 19),   "gm": "Fiddle"},
    "yangqin":  {"name": "扬琴",    "program": 15,  "range": (0, 26),   "gm": "Dulcimer"},
    "ruan":     {"name": "阮",      "program": 105, "range": (0, 14),   "gm": "Banjo"},
    "daigu":    {"name": "大鼓",    "program": None, "range": None,     "gm": "ch10"},
    "luogu":    {"name": "锣鼓组",  "program": None, "range": None,     "gm": "ch10"},
    "strings":  {"name": "弦乐组",  "program": 48,  "range": None,     "gm": "String Ensemble"},
    "pad":      {"name": "合成 pad", "program": 89,  "range": None,     "gm": "Pad 2 (warm)"},
    "piano":    {"name": "钢琴",    "program": 1,   "range": None,     "gm": "Acoustic Grand（表内记 1）"},
}

# SPEC §5 打击乐预设名（必须完全一致）
PERC_PRESETS = ["锣鼓-中板", "锣鼓-快板", "散板散点", "堂鼓-推进", "军鼓-4/4", "电子-国潮", "无"]

# SPEC §5 GM 打击乐映射
DRUM = {
    "BD": 36, "SD": 38, "HH": 42, "OHH": 46, "CRASH": 49,
    "大锣": 52, "小锣": 53, "堂鼓": 45, "木鱼": 76, "碰铃": 37,
}

DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

# 小节块名（其余 @xxx 都当头部指令）
BLOCK_NAMES = {"marks", "melody", "chords", "bass", "perc"}

NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# 音级[:时值] 或 音级/时值 都合法（SPEC §1 写冒号，样板谱与 references 也用冒号；斜杠为兼容写法）
TOKEN_RE = re.compile(r"^([#b]?)([0-7])([',]*)(?:[:/](\d+(?:\.\d+)?))?$")
CHORD_RE = re.compile(r"^([#b]?)([1-7])([A-Za-z0-9]*)(?:/([#b]?[1-7]))?$")

CHORD_INTERVALS = {
    "":      [0, 4, 7],
    "m":     [0, 3, 7],
    "dim":   [0, 3, 6],
    "sus2":  [0, 2, 7],
    "sus4":  [0, 5, 7],
    "7":     [0, 4, 7, 10],
    "m7":    [0, 3, 7, 10],
    "maj7":  [0, 4, 7, 11],
    "6":     [0, 4, 7, 9],
    "m6":    [0, 3, 7, 9],
    "add9":  [0, 4, 7, 14],
    "add2":  [0, 2, 4, 7],
    "9":     [0, 4, 7, 10, 14],
    "omit3": [0, 7],
}

DEFAULT_DEMO_JP = """# jianpu2midi.py 内置 demo（8 小节，D 羽调式，抒情国风）
# 想改成自己的曲子：复制本段到 xxx.jp，改 @key/@tempo/@melody 即可
@title 月下独酌
@key D
@mode yu
@scale qingyue
@meter 4/4
@tempo 72
@instrument di
@style shuqing
@mood 清冷孤寂

@marks
1=前奏
3=主歌A
7=副歌

@melody
6:2 1 2 | 3 5 3 6 | 3 2 1/2 | 2 3 5 3 | 5 6 5 3 | 2/2 3 6 | 6 1'/2 6 | 5/2 3 6 |

@chords
6m7 | 1add9 | 6m7 | 5sus4 | 1add9 | 2m7 | 5sus4 | 6m |

@perc
style=锣鼓-中板
"""


# ---------------------------------------------------------------- 基础工具


def _setup_stdout() -> None:
    """Windows 控制台默认 cp936，统一转 UTF-8，避免中文/符号乱码或报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _warn(msg: str) -> None:
    print(f"⚠️  {msg}", file=sys.stderr)


def _info(msg: str) -> None:
    print(msg)


def read_text_file(path: Path) -> str:
    """读 UTF-8 文本；失败退回 GBK；再失败给中文提示。"""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"文件编码无法识别（既不是 UTF-8 也不是 GBK）：{path}")


def strip_inline_comment(line: str) -> str:
    """去掉行内注释。防误伤升号：#4 的 # 后面紧跟数字，不算注释。"""
    for i, ch in enumerate(line):
        if ch != "#" or i == 0:
            continue
        if not line[i - 1].isspace():
            continue
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if nxt.isdigit() or nxt in "b#":
            continue  # 是 #4 / b7 这类临时记号
        return line[:i]
    return line


def parse_key(text: str) -> tuple[int, str]:
    """'D' / '#F' / 'F#' / 'bB' / 'Bb' / '降B' → (音高类 0-11, 规范名)。"""
    s = (text or "D").strip().replace("♯", "#").replace("♭", "b")
    if not s:
        s = "D"
    acc = 0
    letter = ""
    # 形式一：#F / bB（记号在前）
    if len(s) >= 2 and s[0] in "#b" and s[1].upper() in "ABCDEFG":
        acc = 1 if s[0] == "#" else -1
        letter = s[1].upper()
    # 形式二：F# / Bb（记号在后）
    elif len(s) >= 2 and s[1] in "#b" and s[0].upper() in "ABCDEFG":
        acc = 1 if s[1] == "#" else -1
        letter = s[0].upper()
    # 形式三：单个音名（b 单独出现时按音名 B 处理）
    elif s.upper() in ("A", "B", "C", "D", "E", "F", "G"):
        letter = s.upper()
    else:
        for i, ch in enumerate(s):
            if ch.upper() in "ABCDEFG":
                letter = ch.upper()
                acc = s[:i].count("#") - s[:i].count("b")
                acc += s[i + 1:].count("#") - s[i + 1:].count("b")
                break
    if not letter:
        return 2, "D"
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[letter]
    pc = (base + acc) % 12
    names = NOTE_NAMES_FLAT if acc < 0 else NOTE_NAMES_SHARP
    return pc, names[pc]


def note_name(midi: int, flat: bool = False) -> str:
    names = NOTE_NAMES_FLAT if flat else NOTE_NAMES_SHARP
    return f"{names[midi % 12]}{midi // 12 - 1}"


def parse_meter(text: str) -> tuple[int, int, float]:
    """'4/4' → (分子, 分母, 每小节拍数(以四分音符计))。"""
    s = (text or "4/4").strip().replace(" ", "")
    m = re.match(r"^(\d+)/(\d+)$", s)
    if not m:
        return 4, 4, 4.0
    num, den = int(m.group(1)), int(m.group(2))
    if num <= 0 or den <= 0:
        return 4, 4, 4.0
    return num, den, num * 4.0 / den


def parse_int(text: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(float(str(text).strip()))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


# ---------------------------------------------------------------- DSL 解析


def split_sections(text: str) -> tuple[dict, dict]:
    """把 .jp 拆成 (头部指令 dict, 块 dict{name: [行]})。"""
    headers: dict[str, str] = {}
    blocks: dict[str, list[str]] = {}
    cur = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = strip_inline_comment(line).strip()
        if not line:
            continue
        if line.startswith("@"):
            body = line[1:].strip()
            parts = body.split(None, 1)
            name = parts[0].strip().lower() if parts else ""
            rest = parts[1].strip() if len(parts) > 1 else ""
            if name in BLOCK_NAMES:
                cur = name
                blocks.setdefault(name, [])
                if rest:
                    blocks[name].append(rest)
            else:
                cur = None
                headers[name] = rest
        elif cur:
            blocks[cur].append(line)
    return headers, blocks


def parse_note_token(tok: str) -> dict | None:
    """解析 音级[:时值] → dict；失败返回 None。"""
    t = tok.strip()
    if not t:
        return None
    m = TOKEN_RE.match(t)
    if not m:
        return None
    acc, deg_s, oct_s, dur_s = m.group(1), m.group(2), m.group(3), m.group(4)
    try:
        dur = float(dur_s) if dur_s is not None else 1.0
    except ValueError:
        return None
    if dur <= 0:
        return None
    deg = int(deg_s)
    acc_v = 1 if acc == "#" else (-1 if acc == "b" else 0)
    oct_shift = oct_s.count("'") - oct_s.count(",")
    return {
        "raw": t,
        "degree": deg,
        "acc": acc_v,
        "oct": oct_shift,
        "dur": dur,
        "rest": deg == 0,
        # 相对主音的半音偏移（1 级 = 0）
        "offset": DEGREE_SEMITONES.get(deg, 0) + acc_v + 12 * oct_shift if deg else 0,
    }


def parse_note_bars(lines: list[str], bad_tokens: list[str] | None = None) -> list[list[dict]]:
    """把旋律/低音块拆成「小节 → token 列表」。小节时值不做校正，按实际记录。"""
    bars: list[list[dict]] = []
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]
        else:
            parts = [line.strip()]
        for part in parts:
            toks = []
            for word in part.split():
                tk = parse_note_token(word)
                if tk is None:
                    if bad_tokens is not None:
                        bad_tokens.append(word)
                    continue
                toks.append(tk)
            bars.append(toks)
    return bars


def parse_chord_token(tok: str) -> dict:
    """解析和弦级数写法。无效时 valid=False（lint 报 M15）。"""
    t = (tok or "").strip()
    base = {"raw": t, "valid": False, "degree": 0, "acc": 0, "suffix": "",
            "intervals": [], "inv": None, "root_offset": 0, "name": t}
    m = CHORD_RE.match(t)
    if not m:
        return base
    acc, deg_s, suf_raw, inv_s = m.group(1), m.group(2), m.group(3), m.group(4)
    suffix = suf_raw or ""
    if suffix not in CHORD_INTERVALS:
        low = suffix.lower()
        if low in CHORD_INTERVALS:
            suffix = low
        elif low.startswith("maj") and low[3:] in ("", "7", "9"):
            suffix = "maj7" if low == "maj7" else ""
        else:
            return base
    acc_v = 1 if acc == "#" else (-1 if acc == "b" else 0)
    deg = int(deg_s)
    inv = None
    if inv_s:
        inv = {"acc": 1 if inv_s[0] == "#" else (-1 if inv_s[0] == "b" else 0),
               "degree": int(inv_s[-1])}
    root_offset = DEGREE_SEMITONES[deg] + acc_v
    return {
        "raw": t,
        "valid": True,
        "degree": deg,
        "acc": acc_v,
        "suffix": suffix,
        "intervals": CHORD_INTERVALS[suffix],
        "inv": inv,
        "root_offset": root_offset,
        "name": t,
    }


def parse_chord_bars(lines: list[str]) -> list[list[dict]]:
    """和弦块 → 每小节一个 list（逗号分隔两个和弦时长度为 2）。"""
    bars: list[list[dict]] = []
    for line in lines:
        if "|" in line:
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]
        else:
            parts = [line.strip()]
        for part in parts:
            cells = [c.strip() for c in part.split(",") if c.strip()]
            bars.append([parse_chord_token(c) for c in cells])
    return bars


def parse_marks(lines: list[str]) -> list[tuple[int, str]]:
    """@marks：'1=前奏' → [(1, '前奏')]，按小节号排序。"""
    out = []
    for line in lines:
        m = re.match(r"^(\d+)\s*=\s*(.+)$", line.strip())
        if not m:
            continue
        bar = int(m.group(1))
        name = m.group(2).strip()
        if bar >= 1 and name:
            out.append((bar, name))
    out.sort(key=lambda x: x[0])
    return out


def parse_perc(lines: list[str]) -> dict:
    """@perc 块：style=预设名，或 pattern=note:beats@beat,...（缺 @ 时顺序累加）。"""
    style = ""
    pattern = ""
    for line in lines:
        s = line.strip()
        if s.lower().startswith("style="):
            style = s.split("=", 1)[1].strip()
        elif s.lower().startswith("pattern="):
            pattern = s.split("=", 1)[1].strip()
    return {"style": style, "pattern": pattern}


# ---------------------------------------------------------------- 节奏/音高模型


def tokens_to_notes(bars: list[list[dict]], base_midi: int, bar_beats: float) -> list[dict]:
    """token 小节 → 绝对音符事件（小节网格对齐；同音级相邻 token 合并为连音）。"""
    notes: list[dict] = []
    for bi, bar in enumerate(bars):
        pos = 0.0
        last_pitched = None
        for tk in bar:
            if tk["rest"]:
                pos += tk["dur"]
                last_pitched = None
                continue
            midi = base_midi + tk["offset"]
            midi = max(0, min(127, midi))
            if last_pitched is not None and last_pitched["midi"] == midi:
                last_pitched["dur"] += tk["dur"]  # 同音级连音合并
            else:
                note = {
                    "midi": midi,
                    "dur": tk["dur"],
                    "start": bi * bar_beats + pos,
                    "bar": bi + 1,
                    "beat": pos + 1,
                    "degree": tk["degree"],
                    "offset": tk["offset"],
                }
                notes.append(note)
                last_pitched = note
            pos += tk["dur"]
    return notes


def chord_notes(ch: dict, base_midi: int) -> list[int]:
    """和弦 → 闭合排列的 MIDI 音高列表（支持斜杠转位）。"""
    if not ch.get("valid"):
        return []
    intervals = list(ch["intervals"])
    inv = ch.get("inv")
    if inv:
        inv_pc = (DEGREE_SEMITONES[inv["degree"]] + inv["acc"]) % 12
        pcs = [(ch["root_offset"] + iv) % 12 for iv in intervals]
        idx = None
        for i, pc in enumerate(pcs):
            if pc == inv_pc:
                idx = i
                break
        if idx is not None and idx != 0:
            intervals = intervals[idx:] + [iv + 12 for iv in intervals[:idx]]
    root = base_midi + ch["root_offset"]
    out = []
    for iv in intervals:
        n = root + iv
        out.append(max(0, min(127, n)))
    return out


def bass_pitch_for(ch: dict, base_midi: int) -> int | None:
    """低音声部：默认和弦根音；有斜杠转位则用转位音。"""
    if not ch.get("valid"):
        return None
    if ch.get("inv"):
        inv = ch["inv"]
        off = DEGREE_SEMITONES[inv["degree"]] + inv["acc"]
    else:
        off = ch["root_offset"]
    return max(0, min(127, base_midi + off))


def perc_events(style: str, pattern: str, bars: int, bar_beats: float) -> tuple[list[dict], str]:
    """打击乐：预设名或显式 pattern → (事件列表, 实际生效的预设名)。"""
    if style and style not in PERC_PRESETS:
        _warn(f"打击乐预设「{style}」不在 SPEC §5 名单内（{', '.join(PERC_PRESETS)}），"
              f"本次按「无」处理；建议改成名单内的名字。")
        style = "无"
    if not style:
        style = "无"
    if pattern:
        return _pattern_events(pattern, bars, bar_beats), style
    return _preset_events(style, bars, bar_beats), style


def _ev(note_key: str, beat: float, dur: float, vel: int, bi: int, bar_beats: float) -> dict | None:
    if beat >= bar_beats - 1e-9:
        return None
    return {"midi": DRUM[note_key], "start": bi * bar_beats + beat, "dur": dur, "vel": vel}


def _preset_events(style: str, bars: int, bar_beats: float) -> list[dict]:
    out: list[dict] = []
    if style == "无" or bars <= 0:
        return out
    for bi in range(bars):
        rows: list[tuple[str, float, float, int]] = []
        if style == "锣鼓-中板":
            rows = [("大锣", 0.0, 1.0, 100), ("堂鼓", 1.0, 0.5, 78), ("小锣", 2.0, 1.0, 92),
                    ("堂鼓", 3.0, 0.5, 78), ("木鱼", 3.5, 0.25, 60)]
        elif style == "锣鼓-快板":
            rows = [("大锣", 0.0, 0.5, 106), ("小锣", 2.0, 0.5, 94),
                    ("堂鼓", 1.0, 0.25, 86), ("堂鼓", 3.0, 0.25, 86),
                    ("HH", 0.5, 0.25, 60), ("HH", 1.5, 0.25, 60),
                    ("HH", 2.5, 0.25, 60), ("HH", 3.5, 0.25, 60),
                    ("木鱼", 0.25, 0.25, 55), ("木鱼", 1.25, 0.25, 55),
                    ("木鱼", 2.25, 0.25, 55), ("木鱼", 3.25, 0.25, 55)]
        elif style == "散板散点":
            rows = [("大锣", 0.0, 2.0, 90)]
            if bi % 2 == 1:
                rows += [("木鱼", 2.5, 0.5, 62), ("小锣", 3.5, 0.5, 72)]
            else:
                rows += [("碰铃", 1.5, 0.5, 58), ("堂鼓", 3.0, 1.0, 70)]
        elif style == "堂鼓-推进":
            rows = [("堂鼓", float(b), 1.0, 112 - 6 * b) for b in range(4)]
            rows += [("HH", 0.5 + 0.5 * k, 0.25, 48 + 2 * k) for k in range(7)]
            if bi % 4 == 3:  # 每 4 小节推一次
                rows += [("SD", 3.5, 0.25, 88), ("SD", 3.75, 0.25, 96), ("CRASH", 0.0, 1.0, 92)]
        elif style == "军鼓-4/4":
            rows = [("BD", 0.0, 0.5, 104), ("BD", 2.0, 0.5, 104),
                    ("SD", 1.0, 0.5, 96), ("SD", 3.0, 0.5, 96)]
            rows += [("HH", 0.5 + 0.5 * k, 0.25, 52) for k in range(7)]
            if bi == 0:
                rows.append(("CRASH", 0.0, 1.0, 100))
        elif style == "电子-国潮":
            rows = [("BD", 0.0, 0.5, 110), ("BD", 1.5, 0.5, 100),
                    ("BD", 2.0, 0.5, 108), ("BD", 3.5, 0.5, 100),
                    ("SD", 1.0, 0.5, 100), ("SD", 3.0, 0.5, 100),
                    ("木鱼", 3.75, 0.25, 66)]
            rows += [("OHH" if k % 2 else "HH", 0.5 * k, 0.25, 48) for k in range(8)]
            if bi % 4 == 0:
                rows.append(("大锣", 0.0, 1.0, 108))
        for key, beat, dur, vel in rows:
            ev = _ev(key, beat, dur, vel, bi, bar_beats)
            if ev:
                out.append(ev)
    return out


def _pattern_events(pattern: str, bars: int, bar_beats: float) -> list[dict]:
    """显式 pattern='36:1@0, 38:0.5@1'（note:beats@beat；省略 @ 则顺序累加）。"""
    out: list[dict] = []
    cells = [c.strip() for c in pattern.split(",") if c.strip()]

    def note_of(s: str) -> int | None:
        s = s.strip()
        if s in DRUM:
            return DRUM[s]
        try:
            return int(float(s))
        except ValueError:
            return None

    pos = 0.0
    for cell in cells:
        at = None
        body = cell
        if "@" in cell:
            body, at_s = cell.split("@", 1)
            try:
                at = float(at_s)
            except ValueError:
                at = None
        body = body.strip()
        if ":" in body:
            n_s, d_s = body.split(":", 1)
        else:
            n_s, d_s = body, "1"
        note = note_of(n_s)
        try:
            dur = float(d_s)
        except ValueError:
            dur = 1.0
        if note is None or dur <= 0:
            continue
        start_beat = (pos if at is None else at) % bar_beats if bar_beats else 0.0
        for bi in range(bars):
            out.append({"midi": note, "start": bi * bar_beats + start_beat,
                        "dur": dur, "vel": 90})
        pos = (pos if at is None else at) + dur
    return out


# ---------------------------------------------------------------- MIDI 写入（纯 struct）


def _vlq(value: int) -> bytes:
    if value < 0:
        value = 0
    buf = bytearray([value & 0x7F])
    value >>= 7
    while value:
        buf.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(buf))


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">I", len(payload)) + payload


def _meta(etype: int, data: bytes) -> bytes:
    return bytes([0xFF, etype]) + _vlq(len(data)) + data


def _track_chunk(events: list[tuple[int, int, bytes]], end_tick: int) -> bytes:
    """events: (绝对 tick, 排序序, 事件字节)；同 tick 时序小的先写。"""
    events = sorted(events, key=lambda e: (e[0], e[1]))
    body = bytearray()
    last = 0
    for tick, _order, payload in events:
        body += _vlq(max(0, tick - last)) + payload
        last = tick
    body += _vlq(max(0, end_tick - last)) + _meta(0x2F, b"")
    return _chunk(b"MTrk", bytes(body))


def _note_events(note_list: list[dict], channel: int, order_base: int = 2) -> list[tuple[int, int, bytes]]:
    ev = []
    for n in note_list:
        on = int(round(n["start"] * PPQ))
        off = int(round((n["start"] + n["dur"]) * PPQ))
        if off <= on:
            off = on + max(1, PPQ // 8)
        vel = n.get("vel", 96)
        ev.append((on, order_base + 1, bytes([0x90 | channel, n["midi"] & 0x7F, vel & 0x7F])))
        ev.append((off, order_base, bytes([0x80 | channel, n["midi"] & 0x7F, 0x40])))
    return ev


KEY_SIG_SHARP = {0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6}
KEY_SIG_FLAT = {0: 0, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5, 6: -6}


def _key_signature(tonic_pc: int, flat: bool) -> tuple[int, int]:
    if flat:
        sf = KEY_SIG_FLAT.get(tonic_pc, 0)
    else:
        sf = KEY_SIG_SHARP.get(tonic_pc, 0)
    return sf, 0  # mi=0：调号按大调记法，具体色彩由调式/旋律体现


def build_midi(model: dict) -> bytes:
    bars = model["bars"]
    bar_beats = model["bar_beats"]
    total_ticks = int(round(bars * bar_beats * PPQ))
    num, den = model["meter_num"], model["meter_den"]
    dd = 0
    while (1 << dd) < den:
        dd += 1

    # ---- Track 0：指挥轨
    conductor: list[tuple[int, int, bytes]] = []
    conductor.append((0, 0, _meta(0x03, "指挥轨 conductor".encode("utf-8"))))
    usec = int(round(60_000_000 / max(1, model["bpm"])))
    conductor.append((0, 0, _meta(0x51, usec.to_bytes(3, "big"))))
    conductor.append((0, 0, _meta(0x58, bytes([num & 0xFF, dd, 24, 8]))))
    sf, mi = _key_signature(model["tonic_pc"], model["flat_key"])
    conductor.append((0, 0, _meta(0x59, struct.pack(">bB", sf, mi))))
    for bar, name in model["marks"]:
        tick = int(round((bar - 1) * bar_beats * PPQ))
        if tick < 0:
            tick = 0
        conductor.append((tick, 0, _meta(0x06, name.encode("utf-8"))))
    tracks = [_track_chunk(conductor, total_ticks)]

    # ---- Track 1：旋律
    melody_track: list[tuple[int, int, bytes]] = []
    mel_inst = INSTRUMENTS.get(model["instrument"], {})
    melody_track.append((0, 0, _meta(0x03, f"旋律-{mel_inst.get('name', model['instrument'])}".encode("utf-8"))))
    mel_program = mel_inst.get("program")
    if mel_program is not None and mel_inst.get("program") != 0:
        melody_track.append((0, 0, bytes([0xC0 | model["ch_melody"], mel_program & 0x7F])))
    melody_track += _note_events(model["melody_notes"], model["ch_melody"])
    tracks.append(_track_chunk(melody_track, total_ticks if not model["melody_notes"] else 0))

    # ---- Track 2：和声
    harm_track: list[tuple[int, int, bytes]] = []
    harm_program = 89 if model["harmony_pad"] else 1
    harm_track.append((0, 0, _meta(0x03, ("和声-Pad" if model["harmony_pad"] else "和声-钢琴").encode("utf-8"))))
    harm_track.append((0, 0, bytes([0xC0 | model["ch_harmony"], harm_program & 0x7F])))
    harm_track += _note_events(model["harmony_notes"], model["ch_harmony"], order_base=2)
    tracks.append(_track_chunk(harm_track, 0 if model["harmony_notes"] else total_ticks))

    # ---- Track 3：低音
    bass_track: list[tuple[int, int, bytes]] = []
    bass_track.append((0, 0, _meta(0x03, "低音-Finger Bass".encode("utf-8"))))
    bass_track.append((0, 0, bytes([0xC0 | model["ch_bass"], 33])))
    bass_track += _note_events(model["bass_notes"], model["ch_bass"], order_base=2)
    tracks.append(_track_chunk(bass_track, 0 if model["bass_notes"] else total_ticks))

    # ---- Track 4：打击（GM channel 10 = 0 基通道 9）
    perc_track: list[tuple[int, int, bytes]] = []
    perc_track.append((0, 0, _meta(0x03, f"打击-{model['perc_style']}".encode("utf-8"))))
    perc_track += _note_events(model["perc_notes"], model["ch_perc"], order_base=2)
    tracks.append(_track_chunk(perc_track, 0 if model["perc_notes"] else total_ticks))

    header = _chunk(b"MThd", struct.pack(">HHH", 1, len(tracks), PPQ))
    return header + b"".join(tracks)


# ---------------------------------------------------------------- 模型装配


def load_model(text: str, source: str) -> dict:
    headers, blocks = split_sections(text)
    bad_tokens: list[str] = []

    tonic_pc, key_name = parse_key(headers.get("key", "D"))
    num, den, bar_beats = parse_meter(headers.get("meter", "4/4"))
    bpm = parse_int(headers.get("tempo", "72"), 72, 20, 300)
    instrument = (headers.get("instrument", "di").strip().lower() or "di")
    if instrument not in INSTRUMENTS:
        _warn(f"@instrument「{instrument}」不在 SPEC §4 乐器表内，旋律轨按 GM 73 Flute 写入；"
              f"建议改成：{', '.join(list(INSTRUMENTS)[:8])} …")
    style = headers.get("style", "").strip().lower()
    mode = headers.get("mode", "yu").strip().lower()
    scale = headers.get("scale", "qingyue").strip().lower()
    title = headers.get("title", "未命名").strip() or "未命名"

    base_melody = 60 + tonic_pc
    base_chords = 60 + tonic_pc - 12
    base_bass = 60 + tonic_pc - 12

    melody_bars = parse_note_bars(blocks.get("melody", []), bad_tokens)
    for bad in bad_tokens:
        _warn(f"旋律 token「{bad}」无法解析，已跳过；请检查是否写成 音级[:时值]（如 5/0.5、1'、6,）")
    melody_notes = tokens_to_notes(melody_bars, base_melody, bar_beats)

    chord_bars = parse_chord_bars(blocks.get("chords", []))
    for bi, chords in enumerate(chord_bars):
        for ch in chords:
            if not ch["valid"]:
                _warn(f"第 {bi + 1} 小节和弦「{ch['raw']}」无法解析，已跳过；"
                      f"合法写法如 4add9、3m7、5sus4、1add9/5")

    all_bars = max(len(melody_bars), len(chord_bars))
    if all_bars <= 0:
        raise ValueError("没有解析到任何小节：请至少写一个 @melody 块（每小节一行，token 用空格分隔）")

    # 小节时值校验（不崩，按实际写入 + stderr 提示）
    for bi, bar in enumerate(melody_bars):
        actual = sum(t["dur"] for t in bar)
        if abs(actual - bar_beats) > 1e-6:
            _warn(f"第 {bi + 1} 小节时值 {actual:g} ≠ {bar_beats:g} 拍，已按实际写入；建议跑 lint 修正")

    if chord_bars and len(chord_bars) != len(melody_bars):
        _warn(f"@melody 有 {len(melody_bars)} 小节，@chords 有 {len(chord_bars)} 小节，"
              f"按较多的一方对齐（空缺处留白）；建议补齐")

    # 和声 / 低音 / 打击
    harmony_notes: list[dict] = []
    bass_notes: list[dict] = []
    for bi, chords in enumerate(chord_bars):
        if not chords:
            continue
        n = len(chords)
        span = bar_beats / n
        for ci, ch in enumerate(chords):
            start = bi * bar_beats + ci * span
            if not ch["valid"]:
                continue
            for midi in chord_notes(ch, base_chords):
                harmony_notes.append({"midi": midi, "start": start, "dur": span,
                                      "bar": bi + 1, "vel": 70})
    if not blocks.get("bass"):
        for bi, chords in enumerate(chord_bars):
            if not chords:
                continue
            n = len(chords)
            span = bar_beats / n
            for ci, ch in enumerate(chords):
                p = bass_pitch_for(ch, base_bass)
                if p is None:
                    continue
                bass_notes.append({"midi": p, "start": bi * bar_beats + ci * span,
                                   "dur": span, "bar": bi + 1, "vel": 82})
    else:
        bass_bars = parse_note_bars(blocks["bass"], [])
        bass_notes = tokens_to_notes(bass_bars, base_bass, bar_beats)
        for bi, bar in enumerate(bass_bars):
            actual = sum(t["dur"] for t in bar)
            if abs(actual - bar_beats) > 1e-6:
                _warn(f"@bass 第 {bi + 1} 小节时值 {actual:g} ≠ {bar_beats:g} 拍；建议跑 lint")

    perc = parse_perc(blocks.get("perc", []))
    perc_notes, perc_style = perc_events(perc["style"], perc["pattern"], all_bars, bar_beats)

    harmony_pad = style in ("guochao", "peiyue")
    model = {
        "title": title,
        "source": source,
        "key_name": key_name,
        "tonic_pc": tonic_pc,
        "flat_key": (len(key_name) > 1 and key_name[1] == "b"),
        "mode": mode,
        "scale": scale,
        "style": style,
        "bpm": bpm,
        "meter_num": num,
        "meter_den": den,
        "bar_beats": bar_beats,
        "bars": all_bars,
        "marks": parse_marks(blocks.get("marks", [])),
        "instrument": instrument,
        "melody_notes": melody_notes,
        "harmony_notes": harmony_notes,
        "bass_notes": bass_notes,
        "perc_notes": perc_notes,
        "perc_style": perc_style,
        "harmony_pad": harmony_pad,
        "ch_melody": 0,
        "ch_harmony": 1,
        "ch_bass": 2,
        "ch_perc": 9,
    }
    return model


# ---------------------------------------------------------------- CLI


def _demo_out_dir() -> Path:
    """demo 产物一律写到系统临时目录，避免污染上架包（scripts/ 会被打包扫描）。"""
    d = Path(tempfile.gettempdir()) / "guofeng-music-out"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = SCRIPT_DIR  # 临时目录不可写时退回脚本目录
    return d


def _default_out(input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path.with_suffix(".mid")
    return _demo_out_dir() / "guofeng-demo.mid"


def _summary(model: dict, out_path: Path, midi_bytes: bytes) -> None:
    total_beats = model["bars"] * model["bar_beats"]
    seconds = total_beats * 60.0 / max(1, model["bpm"])
    inst = INSTRUMENTS.get(model["instrument"], {})
    _info("")
    _info("=" * 62)
    _info(f"✅ 已生成 MIDI：{out_path}")
    _info(f"   曲名：{model['title']}")
    _info(f"   调与调式：{model['key_name']} {model['mode']} / 音阶 {model['scale']} / "
          f"{model['meter_num']}/{model['meter_den']} / {model['bpm']} BPM")
    _info(f"   主奏：{inst.get('name', model['instrument'])}（GM {inst.get('program')} "
          f"{inst.get('gm', '')}）")
    _info(f"   小节 {model['bars']} / 时长 {seconds:.1f} 秒 / PPQ {PPQ} / 轨道 5（指挥+旋律+和声+低音+打击）")
    _info(f"   音符数：旋律 {len(model['melody_notes'])}、和声 {len(model['harmony_notes'])}、"
          f"低音 {len(model['bass_notes'])}、打击 {len(model['perc_notes'])}")
    if model["marks"]:
        seg = "、".join(f"第{b}小节「{n}」" for b, n in model["marks"])
        _info(f"   段落 marker：{seg}")
    _info(f"   文件体积：{len(midi_bytes)} 字节")
    _info("=" * 62)
    _info("下一步：把 .mid 拖进 DAW 换真实音源试听；改谱后重跑本脚本即可覆盖。")


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="jianpu2midi.py",
        description="简谱 DSL（.jp）→ 多轨 MIDI（format 1 / PPQ 480 / 五轨）。纯标准库。",
        epilog=("示例：\n"
                "  python jianpu2midi.py                                  # demo → <临时目录>/guofeng-demo.mid\n"
                "  python jianpu2midi.py --input 我的谱.jp                # → 我的谱.mid（同目录）\n"
                "  python jianpu2midi.py --input 我的谱.jp --out 输出.mid\n"
                "时值写法：音级:时值 或 音级/时值（如 1:2、4:0.5），单位「拍」。\n"
                "默认输出名：demo/无参数 → <临时目录>/guofeng-demo.mid；--input 无 --out → 同目录同名 .mid"),
    )
    parser.add_argument("--input", help="输入简谱 DSL 文件（.jp）")
    parser.add_argument("--out", help="输出 MIDI 路径（默认见上）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 谱生成 MIDI")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    out_path = Path(args.out).expanduser() if args.out else _default_out(input_path)

    try:
        if input_path is not None:
            if not input_path.exists():
                print(f"❌ 找不到输入文件：{input_path}", file=sys.stderr)
                print("下一步：确认路径拼写；或用 --demo 先跑一遍内置示例看格式。", file=sys.stderr)
                return 2
            text = read_text_file(input_path)
            source = str(input_path)
        else:
            text = DEFAULT_DEMO_JP
            source = "内置 demo"
        model = load_model(text, source)
        midi_bytes = build_midi(model)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(midi_bytes)
        _summary(model, out_path, midi_bytes)
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # 兜底：绝不把 traceback 甩给用户
        print(f"❌ 生成 MIDI 失败：{exc}", file=sys.stderr)
        print("下一步：① 先用 --demo 确认脚本本身正常；② 检查 .jp 是否有 @melody 块、"
              "每小节 token 用空格分隔；③ 把报错原文发给开发者。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
