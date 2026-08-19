"""skill 命令：命令树驱动的文档查找与回退。

- 文档目录 `skill/` 是命令树路径的镜像：`skill <a> <b>` → `skill/a/b.md`；
- 先用命令树校验路径是否真实存在，再读 markdown；
- 没有 markdown 时回退到该命令的内置帮助（因此新命令天然支持 skill 查询）。
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from typer.main import get_command

SKILL_DIR_NAME = "skill"

# typer 在不同版本里暴露 click 的方式不同：
# - 0.27 起把 click 内嵌成私有模块 typer._click；
# - 更老的版本里 typer 直接依赖外部 click 包（import click）；
# - 某些分支版会彻底剥离 _click。
# skill 的内置帮助回退只是 nice-to-have，缺 _click 时要保证模块本身能加载、
# CLI 能启动，所以这里链式 import + 兜底占位，不让任何一种 typer 版本炸进程。
try:
    from typer import _click as _typer_click  # typer 0.27 起
except ImportError:
    try:
        import click as _typer_click  # 旧版 typer
    except ImportError:
        _typer_click = None


def _skill_dir() -> Path:
    return Path(importlib.resources.files("shadowbot_cli")) / SKILL_DIR_NAME


def _doc_path(segments: list[str]) -> Path:
    """命令路径 → 文档文件：skill/<seg1>/<seg2>.md"""
    parent = _skill_dir().joinpath(*segments[:-1])
    return parent / f"{segments[-1]}.md"


def build_root(app):
    """从 Typer 应用构建命令树根节点。"""
    return get_command(app)


def resolve(root, segments: list[str]):
    """沿命令树解析路径，返回目标命令；路径无效返回 None。"""
    node = root
    for seg in segments:
        if not hasattr(node, "commands") or seg not in node.commands:
            return None
        node = node.commands[seg]
    return node


def read_doc(segments: list[str]) -> str | None:
    """读取命令路径对应的 markdown 文档；不存在或路径非法返回 None。

    调用方已用命令树校验过 segments（都是真实命令名），这里再兜底挡路径穿越。
    """
    for seg in segments:
        if seg in ("", ".", "..") or "/" in seg or "\\" in seg:
            return None
    path = _doc_path(segments)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def command_help(command, segments: list[str]) -> str:
    """生成命令的内置帮助文本（skill 的回退输出）。

    优先用 typer._click.Context（typer 0.27 起的标准入口）；
    缺 _click 时用 typer.testing.CliRunner 触发 --help 拿输出；
    都不行时返回占位文案——help 拿不到不影响 CLI 主流程。
    """
    if _typer_click is not None:
        ctx = _typer_click.Context(command, info_name=" ".join(segments))
        return command.get_help(ctx)

    try:
        from typer.testing import CliRunner

        return CliRunner().invoke(command, ["--help"]).output
    except Exception:
        return "（当前 typer 版本无法生成内置帮助，请参考 skill/<命令路径>.md 或 --help）\n"
