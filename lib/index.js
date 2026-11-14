/**
 * dsh-guofeng-studio 宿主半边。
 *
 * 这是一个「技能包」型 DSH 插件：它不注册任何 UI 或路由，只在本机的技能注册表
 * （`ctx.skills`）里挂一个 bundled provider，把三个技能一次性交给 agent：
 *
 *   - guofeng-song-studio      词曲总入口（分诊 + 文件契约 + 总验收）
 *   - guofeng-music-composer   中国风音乐创作（调式/简谱/和弦/配器/校验/MIDI）
 *   - guofeng-lyricist         中国风作词（韵辙/意象/典故/炼字/校验/填词槽位）
 *
 * 技能内容随包分发在 `assets/skills/<name>/`，`resourceBase` 指向该目录，
 * 所以技能正文里的 `scripts/xxx.py`、`references/xxx.md`、`samples/xxx.jp`
 * 都按基础目录解析。脚本是纯 Python 标准库，模型自己用终端执行即可。
 *
 * 设计约束：
 *   - 只用 node 内置模块，不引入任何运行时依赖（宿主升级不会把它带崩）。
 *   - 不覆写用户自己的同名技能：rank 用 600（bundled 档），项目/用户目录里的
 *     同名技能 rank 更小，会优先胜出。
 *   - SKILL.md 的 YAML frontmatter 在正文里去掉，只把 Markdown 正文喂给模型。
 */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

/** Cordis 插件名（必须与包名一致）。 */
export const name = "dsh-guofeng-studio";

/** 依赖技能注册表服务。 */
export const inject = ["skills"];

/** 与 package.json 的 version 保持一致（smoke 测试会校验）。 */
export const VERSION = "1.0.0";

/** provider 名在本机技能注册表里必须唯一。 */
const PROVIDER = "guofeng-studio";

/** bundled 档优先级：用户/项目同名技能会覆盖它。 */
const RANK = 600;

const SKILLS_ROOT = fileURLToPath(new URL("../assets/skills/", import.meta.url));

/** @typedef {{ name: string, dir: string, description: string, whenToUse?: string }} SkillSpec */

/** @type {SkillSpec[]} */
const SKILLS = [
  {
    name: "guofeng-song-studio",
    dir: "guofeng-song-studio",
    description:
      "中国风词曲一体化工作台：先判断该先作词还是先作曲，再用 .jp 简谱 / .lyr 词稿 / .slots.json 填词槽位三种文件把《中国风音乐创作》和《中国风作词》串成闭环，一次交付词、曲、两份校验报告与多轨 MIDI。触发词：词曲、写一首完整的中国风、先词后曲、先曲后词、词曲联动、填词、作一首歌的词和曲。",
    whenToUse:
      "用户要的是一首完整的中国风歌（词 + 曲 + 可开工文件），或只有一半（只有词 / 只有曲）要补另一半时；只要词或只要曲时直接用对应子技能。",
  },
  {
    name: "guofeng-music-composer",
    dir: "guofeng-music-composer",
    description:
      "中国风音乐创作：说清题材与情绪就出可开工方案——调式与音阶决策、可唱的简谱旋律、五声化和弦级数表、配器与结构表、三道自动校验，以及可拖进 DAW 的多轨 MIDI。触发词：中国风、国风、古风、写一首中国风、国风编曲、五声音阶、简谱、戏腔、民乐配器、国潮、MIDI。",
    whenToUse:
      "要写/编一首中国风或国风歌、影视游戏短剧配乐，要旋律、和弦、配器表或 MIDI 文件，或已有旋律要配和声与编配时。",
  },
  {
    name: "guofeng-lyricist",
    dir: "guofeng-lyricist",
    description:
      "中国风作词：给主题就出能唱的完整词稿——定韵辙与句式、配意象与典故、做化用与炼字、排结构与金句，并用押韵/句长/倒字/伪古风/典故/生僻字等规则自动校验；能读曲谱生成填词槽位，也能把词变成可导 MIDI 的简谱骨架。触发词：作词、写词、填词、中国风歌词、国风歌词、古风歌词、押韵、换韵、典故、化用、歌词润色。",
    whenToUse:
      "要写/改中国风歌词，要按已有曲谱填词，或手里有词要配旋律时。",
  },
];

const skillDir = (spec) => path.join(SKILLS_ROOT, spec.dir);
const skillFile = (spec) => path.join(skillDir(spec), "SKILL.md");

/** 去掉 Markdown 文件开头的 YAML frontmatter（只留正文）。 */
export function stripFrontmatter(text) {
  if (!text.startsWith("---")) return text;
  const match = /^---\r?\n[\s\S]*?\r?\n---\r?\n?/.exec(text);
  return match === null ? text : text.slice(match[0].length);
}

function candidateOf(spec) {
  return {
    name: spec.name,
    description: spec.description,
    ...(spec.whenToUse === undefined ? {} : { whenToUse: spec.whenToUse }),
    invocation: { modelInvocable: true, userInvocable: true },
    source: "plugin",
    provider: PROVIDER,
    resourceBase: { kind: "directory", path: skillDir(spec) },
    rank: RANK,
    locator: skillFile(spec),
  };
}

const provider = {
  name: PROVIDER,
  list() {
    return Promise.resolve(SKILLS.map(candidateOf));
  },
  async get(candidate) {
    const spec = SKILLS.find((item) => item.name === candidate.name);
    if (spec === undefined) return undefined;
    const raw = await readFile(skillFile(spec), "utf8");
    return {
      name: spec.name,
      description: spec.description,
      ...(spec.whenToUse === undefined ? {} : { whenToUse: spec.whenToUse }),
      invocation: { modelInvocable: true, userInvocable: true },
      source: "plugin",
      provider: PROVIDER,
      resourceBase: { kind: "directory", path: skillDir(spec) },
      content: stripFrontmatter(raw),
    };
  },
};

/** 注册技能 provider（卸载时由 cordis 自动注销）。 */
export function apply(ctx) {
  ctx.skills.registerProvider(() => provider);
}

/** 测试钩子：技能清单与目录，供离线 smoke 校验。 */
export const __test = { SKILLS, PROVIDER, RANK, SKILLS_ROOT, candidateOf };
