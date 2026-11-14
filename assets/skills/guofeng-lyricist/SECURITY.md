# 安全说明（SECURITY）

## 一句话

四个脚本只做「文本进、文本出」，不执行外部命令、不联网、不写系统目录。

## 脚本行为边界

| 脚本 | 读什么 | 写什么 | 是否联网 | 是否调用外部程序 |
|---|---|---|---|---|
| `lyric_blueprint.py` | 可选的需求 JSON | 蓝图 Markdown / JSON | 否 | 否 |
| `lint_guofeng_lyric.py` | `.lyr`、可选 `.jp`、可选 `.slots.json` | 校验报告 Markdown | 否 | 否 |
| `jianpu2lyricslots.py` | `.jp` 曲谱 | `.slots.json` + `.slots.md` | 否 | 否 |
| `lyric2jianpu.py` | `.lyr` 词稿 | `.jp` 简谱骨架 | 否 | 否 |

- 纯 Python 标准库实现（`argparse`、`json`、`pathlib`、`re`、`sys`、`unicodedata`），**不依赖任何第三方包**。
- 不做 `eval` / `exec` / `subprocess` / `os.system` 调用。
- 只写用户通过 `--out` / `--report` 指定、或位于当前工作目录的文件；不写系统目录、注册表、开机项。
- 输入异常（缺字段、格式错误、句长不符、韵辙不符）时给出中文提示并退出，不崩溃、不覆盖既有文件。

## 用户侧建议

1. 从购买渠道获取技能包，不接收他人二次分发的修改版脚本。
2. 运行前确认 `--out` 指向自己期望的目录。
3. 脚本全部为纯文本 Python，可直接阅读审计。

## 报告问题

发现安全问题请通过购买渠道客服入口反馈，注明脚本名、命令与报错信息（不要附带个人隐私数据）。

© 2026 奶龙1号
