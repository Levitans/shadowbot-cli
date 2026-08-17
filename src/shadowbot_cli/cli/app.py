"""CLI 层：Typer 命令定义。

职责：
  - 参数解析、交互、输出格式化、错误 → 退出码；
  - 只依赖 api 层（build_api_client），不直接调用 http 层 / config 的业务写入；
  - 未来新增命令（task list / task run ...）也放在这里，需要时可拆成 commands/ 包。
"""

from __future__ import annotations

import functools
from typing import Annotated, NoReturn, Optional

import typer
from dotenv import find_dotenv, load_dotenv

from .. import __version__, config
from ..api.client import build_api_client
from ..errors import ShadowBotError
from .output import emit_fail, emit_ok, error_code, set_pretty
from .skills import build_root, command_help, read_doc, resolve

# ------------------------------------------------------------------
# 帮助选项文案中文化
# typer 0.27 起内嵌 Click（typer._click），"-h, --help  Show this message
# and exit." 的文案写死在 typer._click.decorators.help_option 里。这里在
# 启动时替换它，让所有命令（含子命令）的帮助选项都显示中文。
# typer 内部结构变动时静默回退英文，不影响功能。
# ------------------------------------------------------------------
try:
    from typer._click import decorators as _click_decorators

    _original_help_option = _click_decorators.help_option

    def _localized_help_option(param_decls):
        # help_option(param_decls) 返回的是装饰器，需要再应用到命令上
        apply_original = _original_help_option(param_decls)

        def _apply(command):
            command = apply_original(command)
            for param in command.params:
                if param.name == "help":
                    param.help = "显示帮助并退出。"
            return command

        return _apply

    _click_decorators.help_option = _localized_help_option
except Exception:
    pass

app = typer.Typer(
    help="影刀 RPA 开放平台命令行工具。",
    no_args_is_help=True,
    rich_markup_mode=None,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def _version_callback(value: bool) -> None:
    if value:
        emit_ok({"name": "shadowbot-cli", "version": __version__})
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=_version_callback, is_eager=True, help="显示版本并退出。"),
    ] = None,
    pretty: Annotated[bool, typer.Option("--pretty", help="美化 JSON 输出。")] = False,
) -> None:
    """影刀 RPA 开放平台命令行工具。"""
    if pretty:
        set_pretty(True)


# ------------------------------------------------------------------
# JSON 输出：契约在 cli/output.py 统一实现，这里只做命令层的胶水
# 成功：{"success": true,  "data": {...},  "error": null}
# 失败：{"success": false, "data": null, "error": {"code": "...", "message": "..."}}
# 退出码约定：0 成功 / 1 业务·API 错误 / 2 参数用法错误（Click 默认）
# ------------------------------------------------------------------


def _fail_and_exit(code: str, message: str, *, exit_code: int = 1) -> NoReturn:
    """输出 JSON 错误信封到 stdout，然后退出。

    不写 stderr：结果与错误都解释在 JSON 里，业务命令的 stderr 保持为空。
    """
    emit_fail(code, message)
    raise typer.Exit(exit_code)


def json_command(fn):
    """命令装饰器：返回的 dict 自动包装成成功信封；业务异常自动转错误信封。

    使用：@app.command() 之下再套 @json_command，命令内部只需 return 一个 dict。
    不套此装饰器的命令（如 skill）保持人类可读输出。
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
        except ShadowBotError as e:
            _fail_and_exit(error_code(e), str(e))
        if result is not None:
            emit_ok(result)

    return wrapper


@app.command()
@json_command
def login(
    access_key_id: Annotated[
        Optional[str],
        typer.Option(
            "--access-key-id",
            envvar="SHADOWBOT_ACCESS_KEY_ID",
            help="影刀开放平台的应用 Access Key ID。",
        ),
    ] = None,
    access_key_secret: Annotated[
        Optional[str],
        typer.Option(
            "--access-key-secret",
            envvar="SHADOWBOT_ACCESS_KEY_SECRET",
            help="影刀开放平台的应用 Access Key Secret。",
        ),
    ] = None,
) -> dict:
    """登录，获取访问令牌。"""
    if not access_key_id or not access_key_secret:
        _fail_and_exit(
            "usage_error",
            "缺少 --access-key-id / --access-key-secret（或对应环境变量）",
            exit_code=2,
        )
    token = build_api_client().login(access_key_id, access_key_secret)
    return {"saved_to": str(config.config_file()), "expires_in": token.expires_in}


@app.command()
@json_command
def skill(
    command: Annotated[
        Optional[list[str]],
        typer.Argument(help="命令路径，如 login 或 app run；不填显示用法。"),
    ] = None,
) -> dict:
    """查看命令的使用文档。"""
    if not command:
        return {
            "usage": "shadowbot-cli skill <命令路径>",
            "example": "shadowbot-cli skill login",
        }
    target = resolve(build_root(app), command)
    if target is None:
        _fail_and_exit("usage_error", f"未知命令：{' '.join(command)}")
    content = read_doc(command)
    if content is None:
        content = command_help(target, command)
        source = "help"
    else:
        source = "markdown"
    return {"command": " ".join(command), "source": source, "content": content}


def run() -> None:
    """程序入口：先加载 .env，再运行 Typer 应用。

    load_dotenv 用 find_dotenv(usecwd=True) 从用户当前目录向上查找 .env，
    这样无论从哪个目录调用 CLI 都能读到项目里的 .env。
    """
    load_dotenv(find_dotenv(usecwd=True))
    app()
