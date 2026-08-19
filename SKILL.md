---
name: shadowbot-cli
description: 在使用 `shadowbot-cli`（影刀 RPA 开放平台 CLI）时加载本 skill——当用户要调用该 CLI 的任何命令、查询命令文档、解析其 JSON 输出，或排查调用报错时都应触发。stdout 永远是单一 JSON 信封供 AI Agent 解析，常规 CLI 惯例不适用。
---

# shadowbot-cli

影刀 RPA 开放平台的命令行工具，所有业务命令以 JSON 信封输出到 stdout，面向 AI Agent。

## 调用命令

通过 `shadowbot-cli <命令路径> [选项]` 调用，例如：

```bash
shadowbot-cli login --access-key-id YOUR_KEY_ID --access-key-secret YOUR_KEY_SECRET
shadowbot-cli app list
shadowbot-cli app run --app-id <id> --account-name <name>
shadowbot-cli robot list
shadowbot-cli job get --job-uuid <uuid>
```

敏感参数支持从环境变量读取：`SHADOWBOT_ACCESS_KEY_ID` / `SHADOWBOT_ACCESS_KEY_SECRET`，也可放在当前目录的 `.env` 文件里（参考项目根目录的 `.env.example`）。

## 查看命令文档

使用 `skill` 子命令按命令路径查询文档：

```bash
shadowbot-cli skill                # 列出用法
shadowbot-cli skill login          # 查询 login 的文档
shadowbot-cli skill app            # 查询 app 命令组
shadowbot-cli skill app run        # 查询子命令
```

如果有对应的 `skill/<路径>.md` Markdown 就输出它；**没有就自动回退到该命令的内置 `--help`**，所以每个新命令天然支持 skill 查询。

## 解析输出

所有业务命令 stdout 始终是这一个 JSON 结构：

```json
{"success": true,  "data": {...},  "error": null}                           // 成功
{"success": false, "data": null, "error": {"code": "...", "message": "..."}} // 失败
```

- 退出码：`0` 成功 / `1` 业务·API 错误 / `2` 参数用法错误
- `error.code` 稳定取值：`auth_error` / `http_error` / `api_error` / `usage_error` / `error`
- 加 `--pretty` 在 TTY 终端里用 rich 美化（管道下仍是紧凑 JSON，不影响机器解析）
- 业务命令的 stderr 始终为空；只有 `--help` 和 Click 自带的参数用法错误会写 stderr
