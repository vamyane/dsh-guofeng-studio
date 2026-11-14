#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jianpu2lyricslots.py —— 作曲技能 .jp → 填词槽位表（曲 → 词 方向）

解析作曲技能的简谱 DSL（.jp），按 PLAN-LYRIC §4.1 的断句规则切成「句」，
产出 <name>.slots.json（字段名冻结，严格照 INTEROP v1 契约）+ <name>.slots.md（人读表）。

断句规则（写死）：
  - 以 ≥1.5 拍长音或 ≥1 拍休止为句尾；
  - 每句最多跨 2 小节；
  - 句内音符数 = syllables（一字一音为准），min_syllables = syllables - 2。

用法：
  python jianpu2lyricslots.py
        无参数 = 内置 demo 曲，产物写到系统临时目录
        guofeng-lyric-out/填词槽位-demo.slots.json / .slots.md
  python jianpu2lyricslots.py --demo
        同上（显式 demo）
  python jianpu2lyricslots.py --input 江南雨.jp
        输出 同目录/江南雨.slots.json + 江南雨.slots.md
  python jianpu2lyricslots.py --input 江南雨.jp --out 江南雨-填词槽位
        输出 江南雨-填词槽位.slots.json + 江南雨-填词槽位.slots.md
  python jianpu2lyricslots.py --help

纯标准库；不 import 作曲技能的任何脚本（只认 .jp 文件格式）。
退出码：0 正常；2 参数/文件/解析问题。
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

VERSION = "1.0.0"
SKILL = "guofeng-lyricist"

LONG_NOTE = 1.5   # ≥1.5 拍长音 = 句尾
LONG_REST = 1.0   # ≥1 拍休止 = 句尾
MAX_BARS_PER_LINE = 2

BLOCK_NAMES = {"marks", "melody", "chords", "bass", "perc"}

TOKEN_RE = re.compile(r"^([#b]?)([0-7])([',]*)(?:[:/](\d+(?:\.\d+)?))?$")
MARK_RE = re.compile(r"^(\d+)\s*=\s*(.+)$")

DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

MODE_NAMES = {"gong": "宫", "shang": "商", "jue": "角", "zhi": "徵", "yu": "羽"}
MODE_ALIAS = {"宫": "gong", "商": "shang", "角": "jue", "徵": "zhi", "羽": "yu",
              "gong": "gong", "shang": "shang", "jue": "jue", "zhi": "zhi", "yu": "yu"}
SCALE_NAMES = {"wusheng": "五声", "qingyue": "清乐", "yayue": "雅乐", "yanyue": "燕乐"}

# 调式 → 推荐辙口（按落音与调式色彩；主 2 备，给理由）
MODE_ZHE = {
    "gong": (["言前", "江阳"], "宫调式落音 1，明亮开阔，宜宽辙"),
    "shang": (["江阳", "言前"], "商调式落音 2，有行进感，宜开口辙"),
    "jue": (["人辰", "一七"], "角调式落音 3，偏暗偏窄，宜细辙"),
    "zhi": (["江阳", "遥条"], "徵调式落音 5，最明亮，宜宏亮辙"),
    "yu": (["言前", "人辰"], "羽调式落音 6，柔而不伤，宜宽而收得住"),
}

# 纯器乐段落（不填词）
INSTRUMENTAL_HINTS = ("前奏", "间奏", "过门", "尾奏", "intro", "interlude")

DEFAULT_DEMO_JP = """# jianpu2lyricslots.py 内置 demo（8 小节 · D 羽调式 · 4/4 · 72 BPM）
@title 山月不知
@key D
@mode yu
@scale qingyue
@meter 4/4
@tempo 72
@instrument xiao
@style shuqing
@mood 清冷、山月、旧约

@marks
1=前奏
3=主歌A
7=副歌

@melody
6:2 1':1 2':1 | 3':2 2':1 1':1 | 6:1 1':1 2':1 3:1 | 5:2 6:2 |
6:1 1:1 2:1 0:1 | 3:2 2:1 1:1 | 6:2 5:1 3:1 | 6:4 |

@chords
6m | 5sus4 | 1add9 | 5sus4 |
6m | 4add9 | 5sus4 | 6m |

@perc
style=锣鼓-中板
"""


# INTEROP v1 契约样例（写进 Markdown，字段名冻结；取值示意）
CONTRACT_SAMPLE = {
    "meta": {"skill": "guofeng-lyricist", "version": "1.0.0",
             "source": "江南雨.jp", "title": "江南雨", "key": "D", "mode": "yu",
             "scale": "qingyue", "meter": "4/4", "tempo": 72},
    "sections": [
        {"name": "主歌A", "start_bar": 5, "bars": 8,
         "lines": [
             {"line": 1, "bars": [5, 6], "beats": 8, "syllables": 7, "min_syllables": 5,
              "rhyme": False, "cadence": "6", "contour": "6-1'-2'-3'",
              "tone_hints": ["平", "平", "仄", "仄", "平", "仄", "平"],
              "rest_at_end": 1.0, "long_notes": [{"beat": 3.5, "dur": 1.5}]}
         ]}
    ],
    "rhyme_plan": {"rhyme_lines": [2, 4], "recommended_che": ["言前", "人辰"],
                   "note": "每段偶句押韵，句尾长音处必须押"},
    "next": ["把每句字数写成词，韵脚服从 rhyme_plan",
             "填好后跑 lint_guofeng_lyric.py --slots 江南雨-填词槽位.slots.json"],
}


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


def parse_int(text: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(float(str(text).strip()))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def parse_meter(text: str) -> tuple[int, int, float]:
    s = (text or "4/4").strip().replace(" ", "")
    m = re.match(r"^(\d+)/(\d+)$", s)
    if not m:
        return 4, 4, 4.0
    num, den = int(m.group(1)), int(m.group(2))
    if num <= 0 or den <= 0:
        return 4, 4, 4.0
    return num, den, num * 4.0 / den


def pitch_label(degree: int, oct_shift: int, acc: int = 0) -> str:
    pre = "#" if acc > 0 else ("b" if acc < 0 else "")
    marks = ("'" * oct_shift) if oct_shift > 0 else ("," * (-oct_shift))
    return f"{pre}{degree}{marks}"


# ================================================================ .jp 解析


def split_jp(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    headers: dict[str, str] = {}
    blocks: dict[str, list[str]] = {}
    cur = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("@"):
            body = s[1:].strip()
            parts = body.split(None, 1)
            name = parts[0].strip().lower() if parts else ""
            rest = parts[1].strip() if len(parts) > 1 else ""
            if name in BLOCK_NAMES:
                cur = name
                blocks.setdefault(name, [])
                if rest:
                    blocks[name].append(rest)
            else:
                cur = ""
                headers[name] = rest
        elif cur:
            blocks[cur].append(s)
    return headers, blocks


def parse_melody(lines: list[str]) -> tuple[list[list[dict]], list[str]]:
    """→ (每小节 token 列表, 无法解析的 token)。"""
    bars: list[list[dict]] = []
    bad: list[str] = []
    for line in lines:
        parts = [p.strip() for p in line.split("|") if p.strip()]
        for part in parts:
            toks: list[dict] = []
            for word in part.split():
                m = TOKEN_RE.match(word)
                if not m:
                    bad.append(word)
                    continue
                deg = int(m.group(2))
                dur = float(m.group(4)) if m.group(4) else 1.0
                if dur <= 0:
                    bad.append(word)
                    continue
                oct_shift = m.group(3).count("'") - m.group(3).count(",")
                acc = 1 if m.group(1) == "#" else (-1 if m.group(1) == "b" else 0)
                toks.append({
                    "raw": word, "degree": deg, "acc": acc, "oct": oct_shift,
                    "dur": dur, "rest": deg == 0,
                    "semis": (DEGREE_SEMITONES.get(deg, 0) + acc + 12 * oct_shift) if deg else 0,
                    "label": "0" if deg == 0 else pitch_label(deg, oct_shift, acc),
                })
            bars.append(toks)
    return bars, bad


def parse_marks(lines: list[str]) -> list[tuple[int, str]]:
    out = []
    for line in lines:
        m = MARK_RE.match(line.strip())
        if not m:
            continue
        bar = int(m.group(1))
        name = m.group(2).strip()
        if bar >= 1 and name:
            out.append((bar, name))
    out.sort(key=lambda x: x[0])
    return out


# ================================================================ 断句（INTEROP v1）


def build_lines(bars: list[list[dict]], marks: list[tuple[int, str]],
                strict: bool = False, bar_beats: float = 4.0) -> list[dict]:
    """按 PLAN-LYRIC §4.1 断句。

    默认（musical，推荐）：长音/长休止只有在**小节末**（或出现 ≥2 拍强休止）时才算句尾，
    小节中间的长音当作句内拖腔——否则 `6:2 1':1 2':1 | ...` 这种写法会被切成
    一堆 1 字小句，根本没法填词。
    strict=True：按 §4.1 字面执行（任何 ≥1.5 拍长音 / ≥1 拍休止即收句），用于逐字对拍。

    两种模式都遵守：每句最多跨 2 小节；段落边界收句。
    """
    total_bars = len(bars)
    if total_bars == 0:
        return []
    starts = [b for b, _ in marks]
    if not starts or starts[0] != 1:
        marks = [(1, "全曲")] + [m for m in marks if m[0] > 1]
        starts = [b for b, _ in marks]
    # 段落范围
    sec_ranges: list[tuple[int, int, str]] = []
    for i, (bar, name) in enumerate(marks):
        end = marks[i + 1][0] - 1 if i + 1 < len(marks) else total_bars
        if end < bar:
            end = total_bars
        sec_ranges.append((bar, end, name))

    def section_of(bar_no: int) -> str:
        for s, e, nm in sec_ranges:
            if s <= bar_no <= e:
                return nm
        return sec_ranges[-1][2] if sec_ranges else "全曲"

    lines: list[dict] = []
    cur: list[dict] = []   # 当前句的 token（含休止）
    cur_bars: list[int] = []
    cur_start_sec = ""

    def close(reason: str) -> None:
        nonlocal cur, cur_bars, cur_start_sec
        if not cur:
            return
        pitched = [t for t in cur if not t["rest"]]
        if not pitched:
            cur, cur_bars, cur_start_sec = [], [], ""
            return
        lines.append({
            "tokens": cur,
            "bars": [cur_bars[0], cur_bars[-1]],
            "beats": round(sum(t["dur"] for t in cur), 3),
            "section": cur_start_sec,
            "end_reason": reason,
        })
        cur, cur_bars, cur_start_sec = [], [], ""

    for bar_idx, toks in enumerate(bars, 1):
        # 跨小节：如果当前句已跨 2 小节，进第 3 小节前必须收句
        if cur and cur_bars and bar_idx > cur_bars[0] + MAX_BARS_PER_LINE - 1:
            close("跨满 2 小节")
        if not cur:
            cur_start_sec = section_of(bar_idx)
        if bar_idx not in cur_bars:
            cur_bars.append(bar_idx)
        pos = 0.0
        for tk in toks:
            # 句内被收句后，同一小节里还要重新起句：补记起句小节与段落
            if not cur:
                cur_start_sec = section_of(bar_idx)
            if not cur_bars:
                cur_bars.append(bar_idx)
            t = dict(tk)
            t["bar"] = bar_idx
            t["beat_in_bar"] = pos + 1.0
            cur.append(t)
            pos += t["dur"]
            if strict:
                if t["rest"] and t["dur"] >= LONG_REST - 1e-9:
                    close("句尾休止 ≥1 拍")
                elif (not t["rest"]) and t["dur"] >= LONG_NOTE - 1e-9:
                    close("句尾长音 ≥1.5 拍")
            else:
                # 默认模式：≥2 拍的强休止随时收句（明显换气）
                if t["rest"] and t["dur"] >= 2 * LONG_REST - 1e-9:
                    close("句尾强休止 ≥2 拍")
        if not strict and cur and toks:
            last = toks[-1]
            at_bar_end = abs(pos - bar_beats) < 1e-6 or pos >= bar_beats - 1e-6
            if at_bar_end:
                if last["rest"] and last["dur"] >= LONG_REST - 1e-9:
                    close("句尾休止 ≥1 拍（落小节末）")
                elif (not last["rest"]) and last["dur"] >= LONG_NOTE - 1e-9:
                    close("句尾长音 ≥1.5 拍（落小节末）")
        # 段边界处收句
        if bar_idx in starts and bar_idx != starts[0] and cur:
            close("段落边界")
    close("全曲结束")
    return lines


# ================================================================ 槽位字段（契约）


def tone_hints_for(tokens: list[dict]) -> list[str]:
    """→ 每字「平/仄」。依字行腔：句尾落音/长音→平；上行→平；下行≥2 度→仄；同音→平。"""
    pitched = [t for t in tokens if not t["rest"]]
    hints: list[str] = []
    for i, t in enumerate(pitched):
        if i == len(pitched) - 1:
            hints.append("平")  # 句尾落音，可拖
            continue
        interval = pitched[i + 1]["semis"] - t["semis"]
        if interval <= -2:
            hints.append("仄")
        else:
            hints.append("平")
    return hints


def line_record(idx_in_sec: int, global_no: int, ln: dict, bar_beats: float) -> dict:
    tokens = ln["tokens"]
    pitched = [t for t in tokens if not t["rest"]]
    contour = [t["label"] for t in pitched]
    last_note = pitched[-1]
    rest_at_end = 0.0
    for t in reversed(tokens):
        if t["rest"]:
            rest_at_end += t["dur"]
        else:
            break
    long_notes = []
    pos = 0.0
    for t in tokens:
        if not t["rest"] and t["dur"] >= LONG_NOTE - 1e-9:
            long_notes.append({"beat": round(pos + 1.0, 3), "dur": t["dur"]})
        pos += t["dur"]
    return {
        "line": idx_in_sec,
        "global_line": global_no,
        "bars": ln["bars"],
        "beats": ln["beats"],
        "syllables": len(pitched),
        "min_syllables": max(1, len(pitched) - 2),
        "rhyme": idx_in_sec % 2 == 0,
        "cadence": last_note["label"],
        "contour": "-".join(contour),
        "tone_hints": tone_hints_for(tokens),
        "rest_at_end": round(rest_at_end, 3),
        "long_notes": long_notes,
        "end_reason": ln["end_reason"],
    }


def build_slots(text: str, source: str, strict: bool = False) -> tuple[dict, list[str], list[str]]:
    headers, blocks = split_jp(text)
    warnings: list[str] = []
    bars, bad = parse_melody(blocks.get("melody", []))
    if bad:
        warnings.append(f"有 {len(bad)} 个旋律 token 无法解析，已跳过："
                        f"{'、'.join(bad[:6])}{'…' if len(bad) > 6 else ''}")
    if not bars:
        raise ValueError("没有解析到 @melody 块（写法：`@melody` 后接 `6:2 1':1 | 3':2 ...`）")
    marks = parse_marks(blocks.get("marks", []))
    if not marks:
        warnings.append("没有 @marks 段落标记，已按「全曲」一段处理；建议在 .jp 里补 1=前奏、5=主歌A…")

    num, den, bar_beats = parse_meter(headers.get("meter", "4/4"))
    mode_raw = (headers.get("mode", "yu") or "yu").strip().lower()
    mode = MODE_ALIAS.get(mode_raw, "yu")
    key = (headers.get("key", "D") or "D").strip()
    scale = (headers.get("scale", "qingyue") or "qingyue").strip().lower()
    title = (headers.get("title", "") or Path(source).stem).strip()
    bpm = parse_int(headers.get("tempo", "72"), 72, 20, 300)

    raw_lines = build_lines(bars, marks, strict=strict, bar_beats=bar_beats)
    # 段落分组
    order: list[str] = []
    grouped: dict[str, list[dict]] = {}
    instr_skipped: list[str] = []
    for ln in raw_lines:
        name = ln["section"]
        if any(h in name.lower() for h in INSTRUMENTAL_HINTS):
            if name not in instr_skipped:
                instr_skipped.append(name)
            continue
        if name not in grouped:
            grouped[name] = []
            order.append(name)
        grouped[name].append(ln)
    if instr_skipped:
        warnings.append(f"跳过纯器乐段落（不填词）：{'、'.join(instr_skipped)}")

    sections: list[dict] = []
    rhyme_lines: list[int] = []
    global_no = 0
    for name in order:
        lines = grouped[name]
        bars_span = [lines[0]["bars"][0], lines[-1]["bars"][1]]
        recs = []
        for i, ln in enumerate(lines, 1):
            global_no += 1
            rec = line_record(i, global_no, ln, bar_beats)
            recs.append(rec)
            if rec["rhyme"]:
                rhyme_lines.append(global_no)
        sections.append({
            "name": name,
            "start_bar": bars_span[0],
            "bars": max(1, bars_span[1] - bars_span[0] + 1),
            "lines": recs,
        })
    if not sections:
        raise ValueError("旋律里没有可填词的段落（全部被识别为器乐段），请检查 @marks 的段落名")

    che, why = MODE_ZHE.get(mode, MODE_ZHE["yu"])
    slots = {
        "meta": {
            "skill": SKILL,
            "line_break_mode": "strict(PLAN §4.1 字面)" if strict else "musical(长音/休止落小节末)",
            "version": VERSION,
            "source": source,
            "title": title,
            "key": key,
            "mode": mode,
            "scale": scale,
            "meter": f"{num}/{den}",
            "tempo": bpm,
        },
        "sections": sections,
        "rhyme_plan": {
            "rhyme_lines": rhyme_lines,
            "recommended_che": che,
            "note": f"{MODE_NAMES[mode]}调式，{why}。每段偶句押韵，句尾长音处必须押；"
                    f"同段内不要换辙（lint L1 会报）。",
        },
        "next": [
            "把每句字数写成词，韵脚服从 rhyme_plan",
            "填好后跑 lint_guofeng_lyric.py --slots 江南雨-填词槽位.slots.json",
        ],
        "generated": _dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": {
            "bars": len(bars),
            "sections": len(sections),
            "lines": global_no,
            "syllables_total": sum(len([t for t in ln["tokens"] if not t["rest"]])
                                   for ln in raw_lines),
        },
    }
    return slots, warnings, [f"{b}=" + n for b, n in marks]


# ================================================================ Markdown

END_REASON_TEXT = {
    "句尾长音 ≥1.5 拍": "长音收句（§4.1 字面）",
    "句尾休止 ≥1 拍": "休止收句（§4.1 字面）",
    "句尾长音 ≥1.5 拍（落小节末）": "长音落小节末收句",
    "句尾休止 ≥1 拍（落小节末）": "休止落小节末收句",
    "句尾强休止 ≥2 拍": "≥2 拍强休止收句",
    "跨满 2 小节": "满 2 小节被迫收句（下句可能要抢字，注意字数）",
    "段落边界": "段落边界收句",
    "全曲结束": "曲终收句",
}


def _long_notes_text(notes: list[dict]) -> str:
    if not notes:
        return "—"
    return "、".join(f"{n['beat']:g}@{n['dur']:g}" for n in notes)


def build_markdown(slots: dict, warns: list[str], marks_text: list[str]) -> str:
    meta = slots["meta"]
    sections = slots["sections"]
    L: list[str] = []
    L.append(f"# 填词槽位表 · {meta['title']}")
    L.append("")
    L.append(f"> 由 `jianpu2lyricslots.py` v{VERSION} 生成于 {slots['generated']}；"
             f"曲源 `{meta['source']}`。字段名按《中国风作词》INTEROP v1 冻结。")
    L.append("")
    L.append("## 一、曲目信息")
    L.append("")
    L.append("| 项目 | 取值 |")
    L.append("|---|---|")
    L.append(f"| 曲名 | {meta['title']} |")
    L.append(f"| 调 / 调式 | {meta['key']} / {MODE_NAMES.get(meta['mode'], meta['mode'])}调式 |")
    L.append(f"| 音阶 | {SCALE_NAMES.get(meta['scale'], meta['scale'])} |")
    L.append(f"| 拍号 / 速度 | {meta['meter']} · {meta['tempo']} BPM |")
    L.append(f"| 小节数 | {slots['stats']['bars']} |")
    L.append(f"| 段落 / 句数 | {slots['stats']['sections']} 段 / {slots['stats']['lines']} 句 |")
    L.append(f"| 可用音节总数 | {slots['stats']['syllables_total']}（一字一音为准） |")
    L.append(f"| 断句模式 | {meta.get('line_break_mode', 'musical')} |")
    L.append("")
    L.append("断句口径（PLAN-LYRIC §4.1）：以 ≥1.5 拍长音或 ≥1 拍休止为句尾，每句最多跨 2 小节。"
             "默认模式要求长音/休止**落在小节末**才算句尾——小节中间的长音算句内拖腔，"
             "否则 `6:2 1':1 2':1` 这种写法会被切成一堆 1 字小句，没法填词；"
             "要按字面逐音对齐请加 `--strict`。")
    L.append("")
    if marks_text:
        L.append("段落标记（来自 `.jp` 的 `@marks`）：`" + "，".join(marks_text) + "`")
        L.append("")
    if warns:
        L.append("解析提示：")
        L.append("")
        for w in warns:
            L.append(f"- {w}")
        L.append("")

    L.append("## 二、押韵方案")
    L.append("")
    rp = slots["rhyme_plan"]
    L.append(f"- 建议辙口：**{rp['recommended_che'][0]}**（备：{'、'.join(rp['recommended_che'][1:]) or '无'}）")
    L.append(f"- 理由：{rp['note']}")
    L.append(f"- 押韵句（全局句号）：{'、'.join(str(x) for x in rp['rhyme_lines']) or '无'}")
    L.append("")
    L.append("> 全局句号 = 按报告顺序数下来的第几句（跳过器乐段）。")
    L.append("")

    L.append("## 三、逐句槽位")
    L.append("")
    L.append("| 段落 | 句 | 全局 | 小节 | 拍数 | 音节 | 最少 | 押韵 | 句尾落音 | 声调建议 | 长音 | 句尾休止 | 断句依据 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for sec in sections:
        for r in sec["lines"]:
            L.append(
                f"| {sec['name']} | {r['line']} | {r['global_line']} | "
                f"{r['bars'][0]}–{r['bars'][1]} | {r['beats']:g} | {r['syllables']} | "
                f"{r['min_syllables']} | {'✅' if r['rhyme'] else '—'} | {r['cadence']} | "
                f"{''.join(r['tone_hints'])} | {_long_notes_text(r['long_notes'])} | "
                f"{r['rest_at_end']:g} | {END_REASON_TEXT.get(r['end_reason'], r['end_reason'])} |")
    L.append("")
    L.append("读表说明：")
    L.append("")
    L.append("- **音节** = 这句能放几个字（一字一音）；**最少** = 允许一字多音时的最少字数（syllables−2）。")
    L.append("- **声调建议**：`平` 可放阴平/阳平/上声拖长；`仄` 建议放去声（下行音程处）。")
    L.append("- **句尾落音**是简谱级数（`'` 表示高八度），句尾可用 -cadence 对齐到调式主音。")
    L.append("- **长音**列写 `拍位@时值`，长音处是拖腔位，别放仄声字。")
    L.append("")

    L.append("## 四、填词怎么做（照这个顺序）")
    L.append("")
    L.append("1. 先按「音节」列把每句字数写死（副歌可以按最少字数列再留 2 个拖腔字）；")
    L.append("2. 韵脚只落在「押韵 ✅」的句子尾部，且句尾必须押同一个辙；")
    L.append("3. 句尾落音处不要放去声字（会倒字），放阴平/阳平/上声拖长；")
    L.append("4. 句尾休止 ≥1 拍的句子，句末语气要收住（别写「的」「了」这类悬空字）；")
    L.append("5. 填完跑：`python scripts/lint_guofeng_lyric.py --input 你的词.lyr --slots 本文件同名的 .slots.json`；")
    L.append("6. 想把词再变回骨谱：`python scripts/lyric2jianpu.py --input 你的词.lyr --out 你的.jp`。")
    L.append("")
    L.append("## 五、JSON 契约（字段名冻结）")
    L.append("")
    L.append("完整字段结构（真实取值见同名 `.slots.json`）：")
    L.append("")
    L.append("```json")
    L.append(json.dumps(CONTRACT_SAMPLE, ensure_ascii=False, indent=2))
    L.append("```")
    L.append("")
    L.append("字段说明：`meta`（skill/version/source/title/key/mode/scale/meter/tempo）、"
             "`sections[].{name,start_bar,bars,lines[]}`、"
             "`lines[].{line,bars,beats,syllables,min_syllables,rhyme,cadence,contour,"
             "tone_hints,rest_at_end,long_notes}`、`rhyme_plan`、`next`。"
             "（另附 `global_line/end_reason/generated/stats` 为增强字段，可忽略。）")
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


def resolve_out(out_arg: str | None, input_path: Path | None) -> tuple[Path, Path]:
    if out_arg:
        p = Path(out_arg).expanduser()
        if p.suffix.lower() in (".json", ".md"):
            base = p.with_suffix("")
        elif p.is_dir():
            base = p / "填词槽位"
        else:
            base = p
        return Path(str(base) + ".slots.json"), Path(str(base) + ".slots.md")
    if input_path is not None:
        return (input_path.with_name(input_path.stem + ".slots.json"),
                input_path.with_name(input_path.stem + ".slots.md"))
    d = _demo_out_dir()
    return d / "填词槽位-demo.slots.json", d / "填词槽位-demo.slots.md"


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="jianpu2lyricslots.py",
        description="作曲 .jp → 填词槽位表（.slots.json + .slots.md）。纯标准库，字段名按 INTEROP v1 冻结。",
        epilog=("示例：\n"
                "  python jianpu2lyricslots.py                          # demo → <临时目录>/guofeng-lyric-out/\n"
                "  python jianpu2lyricslots.py --input 江南雨.jp        # → 同目录/江南雨.slots.json + .md\n"
                "  python jianpu2lyricslots.py --input 江南雨.jp --out 江南雨-填词槽位\n"
                "断句规则：≥1.5 拍长音或 ≥1 拍休止为句尾；每句最多跨 2 小节。"),
    )
    parser.add_argument("--input", help="输入简谱 DSL（.jp，来自《中国风音乐创作》）")
    parser.add_argument("--out", help="输出前缀或目录（默认见上）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 曲生成槽位")
    parser.add_argument("--strict", action="store_true",
                        help="严格按 PLAN §4.1 字面断句（任何 ≥1.5 拍长音 / ≥1 拍休止即收句；会产生很多短句）")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    json_path, md_path = resolve_out(args.out, input_path)

    try:
        if input_path is not None:
            if not input_path.exists():
                print(f"❌ 找不到输入文件：{input_path}", file=sys.stderr)
                print("下一步：确认路径；或跑 `python jianpu2lyricslots.py --demo` 看输入格式。", file=sys.stderr)
                return 2
            text = read_text_file(input_path)
            source = str(input_path)
        else:
            text = DEFAULT_DEMO_JP
            source = "内置 demo（8 小节 D 羽调式）"

        slots, warns, marks_text = build_slots(text, source, strict=args.strict)
        md = build_markdown(slots, warns, marks_text)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(slots, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        md_path.write_text(md, encoding="utf-8")

        total_lines = slots["stats"]["lines"]
        print("")
        print("=" * 62)
        print(f"🎼 填词槽位已生成：{slots['meta']['title']}")
        print(f"   曲源：{source}")
        print(f"   段落 {slots['stats']['sections']} / 句数 {total_lines} / "
              f"可用音节 {slots['stats']['syllables_total']}")
        print(f"   建议辙口：{slots['rhyme_plan']['recommended_che'][0]}"
              f"（备 {'、'.join(slots['rhyme_plan']['recommended_che'][1:]) or '—'}）")
        print(f"   押韵句（全局）：{'、'.join(str(x) for x in slots['rhyme_plan']['rhyme_lines']) or '无'}")
        for w in warns:
            print(f"   ⚠️  {w}")
        print(f"   JSON：{json_path}")
        print(f"   Markdown：{md_path}")
        print("=" * 62)
        print("下一步：按槽位每句字数写词 → `python scripts/lint_guofeng_lyric.py --input 你的词.lyr "
              f"--slots {json_path.name}`。")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # 任何输入都不抛 traceback
        print(f"❌ 生成槽位失败：{exc}", file=sys.stderr)
        print("下一步：① 先 `python jianpu2lyricslots.py --demo` 确认脚本正常；"
              "② 检查 .jp 是否有 `@melody` 块与 `@marks` 段名；"
              "③ 旋律 token 写法应为 `音级:时值`（如 `6:2`、`1':1`）。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
