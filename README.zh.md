# dsh-guofeng-studio

**中国风词曲工作室** —— 一个给 DeepSeek Harness 的技能包插件。装上它，agent 就同时拿到
「中国风音乐创作」「中国风作词」和一条把两半接起来的「词曲总入口」技能。

全部本地运行：脚本是纯 Python 标准库，不联网、不要 API Key、不装依赖。

[English](README.md)

## 装完能干什么

| 你说 | 它做 |
| --- | --- |
| 「写一首中国风，写江南雨」 | 出创作蓝图（调式/音阶/结构/配器/和弦候选）→ 简谱旋律 → 五声化和弦 → 配器结构表 → 三道校验 → 多轨 MIDI |
| 「给我这段曲填词」 | 读 `.jp` 简谱生成填词槽位（每句字数、韵位、落音、声调建议）→ 按槽位填 `.lyr` → 14 条词稿校验 |
| 「这首词帮我成曲」 | 词稿 lint → `lyric2jianpu` 出简谱骨架 → 回作曲技能配和声/配器 → MIDI |
| 「词曲一起给我」 | 总入口技能分诊，按闭环跑完，最后一起过校验、一起交付 |

三个技能：

| 技能 | 作用 | 关键产出 |
| --- | --- | --- |
| `guofeng-song-studio` | 词曲总入口：分诊、文件契约、总验收 | 交付清单逐项验收 |
| `guofeng-music-composer` | 中国风作曲工作台 | 蓝图、`.jp` 简谱、和弦级数表、配器表、校验报告、`.mid` |
| `guofeng-lyricist` | 中国风作词工作台 | `.lyr` 词稿、作词蓝图、校验报告、`.slots.json` 填词槽位 |

## 装

```bash
dsh plugin --profile desktop add dsh-guofeng-studio
```

装完刷新页面（或重启 DSH），三个技能会出现在技能目录里；也可以用插件市场一键安装。

## 用

直接说人话就行，例如：

- 「写一首中国风，题材江南雨，抒情，带箫和古筝」→ 走作曲技能
- 「给这首曲填词」+ 你的 `.jp` 文件 → 走作词技能
- 「词曲都要，先出词」→ 走总入口

技能正文里写清了每一步该跑哪个脚本、交付物长什么样、哪些硬规则不能破。
脚本在插件的 `assets/skills/<技能名>/scripts/` 下，技能会告诉你基础目录。

## 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| DeepSeek Harness | `>= 0.2.2-rc.1 < 0.3.0-0` | 用到 `ctx.skills` 技能注册表 |
| Python | 3.8+ | 只跑标准库，无需 pip 安装 |

## 设计说明

- **技能包型插件**：不注册 UI，不注册 `/api` 路由，只往技能注册表挂一个 bundled provider，
  包内 `assets/skills/` 随包分发。
- **不抢用户的同名技能**：provider 用 bundled 优先级（rank 600），项目目录或 `~/.dsh/skills`
  里的同名技能优先胜出。
- **只用 node 内置模块**：零运行时依赖，宿主升级不会把它带崩。
- **frontmatter 不进上下文**：只把 SKILL.md 的 Markdown 正文交给模型。

## 目录

```
dsh-guofeng-studio/
├── lib/index.js                 宿主半边：注册技能 provider
├── assets/icon.png              512×512 图标
├── assets/skills/
│   ├── guofeng-song-studio/     词曲总入口技能
│   ├── guofeng-music-composer/  作曲技能（references/samples/scripts）
│   └── guofeng-lyricist/        作词技能（references/samples/scripts）
├── cordis.patch.yml             组合补丁层
└── test/smoke.mjs               离线冒烟
```

## 许可

- 插件代码（`lib/`、`cordis.patch.yml`、测试与构建脚本）：MIT。
- 随包分发的技能内容（`assets/skills/`）：© 奶龙1号，随本插件免费使用，不得单独转售或二次上架。
  详见包内 `LICENSE` 与 `NOTICE.md`。

## 边界

不替代 DAW 混音、不假装实录民乐、不产出人声演唱；MIDI 用 GM 音色占位，交付说明里会写清换音源建议。
