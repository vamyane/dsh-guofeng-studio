#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lint_guofeng.py —— 中国风简谱 DSL 三道关卡校验（SPEC §3 的 M1–M15）

纯标准库实现。输出 Markdown 报告（每条发现含 级别 / 位置 / 规则编号 / 说明 / 修法），
报告末尾给「门禁清单」：九大误区逐条 ✅/❌ + 总结行 `结论：可交付` / `结论：需修改 N 处`。

用法：
  python lint_guofeng.py
        无参数 = 内置 demo，报告写到系统临时目录 guofeng-music-out/guofeng-lint.md
        （demo 产物放临时目录，避免污染上架包；真实路径见脚本输出）
  python lint_guofeng.py --demo
        同上（显式 demo）
  python lint_guofeng.py --input 我的谱.jp
        报告写到 同目录/我的谱-校验.md
  python lint_guofeng.py --input 我的谱.jp --report 校验.md
  python lint_guofeng.py --help

退出码：0 = 无 error（可交付）；1 = 有 error（需修改）；2 = 参数/文件/解析层面无法继续。
"""

from __future__ import annotations

import argparse
import datetime as _dt
import re
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------- 常量（SPEC §4/§5）

SCRIPT_DIR = Path(__file__).resolve().parent  # 脚本自身目录：不依赖 cwd（SPEC §7）

INSTRUMENTS = {
    "di":       {"name": "笛",      "program": 73,  "range": (0, 21)},
    "xiao":     {"name": "箫",      "program": 75,  "range": (0, 21)},
    "sheng":    {"name": "笙",      "program": 71,  "range": (0, 19)},
    "suona":    {"name": "唢呐",    "program": 111, "range": (0, 24)},
    "guan":     {"name": "管子",    "program": 68,  "range": (2, 21)},
    "xun":      {"name": "埙",      "program": 79,  "range": (0, 16)},
    "dizi_low": {"name": "曲笛",    "program": 73,  "range": (4, 19)},
    "guzheng":  {"name": "古筝",    "program": 107, "range": (0, 28)},
    "guqin":    {"name": "古琴",    "program": 107, "range": (0, 12)},
    "pipa":     {"name": "琵琶",    "program": 105, "range": (0, 26)},
    "erhu":     {"name": "二胡",    "program": 110, "range": (-5, 24)},
    "zhonghu":  {"name": "中胡",    "program": 110, "range": (0, 19)},
    "yangqin":  {"name": "扬琴",    "program": 15,  "range": (0, 26)},
    "ruan":     {"name": "阮",      "program": 105, "range": (0, 14)},
    "daigu":    {"name": "大鼓",    "program": None, "range": None},
    "luogu":    {"name": "锣鼓组",  "program": None, "range": None},
    "strings":  {"name": "弦乐组",  "program": 48,  "range": None},
    "pad":      {"name": "合成 pad", "program": 89,  "range": None},
    "piano":    {"name": "钢琴",    "program": 1,   "range": None},
}

PERC_PRESETS = ["锣鼓-中板", "锣鼓-快板", "散板散点", "堂鼓-推进", "军鼓-4/4", "电子-国潮", "无"]

DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}
DEGREE_TEXT = {1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6", 7: "7"}
PENTA_PCS = {0, 2, 4, 7, 9}  # 五声正音（相对主音的半音集合：1 2 3 5 6）
MODES = {
    "gong": {"name": "宫", "tonic_degree": 1},
    "shang": {"name": "商", "tonic_degree": 2},
    "jue": {"name": "角", "tonic_degree": 3},
    "zhi": {"name": "徵", "tonic_degree": 5},
    "yu": {"name": "羽", "tonic_degree": 6},
}
MODE_ALIAS = {"宫": "gong", "商": "shang", "角": "jue", "徵": "zhi", "羽": "yu",
              "gong": "gong", "shang": "shang", "jue": "jue", "zhi": "zhi", "yu": "yu"}
SCALE_NAMES = {"wusheng": "五声（无偏音）", "qingyue": "清乐（加 4、7）",
               "yayue": "雅乐（加 #4、7）", "yanyue": "燕乐（加 4、b7）"}

BLOCK_NAMES = {"marks", "melody", "chords", "bass", "perc"}
NOTE_NAMES_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
NOTE_NAMES_FLAT = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# 音级[:时值] 或 音级/时值 都合法（SPEC §1 用冒号，样板谱与 references 也用冒号；斜杠为兼容写法）
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

# 与 jianpu2midi.py 内置 demo 保持一致（同一首 8 小节示例，lint 应 0 error）
DEFAULT_DEMO_JP = """# lint_guofeng.py 内置 demo（8 小节，D 羽调式，抒情国风）
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


def strip_inline_comment(line: str) -> str:
    for i, ch in enumerate(line):
        if ch != "#" or i == 0:
            continue
        if not line[i - 1].isspace():
            continue
        nxt = line[i + 1] if i + 1 < len(line) else ""
        if nxt.isdigit() or nxt in "b#":
            continue
        return line[:i]
    return line


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


def note_name(midi: int, tonic_flat: bool = False) -> str:
    names = NOTE_NAMES_FLAT if tonic_flat else NOTE_NAMES_SHARP
    return f"{names[midi % 12]}{midi // 12 - 1}"


def parse_meter(text: str) -> tuple[int, int, float]:
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


# ---------------------------------------------------------------- DSL 解析（与 jianpu2midi.py 同规则，独立实现）


def split_sections(text: str) -> tuple[dict, dict]:
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
        "raw": t, "degree": deg, "acc": acc_v, "oct": oct_shift, "dur": dur,
        "rest": deg == 0,
        "offset": (DEGREE_SEMITONES.get(deg, 0) + acc_v + 12 * oct_shift) if deg else 0,
        # 去掉时值后的音级写法（用于报告里显示，如 6, / 1' / #4）
        "note_text": _pitch_degree_name(deg, acc_v, oct_shift),
    }


def parse_note_bars(lines: list[str], bad_tokens: list[str] | None = None) -> list[list[dict]]:
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
    t = (tok or "").strip()
    base = {"raw": t, "valid": False, "degree": 0, "acc": 0, "suffix": "",
            "intervals": [], "inv": None, "root_offset": 0}
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
    inv = None
    if inv_s:
        inv = {"acc": 1 if inv_s[0] == "#" else (-1 if inv_s[0] == "b" else 0),
               "degree": int(inv_s[-1])}
    return {"raw": t, "valid": True, "degree": int(deg_s), "acc": acc_v,
            "suffix": suffix, "intervals": CHORD_INTERVALS[suffix],
            "inv": inv, "root_offset": DEGREE_SEMITONES[int(deg_s)] + acc_v}


def parse_chord_bars(lines: list[str]) -> list[list[dict]]:
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
    out = []
    for line in lines:
        m = re.match(r"^(\d+)\s*=\s*(.+)$", line.strip())
        if not m:
            continue
        bar, name = int(m.group(1)), m.group(2).strip()
        if bar >= 1 and name:
            out.append((bar, name))
    out.sort(key=lambda x: x[0])
    return out


def parse_perc(lines: list[str]) -> dict:
    style, pattern = "", ""
    for line in lines:
        s = line.strip()
        if s.lower().startswith("style="):
            style = s.split("=", 1)[1].strip()
        elif s.lower().startswith("pattern="):
            pattern = s.split("=", 1)[1].strip()
    return {"style": style, "pattern": pattern}


def tokens_to_notes(bars: list[list[dict]], base_midi: int, bar_beats: float) -> list[dict]:
    notes: list[dict] = []
    for bi, bar in enumerate(bars):
        pos = 0.0
        last = None
        for tk in bar:
            if tk["rest"]:
                pos += tk["dur"]
                last = None
                continue
            midi = max(0, min(127, base_midi + tk["offset"]))
            if last is not None and last["midi"] == midi:
                last["dur"] += tk["dur"]
            else:
                note = {"midi": midi, "dur": tk["dur"], "start": bi * bar_beats + pos,
                        "bar": bi + 1, "beat": pos + 1, "degree": tk["degree"],
                        "acc": tk["acc"], "oct": tk["oct"], "offset": tk["offset"],
                        "text": tk["note_text"], "pc": midi % 12}
                notes.append(note)
                last = note
            pos += tk["dur"]
    return notes


# ---------------------------------------------------------------- 报告数据结构


class Findings:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, level: str, bar, beat, rule: str, msg: str, fix: str) -> None:
        self.rows.append({"level": level, "bar": bar, "beat": beat,
                          "rule": rule, "msg": msg, "fix": fix})

    def by_level(self, level: str) -> list[dict]:
        return [r for r in self.rows if r["level"] == level]

    def count(self, level: str) -> int:
        return len(self.by_level(level))

    def for_rules(self, rules: list[str]) -> list[dict]:
        return [r for r in self.rows if r["rule"] in rules]

    def sorted_rows(self) -> list[dict]:
        order = {"error": 0, "warn": 1, "info": 2}
        return sorted(self.rows, key=lambda r: (order.get(r["level"], 3),
                                                r["bar"] if isinstance(r["bar"], int) else 10 ** 6,
                                                float(r["beat"]) if isinstance(r["beat"], (int, float)) else 0))


def pos_text(bar, beat=None) -> str:
    if bar is None:
        return "全曲"
    if isinstance(bar, str):
        return bar
    if beat is None:
        return f"第 {bar} 小节"
    return f"第 {bar} 小节 第 {beat:g} 拍"


def _pitch_degree_name(degree: int, acc: int, oct_shift: int) -> str:
    pre = "#" if acc > 0 else ("b" if acc < 0 else "")
    marks = ("'" * oct_shift) if oct_shift > 0 else ("," * (-oct_shift))
    return f"{pre}{degree}{marks}"


# ---------------------------------------------------------------- 校验模型与规则


def build_context(text: str) -> dict:
    headers, blocks = split_sections(text)
    bad_tokens: list[str] = []
    tonic_pc, key_name = parse_key(headers.get("key", "D"))
    num, den, bar_beats = parse_meter(headers.get("meter", "4/4"))
    bpm = parse_int(headers.get("tempo", "72"), 72, 20, 300)
    instrument = (headers.get("instrument", "di").strip().lower() or "di")
    mode_raw = (headers.get("mode", "yu").strip().lower() or "yu")
    mode_id = MODE_ALIAS.get(mode_raw, "yu")
    scale = (headers.get("scale", "qingyue").strip().lower() or "qingyue")
    style = (headers.get("style", "").strip().lower())

    melody_bars = parse_note_bars(blocks.get("melody", []), bad_tokens)
    chord_bars = parse_chord_bars(blocks.get("chords", []))
    marks = parse_marks(blocks.get("marks", []))
    perc = parse_perc(blocks.get("perc", []))

    base_melody = 60 + tonic_pc
    melody_notes = tokens_to_notes(melody_bars, base_melody, bar_beats)
    n_bars = max(len(melody_bars), len(chord_bars))
    total_beats = max(1, n_bars) * bar_beats

    mode = MODES[mode_id]
    mode_tonic_pc = (tonic_pc + DEGREE_SEMITONES[mode["tonic_degree"]]) % 12
    dominant_pc = (mode_tonic_pc + 7) % 12
    triad_pcs = {mode_tonic_pc, (mode_tonic_pc + 4) % 12, (mode_tonic_pc + 7) % 12}

    chord_instances: list[dict] = []
    for bi, chords in enumerate(chord_bars):
        n = len(chords) or 1
        span = bar_beats / n
        for ci, ch in enumerate(chords):
            if ch["valid"]:
                chord_instances.append({"bar": bi + 1, "start": bi * bar_beats + ci * span,
                                        "dur": span, "ch": ch})

    sections: list[tuple[int, int, str]] = []
    if marks:
        ms = list(marks)
        if ms[0][0] != 1:
            ms = [(1, "未标记段")] + ms
        for i, (bar, name) in enumerate(ms):
            end = ms[i + 1][0] - 1 if i + 1 < len(ms) else max(n_bars, bar)
            if end >= bar:
                sections.append((bar, end, name))
    if not sections:
        sections = [(1, max(1, n_bars), "全曲")]

    return {
        "headers": headers, "blocks": blocks,
        "key_name": key_name, "tonic_pc": tonic_pc,
        "tonic_flat": (len(key_name) > 1 and key_name[1] == "b"),
        "meter_num": num, "meter_den": den, "bar_beats": bar_beats, "bpm": bpm,
        "instrument": instrument, "mode_id": mode_id, "mode_name": mode["name"],
        "mode_tonic_degree": mode["tonic_degree"], "mode_tonic_pc": mode_tonic_pc,
        "dominant_pc": dominant_pc, "triad_pcs": triad_pcs,
        "scale": scale, "style": style,
        "melody_bars": melody_bars, "melody_notes": melody_notes,
        "chord_bars": chord_bars, "chord_instances": chord_instances,
        "marks": marks, "sections": sections, "perc": perc,
        "bad_tokens": bad_tokens, "n_bars": n_bars, "total_beats": total_beats,
        "title": headers.get("title", "未命名").strip() or "未命名",
        "mood": headers.get("mood", "").strip(),
    }


def is_bianyin(offset: int) -> bool:
    return (offset % 12) not in PENTA_PCS


def rule_checks(ctx: dict, f: Findings) -> None:
    notes: list[dict] = ctx["melody_notes"]
    bar_beats: float = ctx["bar_beats"]
    tonic_pc: int = ctx["tonic_pc"]
    mode_tonic_pc: int = ctx["mode_tonic_pc"]
    dominant_pc: int = ctx["dominant_pc"]
    triad_pcs: set[int] = ctx["triad_pcs"]

    # ---------- 空谱兜底（补充检查，与 M12 位置语义相关）
    if not ctx["melody_bars"]:
        f.add("error", None, None, "S2",
              "没有解析到 @melody 旋律块，无法做任何旋律校验。",
              "补一个 @melody 块：每小节一行，token 用空格分隔，如 `1 2 3 5 |`。")
        return
    for bad in ctx["bad_tokens"]:
        f.add("error", None, None, "S3",
              f"旋律 token「{bad}」无法解析。",
              "合法写法：`音级[:时值]`，音级 0–7 可带 #/b 前缀与 ' / , 八度记号，如 5/0.5、1'、6,。")

    # ---------- 段落 → 段末最后一个音
    section_last_idx: dict[int, int] = {}
    for start_bar, end_bar, name in ctx["sections"]:
        idxs = [i for i, n in enumerate(notes) if start_bar <= n["bar"] <= end_bar]
        if idxs:
            section_last_idx[idxs[-1]] = -1

    # ---------- M12 小节时值
    for bi, bar in enumerate(ctx["melody_bars"]):
        actual = sum(t["dur"] for t in bar)
        if abs(actual - bar_beats) > 1e-6:
            if actual < bar_beats:
                msg = f"第 {bi + 1} 小节时值只有 {actual:g} 拍，比 {ctx['meter_num']}/{ctx['meter_den']} 少了 {bar_beats - actual:g} 拍。"
                fix = "补足拍数（加正音或休止 0），例如 4/4 每小节 token 时值合计必须 = 4。"
            else:
                msg = f"第 {bi + 1} 小节时值 {actual:g} 拍，超出 {ctx['meter_num']}/{ctx['meter_den']} 的 {bar_beats:g} 拍 {actual - bar_beats:g} 拍。"
                fix = "删减 token 或缩短时值，让每小节合计正好 = 4 拍（4/4）。"
            f.add("error", bi + 1, 1, "M12", msg, fix)

    # ---------- 相邻音程（M3/M4）；中间有休止的不算「相邻进行」
    intervals: list[tuple[int, int]] = []  # (起点 note 下标, 半音差)
    for i in range(len(notes) - 1):
        n, nxt = notes[i], notes[i + 1]
        if nxt["start"] > n["start"] + n["dur"] + 1e-6:
            continue  # 中间隔了休止/空拍，不构成旋律相邻进行
        intervals.append((i, nxt["midi"] - n["midi"]))

    if intervals:
        semis = [(i, d) for i, d in intervals if abs(d) == 1]
        ratio = len(semis) / len(intervals)
        if ratio > 0.20:
            examples = "、".join(
                f"{pos_text(notes[i]['bar'], notes[i]['beat'])} {notes[i]['text']}→{notes[i + 1]['text']}"
                for i, _ in semis[:4])
            f.add("error", notes[semis[0][0]]["bar"], notes[semis[0][0]]["beat"], "M3",
                  f"小二度相邻进行占全部音程 {len(semis)}/{len(intervals)} = {ratio:.0%}，超过 20% 阈值（易出和风/日式感）：{examples}",
                  "把半音关系改成正音级进（3→5、7→6、4→5 换成 3→2→1 或 5→6→5 的走向），偏音只做经过音。")

    # M4：大跳判定用「两个音的实际 MIDI 音高差（含八度）」，整八度不算大跳
    for idx, (i, d) in enumerate(intervals):
        if abs(d) < 9:
            continue
        if abs(d) % 12 == 0:
            continue  # 整八度（±12/±24…）是常见写法，不要求反向级进
        if idx + 1 >= len(intervals):
            continue
        j, d2 = intervals[idx + 1]
        if j != i + 1:
            continue  # 大跳后中间隔了休止，不构成「跳进后未解决」
        ok = (d2 != 0 and (d2 > 0) != (d > 0) and abs(d2) <= 4)
        if not ok:
            a, b = notes[i], notes[i + 1]
            flat_k = ctx.get("tonic_flat", False)
            f.add("warn", b["bar"], b["beat"], "M4",
                  f"从 {a['text']}（{note_name(a['midi'], flat_k)}）到 {b['text']}"
                  f"（{note_name(b['midi'], flat_k)}）跳进 {d:+d} 半音（≥9 半音，约六度以上），"
                  f"后一音程 {d2:+d} 半音未反向级进（要求反向且 ≤4 半音）。",
                  f"在 {b['text']} 后补一个反向级进音（如 5→2 后接 1，或 1→6 后接 5），"
                  f"或把大跳改成级进；整八度跳进不受此限。")

    # ---------- M1 偏音落音 / M2 偏音长音
    for i, n in enumerate(notes):
        if not is_bianyin(n["offset"]):
            continue
        # 落音判定：后接休止、段末最后一个音、全曲终止
        phrase_end = False
        reason = ""
        if i == len(notes) - 1:
            phrase_end, reason = True, "全曲终止"
        elif notes[i + 1]["start"] > n["start"] + n["dur"] + 1e-6:
            phrase_end, reason = True, "后接休止"
        elif i in section_last_idx:
            phrase_end, reason = True, "段末"
        if phrase_end and n["dur"] >= 1 - 1e-9:
            f.add("error", n["bar"], n["beat"], "M1",
                  f"偏音「{n['text']}」作落音（{reason}，时值 {n['dur']:g} 拍）——这是九大误区里最伤中国风的一条。",
                  "把落音换成正音：羽调式落 6、宫调式落 1；句末偏音可改成下行级进到 6/5/3。")
        if n["dur"] > 1 + 1e-9:
            f.add("error", n["bar"], n["beat"], "M2",
                  f"偏音「{n['text']}」单音时值 {n['dur']:g} 拍 > 1 拍，长音停留会突出偏音、破坏五声色彩。",
                  "把长音拆成「偏音经过 + 正音长音」，如 4/2 改成 4/0.5 + 5/1.5（或直接换 5/2）。")

    # ---------- M5 五声正音占比
    if notes:
        bianyin = sum(1 for n in notes if is_bianyin(n["offset"]))
        zheng_ratio = 1 - bianyin / len(notes)
        if zheng_ratio < 0.70:
            f.add("error", None, None, "M5",
                  f"五声正音占比 {zheng_ratio:.0%}（正音 {len(notes) - bianyin}/{len(notes)}），低于 70%。",
                  "偏音只作经过/辅助音，且每个乐句不超过 1–2 个；主歌/副歌骨架全部用 1 2 3 5 6。")

    # ---------- M6 终止音
    if notes:
        last = notes[-1]
        if last["pc"] != mode_tonic_pc:
            f.add("error", last["bar"], last["beat"], "M6",
                  f"全曲终止音是「{last['text']}」（pc={note_name(last['midi'], ctx['tonic_flat'])}），"
                  f"不是 {ctx['mode_name']}调式主音（简谱 {ctx['mode_tonic_degree']}）。",
                  f"把最后一个音改成 {ctx['mode_tonic_degree']}，或把 @mode 改成与终止音相符的调式。")

    # ---------- M7 段末落音
    for idx in section_last_idx:
        n = notes[idx]
        if n["pc"] not in triad_pcs and n["pc"] not in (mode_tonic_pc, dominant_pc):
            sec = next((s[2] for s in ctx["sections"] if s[0] <= n["bar"] <= s[1]), "段")
            f.add("warn", n["bar"], n["beat"], "M7",
                  f"「{sec}」段末落音 {n['text']}（{note_name(n['midi'], ctx['tonic_flat'])}）不属于 "
                  f"{{主音、属音、主和弦音}}，段落收束不稳。",
                  f"段末改落 {ctx['mode_tonic_degree']}（主音）或 {ctx['dominant_pc']} 对应级数；"
                  f"副歌收尾优先主音。")

    # ---------- M8 音域
    if notes:
        offsets = [n["offset"] for n in notes]
        span = max(offsets) - min(offsets)
        hi = max(notes, key=lambda n: n["offset"])
        lo = min(notes, key=lambda n: n["offset"])
        if span > 30:
            f.add("error", None, None, "M8",
                  f"音域跨度 {span} 半音（{note_name(lo['midi'], ctx['tonic_flat'])}–"
                  f"{note_name(hi['midi'], ctx['tonic_flat'])}），超过 30 半音上限。",
                  "压缩到两个八度内：把最高音降八度写，或把最低音换成中音区同度。")
        elif span > 24:
            f.add("warn", None, None, "M8",
                  f"音域跨度 {span} 半音（{note_name(lo['midi'], ctx['tonic_flat'])}–"
                  f"{note_name(hi['midi'], ctx['tonic_flat'])}），超过两个八度，"
                  f"民乐单件乐器演奏会吃力。",
                  "把跨度收到 ≤24 半音；主奏乐器只负责一段音区，其余交给副奏/八度叠奏。")
        inst = INSTRUMENTS.get(ctx["instrument"])
        if inst and inst.get("range"):
            lo_r, hi_r = inst["range"]
            out_notes = [n for n in notes if n["offset"] < lo_r or n["offset"] > hi_r]
            if out_notes:
                ex = out_notes[0]
                f.add("info", ex["bar"], ex["beat"], "M8",
                      f"有 {len(out_notes)} 个音超出 {inst['name']} 建议音域（首调 {lo_r}–{hi_r} 半音，"
                      f"如 {ex['text']}），仅作提示：GM 音源能发声，但真实乐器会吃力或改音区。",
                      "按真实乐器换音区/换乐器；若为 GM 试听可忽略（本条不影响交付判定）。")

    # ---------- M9 高潮位置
    if notes:
        top = max(n["midi"] for n in notes)
        occ = [n for n in notes if n["midi"] == top]
        last_top = occ[-1]
        rel = last_top["start"] / ctx["total_beats"]
        if rel < 0.5:
            f.add("warn", last_top["bar"], last_top["beat"], "M9",
                  f"全曲最高音 {note_name(top, ctx['tonic_flat'])} 最后一次出现在 {rel:.0%} 位置（<50%），"
                  f"后半段缺少高点。",
                  "把最高音挪到副歌/末段（60%–85% 位置），前半段用中音区铺陈。")

    # ---------- M10 长音撞小二度
    for n in notes:
        if n["dur"] < 2 - 1e-9:
            continue
        note_end = n["start"] + n["dur"]
        for ci in ctx["chord_instances"]:
            if ci["bar"] != n["bar"]:
                continue
            if not (ci["start"] < note_end - 1e-9 and n["start"] < ci["start"] + ci["dur"] - 1e-9):
                continue
            ch = ci["ch"]
            if n["degree"] == 7 and ch["degree"] == 5:
                continue  # 旋律 7 + 属功能和弦（V）是正常导音解决关系，不报
            pcs = {(tonic_pc + ch["root_offset"] + iv) % 12 for iv in ch["intervals"]}
            clash = [pc for pc in pcs if min((pc - n["pc"]) % 12, (n["pc"] - pc) % 12) == 1]
            if clash:
                cname = ch["raw"]
                f.add("warn", n["bar"], n["beat"], "M10",
                      f"旋律长音 {n['text']}（{n['dur']:g} 拍）与同拍和弦 {cname} 的小二度音相撞"
                      f"（相差 1 半音），会发“糊”。",
                      f"把和弦换成五声化和弦（去掉撞音的那个音：{cname} → 试 sus2/sus4/omit3/add9 变体），"
                      f"或把旋律长音换成相邻正音。")

    # ---------- M11 五声外和弦占比
    if ctx["chord_instances"]:
        bad = []
        for ci in ctx["chord_instances"]:
            ch = ci["ch"]
            pcs = {(ch["root_offset"] + iv) % 12 for iv in ch["intervals"]}
            if any(pc not in PENTA_PCS for pc in pcs):
                bad.append(ci)
        ratio = len(bad) / len(ctx["chord_instances"])
        if ratio > 0.30:
            names = "、".join(f"第{ci['bar']}小节 {ci['ch']['raw']}" for ci in bad[:5])
            f.add("warn", None, None, "M11",
                  f"含五声外音的和弦 {len(bad)}/{len(ctx['chord_instances'])} = {ratio:.0%}，超过 30%：{names}",
                  "把七和弦/大三和弦换成 add9、sus2、sus4、omit3；七和弦只在高潮或转位处偶尔用。")

    # ---------- M13 段落结构
    names = [n for _, n in ctx["marks"]]
    if not names:
        f.add("warn", None, None, "M13",
              "没有 @marks 段落标记，无法判断结构完整性。",
              "补 @marks：`1=前奏`、`5=主歌A`、`13=副歌` 这样标出段落起点。")
    else:
        has_verse = any("主歌" in n for n in names)
        has_chorus = any("副歌" in n for n in names)
        if not (has_verse and has_chorus):
            miss = "、".join(x for x, ok in (("主歌", has_verse), ("副歌", has_chorus)) if not ok)
            f.add("warn", None, None, "M13",
                  f"段落缺少「{miss}」（现有段落：{'、'.join(names)}）。",
                  "补上主歌/副歌段落标记：`5=主歌A`、`13=副歌`，或按配方结构模板补齐。")

    # ---------- M14 打击预设
    style = ctx["perc"]["style"]
    if style and style not in PERC_PRESETS:
        f.add("error", None, None, "M14",
              f"@perc 预设名「{style}」不存在。合法预设：{'、'.join(PERC_PRESETS)}",
              "改成名单内的预设名，或写 `pattern=36:1@0, 38:0.5@1` 自定义。")

    # ---------- M15 和弦符号
    for bi, chords in enumerate(ctx["chord_bars"]):
        for ch in chords:
            if not ch["valid"]:
                f.add("error", bi + 1, 1, "M15",
                      f"和弦符号「{ch['raw']}」无法解析。",
                      "级数写法：1–7 级 + 后缀 m/m7/maj7/7/dim/sus2/sus4/add9/add2/6/m6/9/omit3，"
                      "转位用 5/7；每格可用逗号写两个和弦。")

    # ---------- 补充检查（SPEC 未编号，仅提示）
    if not ctx["chord_bars"]:
        f.add("info", None, None, "S1", "没有 @chords 和声块，无法检查和声撞音/五声化。",
              "补 @chords：每小节一个级数，如 `6m7 | 1add9 | 5sus4 | 6m |`。")
    elif len(ctx["chord_bars"]) != len(ctx["melody_bars"]):
        f.add("warn", None, None, "S1",
              f"@melody {len(ctx['melody_bars'])} 小节、@chords {len(ctx['chord_bars'])} 小节，数量不一致。",
              "补齐或删掉多余小节，让旋律与和弦一小节一格对齐。")
    if not style and not ctx["perc"]["pattern"]:
        f.add("info", None, None, "S1", "没有 @perc 打击乐块，按「无打击」处理。",
              "需要鼓组时补 `@perc` + `style=锣鼓-中板`（预设名见 SPEC §5），"
              "或 `pattern=36:1@0, 38:0.5@1` 自定义。")
    if ctx["instrument"] not in INSTRUMENTS:
        f.add("info", None, None, "S1",
              f"@instrument「{ctx['instrument']}」不在 SPEC §4 乐器表内。",
              f"从这些 id 里选：{'、'.join(list(INSTRUMENTS)[:8])} 等。")


# ---------------------------------------------------------------- 门禁清单


GATES = [
    ("① 偏音（4/7/#4/b7）不当落音", ["M1"]),
    ("② 偏音不做长音停留", ["M2"]),
    ("③ 无密集小二度（和风/日式预警）", ["M3"]),
    ("④ 大跳后反向级进", ["M4"]),
    ("⑤ 五声正音占比 ≥70%", ["M5"]),
    ("⑥ 终止落调式主音、段末落音得当", ["M6", "M7"]),
    ("⑦ 音域与高潮位置合理", ["M8", "M9"]),
    ("⑧ 长音不撞小二度、和弦五声化", ["M10", "M11"]),
    ("⑨ 结构与可执行性（时值/段落/打击/和弦符号）", ["M12", "M13", "M14", "M15"]),
]


def gate_result(f: Findings, rules: list[str]) -> tuple[str, str]:
    rows = [r for r in f.for_rules(rules) if r["level"] in ("error", "warn")]
    if not rows:
        return "✅", "无问题"
    errs = [r for r in rows if r["level"] == "error"]
    wrs = [r for r in rows if r["level"] == "warn"]
    parts = []
    if errs:
        parts.append(f"error {len(errs)} 条")
    if wrs:
        parts.append(f"warn {len(wrs)} 条")
    first = rows[0]
    return "❌", f"{'、'.join(parts)}；首条：{first['rule']} {pos_text(first['bar'], first['beat'])}"


# ---------------------------------------------------------------- Markdown 报告


def build_report(ctx: dict, f: Findings, source: str) -> tuple[str, bool]:
    errors = f.count("error")
    warns = f.count("warn")
    infos = f.count("info")
    n_modify = errors + warns
    all_gate_pass = all(gate_result(f, rules)[0] == "✅" for _, rules in GATES)
    deliverable = (errors == 0 and all_gate_pass)
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")

    L: list[str] = []
    L.append("# 中国风编曲校验报告（lint_guofeng.py）")
    L.append("")
    L.append(f"- 曲谱：{ctx['title']}")
    L.append(f"- 来源：{source}")
    L.append(f"- 生成时间：{now}")
    L.append(f"- 调与调式：{ctx['key_name']} · {ctx['mode_name']}调式"
             f"（主音简谱 {ctx['mode_tonic_degree']}）/ 音阶 {SCALE_NAMES.get(ctx['scale'], ctx['scale'])}")
    L.append(f"- 拍号/速度：{ctx['meter_num']}/{ctx['meter_den']} · {ctx['bpm']} BPM · "
             f"每小节 {ctx['bar_beats']:g} 拍")
    inst = INSTRUMENTS.get(ctx["instrument"])
    L.append(f"- 主奏乐器：{inst['name'] if inst else ctx['instrument']}（id `{ctx['instrument']}`）")
    L.append(f"- 小节数：{ctx['n_bars']}；旋律音数：{len(ctx['melody_notes'])}；"
             f"和弦数：{len(ctx['chord_instances'])}")
    if ctx["mood"]:
        L.append(f"- 情绪标注：{ctx['mood']}")
    L.append("")

    # 一、概览
    L.append("## 一、结论概览")
    L.append("")
    L.append("| 级别 | 条数 | 含义 |")
    L.append("|---|---|---|")
    L.append(f"| error | {errors} | 必须改，否则不可交付 |")
    L.append(f"| warn | {warns} | 建议改，影响质量评分 |")
    L.append(f"| info | {infos} | 仅供了解，不影响判定 |")
    L.append("")
    if deliverable:
        L.append("**结论：可交付** —— 无 error，九道门禁全部通过。")
    elif errors == 0:
        L.append(f"**结论：需修改 {n_modify} 处** —— 无 error，但仍有 warn 项建议处理。")
    else:
        L.append(f"**结论：需修改 {n_modify} 处** —— 其中 error {errors} 条必须修。")
    L.append("")

    # 二、段落
    L.append("## 二、段落结构")
    L.append("")
    L.append("| 小节范围 | 段落名 | 小节数 |")
    L.append("|---|---|---|")
    for s, e, name in ctx["sections"]:
        L.append(f"| {s}–{e} | {name} | {e - s + 1} |")
    L.append("")

    # 三、逐条发现
    L.append("## 三、逐条发现")
    L.append("")
    rows = f.sorted_rows()
    if not rows:
        L.append("未发现任何问题（error/warn/info 均为 0）。可以直接进入导出 MIDI 与试听环节。")
    else:
        L.append("| 级别 | 位置 | 规则 | 说明 | 修法 |")
        L.append("|---|---|---|---|---|")
        for r in rows:
            lvl = {"error": "error ❌", "warn": "warn ⚠️", "info": "info ℹ️"}.get(r["level"], r["level"])
            msg = str(r["msg"]).replace("|", "\\|")
            fix = str(r["fix"]).replace("|", "\\|")
            L.append(f"| {lvl} | {pos_text(r['bar'], r['beat'])} | {r['rule']} | {msg} | {fix} |")
    L.append("")

    # 四、规则明细
    L.append("## 四、规则执行明细（M1–M15）")
    L.append("")
    L.append("| 编号 | 规则摘要 | 结果 |")
    L.append("|---|---|---|")
    rule_brief = {
        "M1": "偏音不作落音（段末/句末，时值 ≥1 拍）",
        "M2": "偏音单音时值 ≤1 拍（不做长音）",
        "M3": "小二度相邻进行 ≤20% 音程",
        "M4": "≥9 半音跳进后反向级进（≤4 半音）",
        "M5": "五声正音占比 ≥70%",
        "M6": "全曲终止音 = 调式主音",
        "M7": "段末落音 ∈ {主音, 属音, 主和弦音}",
        "M8": "音域跨度 ≤24 半音（>30 error）；乐器音域仅 info",
        "M9": "全曲最高音不出现在前半段",
        "M10": "≥2 拍旋律长音不与同拍和弦小二度相撞",
        "M11": "含五声外音的和弦 ≤30%",
        "M12": "小节时值 = 拍号要求",
        "M13": "段落含主歌与副歌",
        "M14": "@perc 预设名存在",
        "M15": "和弦符号可解析",
    }
    for code in [f"M{i}" for i in range(1, 16)]:
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
            head = "❌ " if (e or w) else "ℹ️ "
            res = head + " / ".join(bits)
        L.append(f"| {code} | {rule_brief[code]} | {res} |")
    # 补充检查
    supp = f.for_rules(["S1", "S2", "S3"])
    if supp:
        bits = []
        for lvl in ("error", "warn", "info"):
            c = len([h for h in supp if h["level"] == lvl])
            if c:
                bits.append(f"{lvl} {c}")
        L.append(f"| S1–S3 | 补充检查（块缺失/小节数一致性/token 可解析） | {'、'.join(bits)} |")
    L.append("")

    # 五、门禁清单
    L.append("## 五、门禁清单（九大误区逐条打勾）")
    L.append("")
    L.append("| # | 误区 | 判定 | 依据 |")
    L.append("|---|---|---|---|")
    for title, rules in GATES:
        mark, why = gate_result(f, rules)
        L.append(f"| {title.split(' ', 1)[0]} | {title.split(' ', 1)[1]} | {mark} | {why} |")
    L.append("")
    checked = sum(1 for title, rules in GATES if gate_result(f, rules)[0] == "✅")
    L.append(f"门禁通过数：**{checked}/9**；error **{errors}** 条 / warn **{warns}** 条。")
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
    L.append("1. 按上表「修法」逐条改 .jp（先修 error，再处理 warn）；")
    L.append("2. 重跑本脚本直到 error = 0；")
    L.append("3. 导出 MIDI：`python scripts/jianpu2midi.py --input 你的谱.jp --out 你的谱.mid`。")
    L.append("")
    return "\n".join(L), deliverable


# ---------------------------------------------------------------- CLI


def _demo_out_dir() -> Path:
    """demo 产物一律写到系统临时目录，避免污染上架包（scripts/ 会被打包扫描）。"""
    d = Path(tempfile.gettempdir()) / "guofeng-music-out"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = SCRIPT_DIR  # 临时目录不可写时退回脚本目录
    return d


def _default_report(input_path: Path | None) -> Path:
    if input_path is not None:
        return input_path.with_name(input_path.stem + "-校验.md")
    return _demo_out_dir() / "guofeng-lint.md"


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="lint_guofeng.py",
        description="中国风简谱 DSL 校验：SPEC §3 的 M1–M15 + 九大误区门禁清单。纯标准库。",
        epilog=("示例：\n"
                "  python lint_guofeng.py                       # demo → <临时目录>/guofeng-lint.md\n"
                "  python lint_guofeng.py --input 我的谱.jp     # → 同目录/我的谱-校验.md\n"
                "  python lint_guofeng.py --input 我的谱.jp --report 校验.md\n"
                "默认报告名：demo/无参数 → <临时目录>/guofeng-lint.md；--input 无 --report → <输入名>-校验.md\n"
                "退出码：0 无 error；1 有 error；2 参数/文件问题"),
    )
    parser.add_argument("--input", help="输入简谱 DSL 文件（.jp）")
    parser.add_argument("--report", help="输出 Markdown 报告路径（默认见上）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 谱做校验")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    report_path = Path(args.report).expanduser() if args.report else _default_report(input_path)

    try:
        if input_path is not None:
            if not input_path.exists():
                print(f"❌ 找不到输入文件：{input_path}", file=sys.stderr)
                print("下一步：确认路径；或先跑 `python lint_guofeng.py --demo` 看输入格式。", file=sys.stderr)
                return 2
            text = read_text_file(input_path)
            source = str(input_path)
        else:
            text = DEFAULT_DEMO_JP
            source = "内置 demo（8 小节 D 羽调式）"

        ctx = build_context(text)
        f = Findings()
        rule_checks(ctx, f)
        report, deliverable = build_report(ctx, f, source)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")

        errors = f.count("error")
        warns = f.count("warn")
        infos = f.count("info")
        print("")
        print("=" * 62)
        print(f"📋 校验完成：{ctx['title']}")
        print(f"   error {errors} 条 / warn {warns} 条 / info {infos} 条")
        if errors:
            for r in f.sorted_rows():
                if r["level"] == "error":
                    print(f"   ❌ {r['rule']} {pos_text(r['bar'], r['beat'])}：{r['msg'][:60]}")
        print(f"   报告：{report_path}")
        print(f"   结论：{'可交付' if deliverable else f'需修改 {errors + warns} 处'}")
        print("=" * 62)
        print("下一步：按报告里的「修法」改谱 → 重跑本脚本 → error 归零后再导出 MIDI。")
        return 1 if errors else 0
    except SystemExit:
        raise
    except Exception as exc:
        print(f"❌ 校验失败：{exc}", file=sys.stderr)
        print("下一步：① 先用 --demo 确认脚本本身正常；② 检查 .jp 是否有 @melody 与 @chords 块；"
              "③ 把报错原文发给开发者。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
