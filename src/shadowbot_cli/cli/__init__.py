"""CLI 层。

注意：这里故意不重导出 app/run，避免包名 `cli.app` 与子模块 `cli.app` 冲突
（那会让 `shadowbot_cli.cli.app` 指向 Typer 实例而不是子模块）。
入口统一走 `shadowbot_cli.cli.app` 子模块。
"""
