"""跨进程令牌桶限流器。

影刀开放平台不同接口有各自的 QPS 上限。CLI 可能被脚本 / 定时任务并行调用，
进程内限流挡不住并行进程的合流，所以这里用「状态文件 + 文件锁」实现跨进程
共享的令牌桶：多个进程读写同一份桶状态，靠 fcntl 文件锁保证原子性。

状态文件存放在 XDG state 目录（config.state_dir()），与配置目录分开。
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # Windows 没有 fcntl
    fcntl = None

# 进程内兜底锁（无 fcntl 平台 / 单进程场景）
_in_process_lock = threading.Lock()


class RateLimitTimeout(RuntimeError):
    """在限定时间内拿不到令牌。"""


@dataclass(frozen=True)
class RateLimit:
    rate: float  # 每秒补充的令牌数（≈QPS）
    capacity: float  # 桶容量（允许的瞬时突发上限）
    name: str  # 桶标识，作为状态文件名区分不同的桶


class _FileLock:
    """基于 fcntl 的跨进程文件锁；无 fcntl 时退回进程内锁。

    锁文件与被保护的数据文件分离：避免 Windows 上 os.replace
    替换仍持锁的数据文件时 PermissionError（Win32 不允许重命名
    或替换有打开句柄的文件）。
    """

    def __init__(self, lock_path: Path):
        self._path = lock_path
        self._fh: Any = None
        self._fallback = _in_process_lock if fcntl is None else None

    def __enter__(self):
        self._fh = open(self._path, "a+")
        if fcntl is not None:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX)
        else:
            self._fallback.acquire()
        return self

    def __exit__(self, *exc):
        try:
            if fcntl is not None:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            if fcntl is None:
                self._fallback.release()


class RateLimiter:
    """跨进程令牌桶。state_dir 下每个桶对应一个 JSON 状态文件。"""

    def __init__(self, state_dir: Path, *, _time: Any = time.time, _sleep: Any = time.sleep):
        # _time / _sleep 可注入，便于测试用可控时钟
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._time = _time
        self._sleep = _sleep

    def acquire(self, limit: RateLimit, tokens: float = 1.0, timeout: float | None = None) -> None:
        """获取 tokens 个令牌；不足时阻塞等待（锁外分片睡眠），超时抛 RateLimitTimeout。"""
        if limit.rate <= 0 or limit.capacity <= 0:
            raise ValueError(f"非法的限流配置：{limit}")
        state_file = self._state_dir / f"{_safe_name(limit.name)}.json"
        lock_file = state_file.with_suffix(".lock")
        deadline = self._time() + timeout if timeout is not None else None
        while True:
            with _FileLock(lock_file):
                state = self._read_state(state_file, limit)
                now = self._time()
                refilled = state["tokens"] + (now - state["last_refill"]) * limit.rate
                state["tokens"] = min(limit.capacity, refilled)
                state["last_refill"] = now
                if state["tokens"] >= tokens:
                    state["tokens"] -= tokens
                    self._write_state(state_file, state)
                    return
                wait = (tokens - state["tokens"]) / limit.rate
            # 锁外等待，分片睡眠便于及时响应超时 / 并发
            if deadline is not None and self._time() >= deadline:
                raise RateLimitTimeout(f"{limit.name} 等待限流令牌超时")
            self._sleep(min(wait, 0.05))

    def _read_state(self, path: Path, limit: RateLimit) -> dict[str, float]:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state, dict):
                raise ValueError
            return {
                "tokens": float(state.get("tokens", limit.capacity)),
                "last_refill": float(state.get("last_refill", self._time())),
            }
        except (OSError, ValueError, json.JSONDecodeError):
            # 文件缺失或损坏：视为全新状态（持锁期间，安全）
            return {"tokens": limit.capacity, "last_refill": self._time()}

    def _write_state(self, path: Path, state: dict[str, float]) -> None:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        os.replace(tmp, path)  # 原子替换，避免其他进程读到半截


def _safe_name(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
