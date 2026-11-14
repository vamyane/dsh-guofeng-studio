#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lyric2jianpu.py —— 歌词 .lyr → 五声简谱骨架 .jp（词 → 曲 方向）

按四声声调走向生成音高轮廓（依字行腔）：
  阴平(1)：同音或 +1 级（连续阴平时阶梯上行，避免一条直线）
  阳平(2)：+2 度上行
  上声(3)：先 −2 后 +2（拆成两个音，总时值不变）
  去声(4)：−2~−3 度下行
  轻声/未知(0)：同前一字
句尾一律落到 `--cadence` 指定的调式音；越界时八度回折，默认始终留在五声音阶内
（`--allow-bianyin` 才允许 4/7 作经过音）。

产出 .jp 头部完整（@title/@key/@mode/@scale/@meter/@tempo/@marks/@melody[/@chords]），
可直接喂给作曲技能：`python ../guofeng-music/package/scripts/jianpu2midi.py --input 骨架.jp`

用法：
  python lyric2jianpu.py
        无参数 = 内置 demo 词，产物写到系统临时目录 guofeng-lyric-out/词谱曲骨架-demo.jp
  python lyric2jianpu.py --demo
        同上（显式 demo）
  python lyric2jianpu.py --input 山月不知.lyr
        输出 同目录/山月不知.jp
  python lyric2jianpu.py --input 山月不知.lyr --key D --mode yu --cadence 6 \
      --tempo 72 --meter 4/4 --chords "6m | 4add9 | 5sus4 | 6m |" --out 山月不知.jp
  python lyric2jianpu.py --input 词.lyr --allow-bianyin
  python lyric2jianpu.py --help

退出码：0 正常；2 参数/文件/解析问题。
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent  # 不依赖 cwd

VERSION = "1.0.0"

PENTA = [1, 2, 3, 5, 6]                       # 五声：宫商角徵羽
DEGREE_SEMITONES = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

MODE_NAMES = {"gong": "宫", "shang": "商", "jue": "角", "zhi": "徵", "yu": "羽"}
MODE_ALIAS = {"宫": "gong", "商": "shang", "角": "jue", "徵": "zhi", "羽": "yu",
              "gong": "gong", "shang": "shang", "jue": "jue", "zhi": "zhi", "yu": "yu",
              "gongdiao": "gong", "shangdiao": "shang", "juediao": "jue",
              "zhidiao": "zhi", "yudiao": "yu"}
MODE_TONIC = {"gong": 1, "shang": 2, "jue": 3, "zhi": 5, "yu": 6}
MODE_COLOR = {
    "gong": "明亮开阔",
    "shang": "有行进感，略带凄清",
    "jue": "偏暗、少用，多作色彩段",
    "zhi": "最明亮，适合豪迈与咏叹",
    "yu": "柔而不伤，国风最常用",
}
SCALE_NAMES = {"wusheng": "五声", "qingyue": "清乐（加 4、7）", "yayue": "雅乐（加 #4、7）",
               "yanyue": "燕乐（加 4、b7）"}

# 音域：相对简谱「1」的半音范围（1 = 0，6' = 21）
RANGE_LO = 0
RANGE_HI = 21

PUNCT = set("，。、；：！？…—·「」『』（）()《》〈〉“”‘’,.;:!?\"' \t")

DEFAULT_DEMO_LYR = """# 内置 demo：把这段词变成五声简谱骨架（D 羽调式）
[主歌A]
灯:1 花:1 落:4 在:4 | 窗:1 前:2
旧:4 年:2 的:0 雨:3 声:1
你:3 留:2 下:4 的:0 针:1 线:4
还:2 在:4 枕:3 边:1

[副歌]
你:3 若:4 回:2 头:2 旧:4 门:2
灯:1 还:2 亮:4 着:0 等:3 团:2 圆:2
把:3 旧:4 信:4 折:2 成:2 小:3 船:2
放:4 进:1 雨:3 里:3 漂:1 远:3
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


def parse_meter(text: str) -> tuple[int, int, float]:
    s = (text or "4/4").strip().replace(" ", "")
    m = re.match(r"^(\d+)/(\d+)$", s)
    if not m:
        return 4, 4, 4.0
    num, den = int(m.group(1)), int(m.group(2))
    if num <= 0 or den <= 0:
        return 4, 4, 4.0
    return num, den, num * 4.0 / den


def parse_int(text, default: int, lo: int, hi: int) -> int:
    try:
        v = int(float(str(text).strip()))
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def fmt_dur(d: float) -> str:
    if abs(d - round(d)) < 1e-9:
        return str(int(round(d)))
    return f"{d:.2f}".rstrip("0").rstrip(".")


# ================================================================ .lyr 解析


def parse_lyr(text: str) -> tuple[list[dict], str, int]:
    """→ ([{name, lines:[{chars:[{ch,tone}], text}]}], 情绪注释, 带声调标注的字数)"""
    sections: list[dict] = []
    cur = {"name": "未命名段", "lines": []}
    mood = ""
    annotated_total = 0
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith("#"):
            if ("情绪" in s or "mood" in s.lower()) and not mood:
                mood = s.lstrip("#").strip()
            continue
        if s.startswith("//"):
            continue
        if s.startswith("[") and s.endswith("]"):
            cur = {"name": s[1:-1].strip() or "未命名段", "lines": []}
            sections.append(cur)
            continue
        if not sections:
            sections.append(cur)
        norm = s.replace("|", " | ")
        chars: list[dict] = []
        annotated = 0
        for tok in norm.split():
            if tok == "|":
                continue
            body, _, tone_str = tok.partition(":")
            tones = [int(x) for x in tone_str if x.isdigit()]
            for i, ch in enumerate(body):
                if ch in PUNCT or not is_cjk(ch):
                    continue
                if len(tones) == len(body) and len(body) > 1:
                    tone = tones[i]
                elif len(tones) == 1:
                    tone = tones[0]
                else:
                    tone = 0
                if tones:
                    annotated += 1
                chars.append({"ch": ch, "tone": tone if tone in (0, 1, 2, 3, 4) else 0})
        if chars:
            annotated_total += annotated
            cur["lines"].append({"chars": chars, "text": "".join(c["ch"] for c in chars),
                                 "annotated": annotated})
    return [sec for sec in sections if sec["lines"]], mood, annotated_total


# ================================================================ 音高模型（五声 + 八度回折）


def penta_to_label(p: int) -> str:
    """五声序号 p ∈ ℤ → 简谱标签（p=0 → 1，p=5 → 1'）。"""
    octave = p // 5
    deg = PENTA[p % 5]
    return f"{deg}" + ("'" * octave if octave > 0 else "," * (-octave))


def penta_semitone(p: int) -> int:
    return DEGREE_SEMITONES[PENTA[p % 5]] + 12 * (p // 5)


def penta_of_semitone(semi: int) -> int:
    """最近的五声序号（±1 半音容差外也能找最近）。"""
    return min(range(-3, 12), key=lambda q: (abs(penta_semitone(q) - semi), q))


def clamp_penta(p: int) -> int:
    """贴边：把五声序号收到音域内（不回绕）。"""
    for _ in range(8):
        if penta_semitone(p) < RANGE_LO:
            p += 1
        elif penta_semitone(p) > RANGE_HI:
            p -= 1
        else:
            break
    return p


def semitone_to_label(semi: int) -> str:
    """半音（相对简谱 1）→ 简谱标签，允许 4/7 与临时记号（--allow-bianyin 用）。"""
    best = None
    for octave in (-1, 0, 1, 2):
        for deg, base in DEGREE_SEMITONES.items():
            diff = semi - (base + 12 * octave)
            if abs(diff) > 1:
                continue
            cand = (abs(diff), deg, octave, diff)
            if best is None or cand < best:
                best = cand
    if best is None:
        return "1"
    _ad, deg, octave, diff = best
    pre = "#" if diff == 1 else ("b" if diff == -1 else "")
    marks = ("'" * octave) if octave > 0 else ("," * (-octave))
    return f"{pre}{deg}{marks}"


def nearest_degree_semitone(degree: int, target: int) -> int:
    base = DEGREE_SEMITONES[degree]
    return min((base + 12 * k for k in (-1, 0, 1, 2)), key=lambda v: abs(v - target))


class MelodyMaker:
    """依字行腔：默认纯五声；allow_bianyin 时按半音移动（可能经过 4/7）。

    越界处理：先按「八度回折」±12 半音（±5 个五声级）把目标拉回音域，
    再贴边；任何情况下都不出五声（除非 allow_bianyin）。
    """

    def __init__(self, mode: str, cadence: int, allow_bianyin: bool) -> None:
        self.mode = mode
        self.cadence = cadence
        self.allow_bianyin = allow_bianyin
        self.p = 4                     # 起点：简谱 6（中高音区，上下都留得开）
        self.semi = penta_semitone(self.p)
        self.flat_run = 0              # 连续阴平计数
        self.last_dir = 0              # 上一个字的走向：+1 上 / -1 下 / 0 平

    # ---- 状态
    def _label(self) -> str:
        if self.allow_bianyin:
            return semitone_to_label(self.semi)
        return penta_to_label(self.p)

    def _set_penta(self, p: int) -> None:
        self.p = clamp_penta(p)
        self.semi = penta_semitone(self.p)

    def _set_semi(self, semi: int) -> None:
        self.semi = max(RANGE_LO, min(RANGE_HI, semi))
        if not self.allow_bianyin:
            self._set_penta(penta_of_semitone(self.semi))

    def _fold(self, semi: int) -> int:
        """越界八度回折（±12 半音），再贴边。"""
        for _ in range(3):
            if semi < RANGE_LO:
                semi += 12
            elif semi > RANGE_HI:
                semi -= 12
            else:
                break
        return max(RANGE_LO, min(RANGE_HI, semi))

    # ---- 单字
    def char_notes(self, tone: int, dur: float, is_line_end: bool) -> list[tuple[str, float]]:
        if is_line_end:
            return self._cadence_notes(dur, tone)
        if tone == 2:          # 阳平：上行二度
            self.flat_run = 0
            self.last_dir = 1
            if self.allow_bianyin:
                self._set_semi(self._fold(self.semi + 2))
            else:
                self._move_penta(2)
        elif tone == 3:        # 上声：先 −2 后 +2（两音，总时值不变）
            self.flat_run = 0
            self.last_dir = -1
            if self.allow_bianyin:
                low = self._fold(self.semi - 2)
                high = self._fold(low + 2)
                low_label = semitone_to_label(low)
                high_label = semitone_to_label(high)
                self._set_semi(high)
                return [(low_label, dur * 0.6), (high_label, dur * 0.4)]
            low = clamp_penta(self.p - 2)
            high = clamp_penta(low + 2)
            self._set_penta(high)
            return [(penta_to_label(low), dur * 0.6), (penta_to_label(high), dur * 0.4)]
        elif tone == 4:        # 去声：下行二至三度（上行之后落得更狠）
            self.flat_run = 0
            steps = 3 if self.last_dir > 0 else 2
            self.last_dir = -1
            if self.allow_bianyin:
                self._set_semi(self._fold(self.semi - steps))
            else:
                self._move_penta(-steps)
        elif tone == 1:        # 阴平：同音或 +1 级
            if self.flat_run >= 2:
                self.flat_run = 0
                self.last_dir = 1
                if self.allow_bianyin:
                    self._set_semi(self._fold(self.semi + 2))
                else:
                    self._move_penta(1)
            else:
                self.flat_run += 1
        # tone == 0：轻声/未知，保持同音
        return [(self._label(), dur)]

    def _move_penta(self, steps: int) -> None:
        target = self.p + steps
        semi = penta_semitone(target)
        if semi < RANGE_LO or semi > RANGE_HI:
            target = penta_of_semitone(self._fold(semi))
        self._set_penta(target)

    # ---- 句尾：落到 cadence（最后一个字拆「经过音 + 落音」，顺手避倒字）
    def _cadence_notes(self, dur: float, tone: int) -> list[tuple[str, float]]:
        target = nearest_degree_semitone(self.cadence, self.semi)
        if self.cadence not in PENTA and not self.allow_bianyin:
            # 偏音不能落句尾：退回调式主音
            target = nearest_degree_semitone(MODE_TONIC[self.mode], self.semi)
        target = self._fold(target)
        self.flat_run = 0
        self.last_dir = 0

        def land_label():
            if self.allow_bianyin:
                self._set_semi(target)
                return semitone_to_label(target)
            self._set_penta(penta_of_semitone(target))
            return penta_to_label(self.p)

        if tone == 0:
            return [(land_label(), dur)]
        if self.allow_bianyin:
            approach = target - 2 if tone in (1, 2, 3) else target + 2
            approach = self._fold(approach)
            if approach == target:
                return [(land_label(), dur)]
            return [(semitone_to_label(approach), dur * 0.4), (land_label(), dur * 0.6)]
        # 纯五声：阴平/阳平/上声从下方级进上去（落音方向=上行），去声从上方级进下来
        base_p = penta_of_semitone(target)
        step = -2 if tone in (1, 2, 3) else 2
        approach_p = clamp_penta(base_p + step)
        if approach_p == base_p:
            return [(land_label(), dur)]
        return [(penta_to_label(approach_p), dur * 0.4), (land_label(), dur * 0.6)]

    def beat_value(self, dur: float) -> str:
        return fmt_dur(dur)


# ================================================================ 排版（小节 / marks）


def build_bars(groups: list[tuple[list[str], float]], bar_beats: float) -> list[list[str]]:
    """把「按字分组」的音符 token 排成整小节（不足补休止）。"""
    bars: list[list[str]] = []
    cur: list[str] = []
    acc = 0.0
    for tokens, beats in groups:
        if acc > 1e-9 and acc + beats > bar_beats + 1e-9:
            pad = bar_beats - acc
            if pad > 1e-9:
                cur.append(f"0:{fmt_dur(pad)}")
            bars.append(cur)
            cur, acc = [], 0.0
        cur.extend(tokens)
        acc += beats
        if acc >= bar_beats - 1e-9:
            bars.append(cur)
            cur, acc = [], 0.0
    if cur:
        pad = bar_beats - acc
        if pad > 1e-9:
            cur.append(f"0:{fmt_dur(pad)}")
        bars.append(cur)
    return bars


def build_jp(sections: list[dict], title: str, key: str, mode: str, scale: str,
             meter: str, tempo: int, cadence: int, chords: str,
             allow_bianyin: bool, instrument: str, mood: str) -> tuple[str, dict]:
    num, den, bar_beats = parse_meter(meter)
    maker = MelodyMaker(mode, cadence, allow_bianyin)

    marks: list[tuple[str, int]] = []
    bars: list[list[str]] = []
    for sec in sections:
        marks.append((sec["name"], len(bars) + 1))
        for ln in sec["lines"]:
            groups: list[tuple[list[str], float]] = []
            chars = ln["chars"]
            for i, c in enumerate(chars):
                is_end = (i == len(chars) - 1)
                notes = maker.char_notes(c["tone"], 1.0, is_end)
                tokens = [f"{label}:{fmt_dur(d)}" for label, d in notes]
                groups.append((tokens, sum(d for _, d in notes)))
            bars.extend(build_bars(groups, bar_beats))

    L: list[str] = []
    L.append(f"# 由 lyric2jianpu.py v{VERSION} 生成（词 → 五声简谱骨架）")
    L.append(f"# {MODE_NAMES[mode]}调式 · {SCALE_NAMES.get(scale, scale)} · {meter} · {tempo} BPM"
             " · 句尾落 " + str(cadence) + ("（允许 4/7 经过音）" if allow_bianyin else "（纯五声）"))
    L.append(f"@title {title}")
    L.append(f"@key {key}")
    L.append(f"@mode {mode}")
    L.append(f"@scale {scale}")
    L.append(f"@meter {meter}")
    L.append(f"@tempo {tempo}")
    L.append(f"@instrument {instrument}")
    L.append("@style shuqing")
    if mood:
        L.append(f"@mood {mood}")
    L.append("")
    L.append("@marks")
    for name, start in marks:
        L.append(f"{start}={name}")
    L.append("")
    L.append("@melody")
    for i in range(0, len(bars), 4):
        L.append(" ".join(" ".join(bar) + " |" for bar in bars[i:i + 4]))
    L.append("")
    if chords.strip():
        L.append("@chords")
        L.append(chords.strip())
        L.append("")
    L.append("@perc")
    L.append("style=锣鼓-中板")
    L.append("")
    stats = {
        "bars": len(bars),
        "lines": sum(len(s["lines"]) for s in sections),
        "chars": sum(len(ln["chars"]) for s in sections for ln in s["lines"]),
        "sections": len(sections),
        "bar_beats": bar_beats,
    }
    return "\n".join(L), stats


# ================================================================ CLI


def _demo_out_dir() -> Path:
    d = Path(tempfile.gettempdir()) / "guofeng-lyric-out"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        d = SCRIPT_DIR
    return d


def resolve_out(out_arg: str | None, input_path: Path | None) -> Path:
    if out_arg:
        p = Path(out_arg).expanduser()
        if p.suffix.lower() == ".jp":
            return p
        if p.is_dir():
            return p / "词谱曲骨架.jp"
        return Path(str(p) + ".jp")
    if input_path is not None:
        return input_path.with_name(input_path.stem + ".jp")
    return _demo_out_dir() / "词谱曲骨架-demo.jp"


def main(argv: list[str] | None = None) -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(
        prog="lyric2jianpu.py",
        description="歌词 .lyr → 五声简谱骨架 .jp（依字行腔；可直接喂给作曲技能 jianpu2midi.py）。纯标准库。",
        epilog=("示例：\n"
                "  python lyric2jianpu.py                                 # demo → <临时目录>/guofeng-lyric-out/\n"
                "  python lyric2jianpu.py --input 山月不知.lyr            # → 同目录/山月不知.jp\n"
                "  python lyric2jianpu.py --input 词.lyr --key D --mode yu --cadence 6 --out 山月不知.jp\n"
                "音高规则：阴平同音/+1 级，阳平 +2 度，上声先 −2 后 +2，去声 −2~−3 度，句尾落 cadence。"),
    )
    parser.add_argument("--input", help="输入歌词（.lyr）")
    parser.add_argument("--out", help="输出 .jp 路径（默认见上）")
    parser.add_argument("--demo", action="store_true", help="用内置 demo 词生成骨架")
    parser.add_argument("--key", default="D", help="调（默认 D）")
    parser.add_argument("--mode", default="yu",
                        help="调式：gong/shang/jue/zhi/yu 或 宫/商/角/徵/羽（默认 yu）")
    parser.add_argument("--scale", default="qingyue",
                        help="音阶：wusheng/qingyue/yayue/yanyue（默认 qingyue）")
    parser.add_argument("--cadence", default=None,
                        help="句尾落音级数 1–7（默认取调式主音：宫1/商2/角3/徵5/羽6）")
    parser.add_argument("--tempo", default="72", help="BPM（默认 72）")
    parser.add_argument("--meter", default="4/4", help="拍号（默认 4/4）")
    parser.add_argument("--chords", default="", help='和弦串，如 "6m | 4add9 | 5sus4 | 6m |"')
    parser.add_argument("--allow-bianyin", action="store_true", help="允许 4/7 作经过音")
    parser.add_argument("--instrument", default="xiao",
                        help="主奏乐器 id（默认 xiao；可选 di/guzheng/erhu/pipa…）")
    args = parser.parse_args(argv)

    input_path = Path(args.input).expanduser() if args.input else None
    out_path = resolve_out(args.out, input_path)

    try:
        mode_raw = (args.mode or "yu").strip()
        mode = MODE_ALIAS.get(mode_raw.lower()) or MODE_ALIAS.get(mode_raw)
        if not mode:
            print(f"❌ 不认识的调式：{args.mode}", file=sys.stderr)
            print("下一步：--mode 用 gong/shang/jue/zhi/yu 或 宫/商/角/徵/羽。", file=sys.stderr)
            return 2
        scale = (args.scale or "qingyue").strip().lower()
        if scale not in SCALE_NAMES:
            print(f"❌ 不认识的音阶：{args.scale}", file=sys.stderr)
            print("下一步：--scale 用 wusheng/qingyue/yayue/yanyue。", file=sys.stderr)
            return 2
        meter_num, meter_den, bar_beats = parse_meter(args.meter)
        if bar_beats <= 0:
            print(f"❌ 拍号不合法：{args.meter}", file=sys.stderr)
            print('下一步：--meter 写成 "4/4" 这种形式。', file=sys.stderr)
            return 2
        tempo = parse_int(args.tempo, 72, 20, 300)
        cadence = parse_int(args.cadence, MODE_TONIC[mode], 1, 7)
        if cadence not in (1, 2, 3, 4, 5, 6, 7):
            cadence = MODE_TONIC[mode]

        if input_path is not None:
            if not input_path.exists():
                print(f"❌ 找不到输入文件：{input_path}", file=sys.stderr)
                print("下一步：确认路径；或跑 `python lyric2jianpu.py --demo` 看 .lyr 格式。", file=sys.stderr)
                return 2
            text = read_text_file(input_path)
            title = input_path.stem
        else:
            text = DEFAULT_DEMO_LYR
            title = "山月不知"

        sections, mood, annotated = parse_lyr(text)
        if not sections:
            print("❌ 没有解析到歌词：请用 `字:调` 写法（如 `江:1 南:2 雨:3`），段名用 `[主歌A]`。", file=sys.stderr)
            return 2
        if annotated == 0:
            print("❌ 全篇没有 `字:调` 声调标注，无法依字行腔。", file=sys.stderr)
            print("下一步：把每句写成 `江:1 南:2 雨:3`（1 阴平 2 阳平 3 上声 4 去声 0 未知），"
                  "段名用 `[主歌A]`；也可以先跑 `lyric_blueprint.py` 复制它生成的 .lyr 骨架。", file=sys.stderr)
            return 2

        jp, stats = build_jp(sections, title, (args.key or "D").strip(), mode, scale,
                             f"{meter_num}/{meter_den}", tempo, cadence,
                             args.chords, args.allow_bianyin,
                             (args.instrument or "xiao").strip(), mood)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(jp, encoding="utf-8")

        print("")
        print("=" * 62)
        print(f"🎵 简谱骨架已生成：{title}")
        print(f"   调式：{args.key} {MODE_NAMES[mode]}调式（{MODE_COLOR[mode]}）"
              f" · {SCALE_NAMES[scale]} · 句尾落 {cadence}")
        print(f"   结构：{stats['sections']} 段 / {stats['lines']} 句 / {stats['chars']} 字 / "
              f"{stats['bars']} 小节（{meter_num}/{meter_den}，每小节 {bar_beats:g} 拍）")
        print(f"   乐器：{args.instrument} ｜ 速度：{tempo} BPM")
        if args.allow_bianyin:
            print("   ℹ️  已允许 4/7 作经过音（要纯五声请去掉 --allow-bianyin）")
        print(f"   输出：{out_path}")
        print("=" * 62)
        print("下一步：")
        print(f"  1. 导出 MIDI：`python ../guofeng-music/package/scripts/jianpu2midi.py --input {out_path.name}`")
        print("  2. 想改旋律：直接改 .jp 的 @melody（每小节拍数合计 = 拍号），再重跑 jianpu2midi.py；")
        print("  3. 词要返工：改 .lyr 后重跑本脚本覆盖 .jp。")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # 任何输入都不抛 traceback
        print(f"❌ 生成简谱骨架失败：{exc}", file=sys.stderr)
        print("下一步：① 先用 --demo 确认脚本正常；② 检查 .lyr 每行是否为 `字:调`；"
              "③ 生僻字/表情符号先删掉；④ 把这段报错发给开发者。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
