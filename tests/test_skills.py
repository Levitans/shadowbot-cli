"""cli/skills.py：命令路径解析与文档定位。"""

from shadowbot_cli.cli import skills
from shadowbot_cli.cli.skills import _doc_path, read_doc, resolve, command_help


class _Node:
    """轻量替身：只需有 .commands 字典，模拟命令组/命令树。"""

    def __init__(self, name, **children):
        self.name = name
        self.commands = children


def test_doc_path_maps_command_path():
    p = _doc_path(["app", "run"])
    assert p.name == "run.md"
    assert p.parent.name == "app"
    assert _doc_path(["login"]).name == "login.md"
    assert _doc_path(["queue", "item", "add"]).name == "add.md"
    assert _doc_path(["queue", "item", "add"]).parent.name == "item"


def test_resolve_nested_path():
    run = _Node("run")
    app = _Node("app", run=run)
    root = _Node("root", app=app)

    assert resolve(root, ["app"]) is app
    assert resolve(root, ["app", "run"]) is run
    assert resolve(root, ["app", "nope"]) is None
    assert resolve(root, ["nope"]) is None


def test_read_doc_rejects_path_traversal():
    assert read_doc(["..", "config"]) is None
    assert read_doc(["a/../b"]) is None
    assert read_doc(["a\\b"]) is None


def test_command_help_falls_back_when_click_unavailable(monkeypatch):
    """模拟 typer 没有 _click 且 click 也不在 sys.modules 里：command_help 不应崩。"""
    # 清掉 skills 里已经导入的 click 类引用，强制走兜底
    monkeypatch.setattr(skills, "_typer_click", None)
    # 阻断 CliRunner 这条兜底，让它走到最后的占位文案
    monkeypatch.setattr(
        "typer.testing.CliRunner",
        None,
        raising=False,
    )
    out = command_help(_Node("login"), ["login"])
    # 占位文案是中文 + 不会抛异常
    assert isinstance(out, str)
    assert "无法生成内置帮助" in out
