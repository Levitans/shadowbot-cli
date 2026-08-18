"""stdout JSON 输出约定（CLI 层）。

所有业务命令 stdout 只输出一个 JSON 对象：
  成功: {"success": true,  "data": {...},  "error": null}
  失败: {"success": false, "data": null, "error": {"code": "...", "message": "...", "detail": ...}}
过程性日志一律写 stderr，保证 stdout 可被 Agent 直接解析。

与命令定义解耦：命令层只负责 return 数据 / 抛出异常，这里统一负责序列化。
"""

from __future__ import annotations

import json
import sys
from typing import Any

from ..errors import ApiError, AuthError, HttpError

# --- UTF-8 ---
# 强制 stdout/stderr 使用 UTF-8，避免 Windows 控制台中文乱码。
# 部分环境（如某些测试桩）的流没有 reconfigure，需兜底。


def _ensure_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        enc = getattr(stream, "encoding", None)
        if enc is not None and enc.lower() != "utf-8":
            try:
                stream.reconfigure(encoding="utf-8")
            except (AttributeError, OSError, ValueError):
                pass


_ensure_utf8()

# --- 输出 ---

_pretty = False


def set_pretty(enabled: bool) -> None:
    """启用/禁用 JSON 美化输出（仅在 stdout 为 TTY 时生效，不影响机器解析）。"""
    global _pretty
    _pretty = enabled


def emit_ok(data: Any = None) -> None:
    """输出成功信封。"""
    _emit({"success": True, "data": data, "error": None})


def emit_fail(code: str, message: str, detail: Any = None) -> None:
    """输出失败信封。"""
    error: dict[str, Any] = {"code": code, "message": message}
    if detail is not None:
        error["detail"] = detail
    _emit({"success": False, "data": None, "error": error})


def error_code(err: Exception) -> str:
    """异常类型 → 稳定的错误码。"""
    if isinstance(err, AuthError):
        return "auth_error"
    if isinstance(err, HttpError):
        return "http_error"
    if isinstance(err, ApiError):
        return "api_error"
    return "error"


def _emit(payload: dict) -> None:
    if _pretty and sys.stdout.isatty():
        # 人类在终端里：rich 美化输出
        from rich import print_json

        print_json(data=payload)
        return
    indent = 2 if _pretty else None
    print(json.dumps(payload, ensure_ascii=False, indent=indent), flush=True)
