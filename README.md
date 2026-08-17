# shadowbot-cli

影刀 RPA 开放平台的命令行工具。用 [Typer](https://typer.tiangolo.com/) 实现，`--help` 输出为 Click 风格（无边框、无彩色）。

## 安装

```bash
pip install shadowbot-cli
```

开发模式：

```bash
uv sync
uv run shadowbot-cli --help
```

## 使用

登录（获取并保存访问令牌，**非交互式**，凭据来自参数 / 环境变量 / .env）：

```bash
shadowbot-cli login --access-key-id YOUR_KEY_ID --access-key-secret YOUR_KEY_SECRET
# 或设置环境变量 SHADOWBOT_ACCESS_KEY_ID / SHADOWBOT_ACCESS_KEY_SECRET 后直接运行
shadowbot-cli login
```

### 用 .env 管理凭据

支持读取当前目录（或其父目录）下的 `.env` 文件，示例见 `.env.example`：

```bash
cp .env.example .env   # 编辑 .env 填入真实凭据
shadowbot-cli login        # 自动读取，无需再传参数
```

取值优先级：真实 shell 环境变量 > `.env` 文件。`.env` 已被 git 忽略，不会误提交。

### 查看命令文档（skill）

`skill` 按命令路径查看使用文档，命令树驱动：

```bash
shadowbot-cli skill login          # 查看 login 的文档
shadowbot-cli skill app            # 查看 app 组的文档
shadowbot-cli skill app run        # 查看 app run 子命令的文档
```

- 有对应的 Markdown 时输出 Markdown；**没有时自动回退到该命令的内置 `--help`**，
  所以新命令天然支持 skill 查询，无需额外登记。
- 输出为 JSON 信封，`data` 含 `command` / `source`（`markdown` 或 `help`）/ `content`。
- 文档放在 `src/shadowbot_cli/skill/`，目录结构镜像命令树（见下）。

## 输出格式（面向 AI Agent）

所有命令统一以 **JSON 信封**输出到 stdout：

```json
{"success": true,  "data": {...},  "error": null}                          // 成功
{"success": false, "data": null, "error": {"code": "...", "message": "..."}} // 失败
```

- **stdout 只承载 JSON**，业务命令的 stderr 保持为空——结果与错误都解释在 JSON 里
- `data` / `error` 始终带键（成功时 `error` 为 null），agent 无需判空
- 退出码：`0` 成功 / `1` 业务·API 错误 / `2` 参数用法错误
- `error.code` 稳定取值：`auth_error` / `http_error` / `api_error` / `usage_error` / `error`
- 人类体验：加 `--pretty` 后，在 TTY 终端里用 rich 美化输出（管道下仍是紧凑 JSON）
- 仅两个例外会写 stderr / 保持文本：`--help`（Click 自带协议）与 Click 的参数用法错误（无法覆盖）

## 项目结构

三层分层，单向依赖：`cli → api → http`

```
src/shadowbot_cli/
├── cli/        # Typer 命令：参数/交互/输出格式化/错误→退出码
│   ├── app.py         # 命令定义
│   └── skills.py      # skill 命令的文档查找与回退
├── api/        # OpenAPI 接口：一个方法一个接口、响应解析、认证状态
│   ├── client.py       # ApiClient + 依赖组装（build_api_client）
│   ├── models.py       # Token 等数据模型
│   └── rate_limits.py  # 各接口 QPS 登记表（接入新接口时在此登记）
├── http/       # 底层 HTTP：httpx 封装、重试、跨进程限流器
│   ├── client.py       # HttpClient
│   └── rate_limiter.py # 跨进程令牌桶（状态文件 + fcntl 文件锁）
├── skill/      # 命令使用文档（Markdown），目录结构镜像命令树
│   ├── login.md        # → shadowbot-cli skill login
│   └── app/run.md      # 示例 → shadowbot-cli skill app run
├── config.py   # XDG 配置/状态目录
└── errors.py   # 统一异常：HttpError / ApiError / AuthError
```

- **限流**：每个接口的 QPS 在 `api/rate_limits.py` 登记，api 层调用时传给 http 层；
  限流器状态存在 `$XDG_STATE_HOME/shadowbot-cli/rate-limiter/`，跨进程共享。
- **新增接口**：在 `api/rate_limits.py` 登记 QPS → 在 `ApiClient` 加一个方法 → 在 `cli` 加命令。
- **新增文档**：在 `skill/` 放对应路径的 Markdown（如 `app/run.md`）；不放也能用，`skill` 会回退到内置帮助。

- **限流**：每个接口的 QPS 在 `api/rate_limits.py` 登记，api 层调用时传给 http 层；
  限流器状态存在 `$XDG_STATE_HOME/shadowbot-cli/rate-limiter/`，跨进程共享。
- **新增接口**：在 `api/rate_limits.py` 登记 QPS → 在 `ApiClient` 加一个方法 → 在 `cli` 加命令。


凭据与令牌按 [XDG 规范](https://specifications.freedesktop.org/basedir-spec/latest/) 保存在
`$XDG_CONFIG_HOME/shadowbot-cli/config.json`（未设置时默认为 `~/.config/shadowbot-cli/config.json`），
文件权限为 0600。
