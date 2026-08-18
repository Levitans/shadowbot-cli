# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

`shadowbot-cli` 是影刀 RPA（ShadowBot）开放平台的命令行工具，**面向 AI Agent**：业务命令统一以 JSON 信封输出到 stdout，stderr 保持为空。技术栈：Python 3.12 / uv / Typer / httpx。

## 常用命令

```bash
uv sync                          # 安装依赖（含 dev 测试组）
uv run pytest                    # 全部测试
uv run pytest tests/test_cli.py::test_login_success -v   # 单个用例
uv run shadowbot-cli --help      # 开发时运行 CLI（等价：uv run python -m shadowbot_cli）
uv build                         # 构建 wheel/sdist，发布前检查
uv tool install --editable . --force   # 装成全局命令；入口点/结构变了要 --force 重装
```

## 架构：三层单向依赖 `cli → api → http`

- `cli/` — Typer 命令 + JSON 输出契约
  - `app.py`：命令定义；`@json_command` 装饰器把命令返回的 dict 自动包装成成功信封、业务异常转错误信封
  - `output.py`：JSON 输出契约（emit_ok / emit_fail / error_code / set_pretty，import 时强制 UTF-8）
  - `skills.py`：`skill` 命令的文档查找（沿命令树解析路径）
- `api/` — 影刀 OpenAPI 业务层，**一个方法对应一个接口**
  - `client.py`：`ApiClient` + `build_api_client()`（组装依赖：跨进程限流器 → HttpClient）
  - `rate_limits.py`：各接口 QPS 登记表（影刀文档真实值，勿改）
- `http/` — 通用 HTTP，不含影刀语义
  - `client.py`：`HttpClient`（httpx 封装，重试、可选 `RateLimit` 限流）
  - `rate_limiter.py`：跨进程令牌桶（状态文件 + fcntl 文件锁）

`config.py`（XDG 配置/状态目录）、`errors.py`（HttpError/ApiError/AuthError 层级）为共享基础设施。`skill/` 存命令 Markdown 文档，目录结构镜像命令树（`skill app run` → `skill/app/run.md`）。

## 必须遵守的约定

- **JSON 输出**：业务命令 stdout 只输出一个 JSON 信封，stderr 必须为空。信封：成功 `{"success":true,"data":{...},"error":null}`；失败 `{"success":false,"data":null,"error":{"code","message"}}`。只有 `--help` 保持 Click 原生文本。**新增业务命令必须套 `@json_command`**。
- **`error.code`** 稳定取值：`auth_error` / `http_error` / `api_error` / `usage_error` / `error`。
- **退出码**：0 成功 / 1 业务·API 错误 / 2 参数用法错误。
- **禁止 Click 交互式 prompt**：提示文本会污染 stdout JSON（agent 也无法应答）。输入一律来自参数 / 环境变量 / `.env`。
- **安全**：`login` 等输出不得包含令牌/密钥本体。
- **中文**：命令 help、输出消息、文档均为中文。
- **注释规范**：文件内分区/分组的标题注释统一用 `# --- 标题 ---` 格式（左右各三个短横线），不要用长短不一的 `# ---- ... ----`、`# ------ ...` 分隔线。
- **文档与帮助文案**：`skill/` 的 Markdown 和 `--help` 说明只写"如何使用"（参数、示例、输出格式），**不解释实现原理**，保持简洁。

## 关键实现细节（踩过的坑）

- **typer 0.27 内嵌了 Click**（`typer._click`），项目里没有独立 click 包，不能 `import click`；`result_callback` 已移除，所以用 `@json_command` 装饰器。`-h, --help` 的文案写死在 `typer._click.decorators.help_option`，app.py 通过 monkeypatch 中文化（有 try/except 兜底，typer 升级后可能失效）。
- **`cli/__init__.py` 必须保持为空**：不要重导出 `app`/`run`，否则 `shadowbot_cli.cli.app` 解析成 Typer 实例而非子模块，monkeypatch 测试会挂。
- **跨进程限流器**：`RateLimiter(state_dir, _time=..., _sleep=...)` 时钟/睡眠可注入，测试用可控假时钟（`tests/test_rate_limiter.py`）。状态文件在 `$XDG_STATE_HOME/shadowbot-cli/rate-limiter/`。
- **QPS**：新接口在 `api/rate_limits.py` 登记；`rate_limit_for(path)` 未登记返回 None（不限流）。`capacity` 取 = QPS（允许一秒配额内的突发）。
- **`.env`**：入口用 `load_dotenv(find_dotenv(usecwd=True))`——必须 `usecwd=True`，否则从 site-packages 向上找，找不到项目里的 `.env`。
- **测试**：Typer 的 `CliRunner()` 不接受 `mix_stderr`，但 `result.stdout` / `result.stderr` 是分开捕获的——用 `result.stdout` 断言纯 JSON，用 `assert result.stderr == ""` 锁死"stderr 为空"契约。

## 新增一个接口的标准流程

1. `api/rate_limits.py` 登记该接口 QPS
2. `api/client.py` 的 `ApiClient` 加方法，内部 `self._http.get(path, ..., rate_limit=rate_limit_for(path))`
3. `cli/app.py` 加命令，套 `@app.command()` + `@json_command`，命令体 `return {...}`
4. 可选：`skill/<路径>.md` 写使用文档（只讲用法，不讲实现原理；不放也能用，回退到内置帮助）
5. 补测试（各层一个：api 解析 / cli JSON 输出 / 必要时 http）
