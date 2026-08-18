"""应用详情本地缓存：按 appId 存 version / instruction / flowParams。

目录：$XDG_STATE_HOME/shadowbot-cli（未设置时回落到 ~/.local/state/shadowbot-cli）。
用途：`app list` 拉详情前先查缓存，version 未变的命中直接复用，避免重复请求。

清理策略：
  - 内容新鲜度由 version 字段保证（版本一变即重拉）；
  - 条目带 cached_at，命中续期、写成功记时；load() 时剔除超 TTL 的条目（孤儿回收）；
  - save() 用临时文件 + os.replace 原子替换，避免并发/中断写坏缓存。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from . import config

# 孤儿条目回收阈值（秒）：应用超过该时长未在列表里被确认，视为已下线，丢弃缓存。
CACHE_TTL = 30 * 24 * 3600


def _path() -> Path:
    return config.state_dir() / "app-cache.json"


def _read() -> dict:
    """读取缓存文件；缺失或损坏返回空 dict。"""
    path = _path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load() -> dict:
    """读取缓存，并剔除过期 / 非法条目（孤儿回收）。"""
    now = time.time()
    return {
        key: value
        for key, value in _read().items()
        if isinstance(value, dict) and now - value.get("cached_at", 0) < CACHE_TTL
    }


def save(data: dict) -> None:
    """原子写回缓存：先写临时文件，再 os.replace 覆盖。"""
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
