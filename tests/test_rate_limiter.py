"""http 层：跨进程令牌桶限流器。"""

import pytest

from shadowbot_cli.http.rate_limiter import RateLimit, RateLimiter, RateLimitTimeout


class _FakeClock:
    """可控时钟：sleep 会推进时间，模拟真实时间的流逝。"""

    def __init__(self, now=0.0):
        self._now = now

    def __call__(self):
        return self._now

    def sleep(self, dt):
        self._now += dt


def _limiter(tmp_path, *, rate=1.0, capacity=1.0, clock=None):
    clock = clock or _FakeClock()
    return RateLimiter(tmp_path, _time=clock, _sleep=clock.sleep), clock


def test_acquire_immediately_within_capacity(tmp_path):
    limiter, _ = _limiter(tmp_path, rate=10, capacity=3)
    limit = RateLimit(rate=10, capacity=3, name="a")
    limiter.acquire(limit)
    limiter.acquire(limit)
    limiter.acquire(limit)  # 桶满时连拿 3 个不阻塞


def test_acquire_blocks_until_refill(tmp_path):
    limiter, clock = _limiter(tmp_path, rate=1.0, capacity=1.0)
    limit = RateLimit(rate=1.0, capacity=1.0, name="a")
    limiter.acquire(limit)
    limiter.acquire(limit)  # 桶空，需等 ~1s（fake 时钟自动推进）
    assert clock() >= 1.0


def test_acquire_timeout(tmp_path):
    limiter, _ = _limiter(tmp_path, rate=0.1, capacity=1.0)
    limit = RateLimit(rate=0.1, capacity=1.0, name="a")
    limiter.acquire(limit)
    with pytest.raises(RateLimitTimeout):
        limiter.acquire(limit, timeout=0.3)


def test_state_shared_via_file(tmp_path):
    """两个限流器实例共享同一状态文件（模拟跨进程并行）。"""
    limit = RateLimit(rate=1.0, capacity=1.0, name="a")
    clock = _FakeClock()
    a = RateLimiter(tmp_path, _time=clock, _sleep=clock.sleep)
    a.acquire(limit)  # 桶被打空
    clock.sleep(0.5)  # 只回填了 0.5 个令牌
    b = RateLimiter(tmp_path, _time=clock, _sleep=clock.sleep)  # 新实例读同一状态
    assert (tmp_path / "a.json").exists()  # 状态已落盘
    b.acquire(limit, timeout=2)  # 还需等 0.5s
    assert clock() >= 1.0


def test_invalid_rate_raises(tmp_path):
    limiter, _ = _limiter(tmp_path)
    with pytest.raises(ValueError):
        limiter.acquire(RateLimit(rate=0, capacity=1, name="bad"))


def test_lock_file_separate_from_state(tmp_path):
    """锁文件与状态文件分离：避免 Windows 上 os.replace 替换仍持锁的状态文件时 PermissionError。"""
    limiter, _ = _limiter(tmp_path, rate=10, capacity=3)
    limit = RateLimit(rate=10, capacity=3, name="a")
    limiter.acquire(limit)
    assert (tmp_path / "a.json").exists()
    assert (tmp_path / "a.lock").exists()
