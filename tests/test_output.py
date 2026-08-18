"""output：--pretty 美化输出路径。"""

import sys

from shadowbot_cli.cli import output


def test_pretty_output_accepts_dict(monkeypatch):
    # --pretty 且 stdout 为 TTY 时走 rich 的 print_json；
    # 旧代码把 dict 当 json 字符串传会抛 TypeError，正确写法是 print_json(data=...)。
    monkeypatch.setattr(output, "_pretty", True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    output.emit_ok({"a": 1})  # 不抛 TypeError 即通过
