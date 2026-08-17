"""配置存储：凭据与令牌按 XDG 目录规范保存在本地。

目录：$XDG_CONFIG_HOME/shadowbot-cli（未设置时回落到 ~/.config/shadowbot-cli）。
如需测试隔离，可设置 XDG_CONFIG_HOME 指向临时目录。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "shadowbot-cli"


def config_dir() -> Path:
    """配置目录，遵循 XDG：优先 $XDG_CONFIG_HOME，否则 ~/.config。"""
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".config" / APP_NAME


def config_file() -> Path:
    """配置文件路径。"""
    return config_dir() / "config.json"


def state_dir() -> Path:
    """状态目录（限流器等运行时状态）：$XDG_STATE_HOME 或 ~/.local/state。"""
    base = os.environ.get("XDG_STATE_HOME")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ".local" / "state" / APP_NAME


def load() -> dict[str, object]:
    """读取配置，文件不存在或损坏时返回空 dict。"""
    path = config_file()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save(data: dict[str, object]) -> None:
    """写入配置；文件含密钥，收紧为 0600。"""
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # Windows 无 POSIX 权限位，忽略
