# dsh-guofeng-studio

**A Chinese-style songwriting studio for DeepSeek Harness.** One install gives the agent three
skills: a Chinese-style composer, a Chinese-style lyricist, and an orchestration skill that connects
the two halves through a shared file contract.

Everything runs locally: the bundled Python scripts use only the standard library — no network, no
API keys, no `pip install`.

[中文](README.zh.md)

## What it does

| You say | It delivers |
| --- | --- |
| "Write me a Chinese-style song about rain in Jiangnan" | A composition blueprint (mode/scale/structure/arrangement/chord candidates) → a singable numbered-notation melody → pentatonic chords → arrangement table → three lint gates → multi-track MIDI |
| "Put lyrics on this melody" | Reads the `.jp` numbered notation and emits lyric slots (syllables per line, rhyme positions, cadence notes, tone hints) → fills `.lyr` → 14 lyric lint rules |
| "Turn this lyric into a song" | Lyric lint → `lyric2jianpu` builds the melody skeleton → back to the composer skill for harmony and arrangement → MIDI |
| "Give me both words and music" | The orchestration skill triages, runs the loop, and passes both lint gates before delivery |

Skills:

| Skill | Role | Key outputs |
| --- | --- | --- |
| `guofeng-song-studio` | Suite entry: triage, file contract, final acceptance | Delivery checklist |
| `guofeng-music-composer` | Composition workbench | Blueprint, `.jp` melody, chord degree chart, arrangement table, lint report, `.mid` |
| `guofeng-lyricist` | Lyric workbench | `.lyr` draft, lyric blueprint, lint report, `.slots.json` slots |

## Install

```bash
dsh plugin --profile desktop add dsh-guofeng-studio
```

Refresh the page (or restart DSH) and the three skills show up in the skill catalog. The plugin market
installs it the same way.

## Environment

| Component | Version | Notes |
| --- | --- | --- |
| DeepSeek Harness | `>= 0.2.2-rc.1 < 0.3.0-0` | Uses the `ctx.skills` registry |
| Python | 3.8+ | Standard library only |

## How it is built

- **Skill-bundle plugin**: no UI, no `/api` routes; it registers one bundled skill provider and ships
  its content under `assets/skills/`.
- **Never shadows your skills**: candidates use bundled rank (600), so a same-named skill in a
  project directory or `~/.dsh/skills` wins.
- **Zero runtime dependencies**: node built-ins only.
- **Frontmatter stays out of context**: only the Markdown body of each `SKILL.md` is shown to the model.

## License

- Plugin code (`lib/`, `cordis.patch.yml`, tests): MIT.
- Bundled skill content (`assets/skills/`): © 奶龙1号, free to use with this plugin; reselling or
  republishing the content alone is not allowed. See `LICENSE` and `NOTICE.md`.
