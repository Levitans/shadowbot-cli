"""cli/skills.py：命令路径解析与文档定位。"""

from shadowbot_cli.cli.skills import _doc_path, read_doc, resolve


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
