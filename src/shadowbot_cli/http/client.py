"""底层 HTTP 客户端：httpx 封装 + 可选跨进程限流 + 重试 + 错误归一。

本层不关心"影刀 OpenAPI"是什么：
  - 只负责发送请求、按调用方传入的 RateLimit 限流、重试、解析 JSON；
  - 网络错误 / 非 2xx / 非 JSON 统一抛 HttpError。
OpenAPI 业务语义（路径、参数、响应解析）在 api 层实现。
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from ..errors import HttpError
from .rate_limiter import RateLimit, RateLimiter

# 429/5xx 重试的指数退避基数（秒）
_BACKOFF_BASE = 0.5


class HttpClient:
    def __init__(
        self,
        *,
        base_url: str,
        rate_limiter: RateLimiter,
        timeout: float = 30.0,
        retries: int = 3,
        transport: httpx.BaseTransport | None = None,
        _sleep: Any = time.sleep,
    ):
        self._limiter = rate_limiter
        self._retries = retries
        self._sleep = _sleep
        self._client = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)

    def get(self, path: str, *, rate_limit: RateLimit | None = None, **kwargs: Any) -> Any:
        return self.request("GET", path, rate_limit=rate_limit, **kwargs)

    def post(self, path: str, *, rate_limit: RateLimit | None = None, **kwargs: Any) -> Any:
        return self.request("POST", path, rate_limit=rate_limit, **kwargs)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        rate_limit: RateLimit | None = None,
    ) -> Any:
        """发送请求并返回解析后的 JSON。

        限流：rate_limit 不为 None 时，先向限流器申请令牌（可能阻塞）。
        重试：网络错误、429、5xx 按指数退避重试（默认 3 次）。
        """
        if rate_limit is not None:
            self._limiter.acquire(rate_limit)

        last_error: BaseException | None = None
        for attempt in range(self._retries):
            try:
                resp = self._client.request(method, path, params=params, json=json, headers=headers)
            except httpx.HTTPError as e:
                last_error = e
            else:
                if resp.status_code == 429 or resp.status_code >= 500:
                    last_error = HttpError(
                        f"HTTP {resp.status_code}", status_code=resp.status_code, method=method, url=path
                    )
                elif resp.status_code >= 400:
                    raise HttpError(
                        f"HTTP {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                        method=method,
                        url=path,
                    )
                else:
                    return self._parse_json(resp)

            if attempt < self._retries - 1:
                self._sleep(_BACKOFF_BASE * (2**attempt))

        raise HttpError(f"请求失败（重试 {self._retries} 次后放弃）：{last_error}", method=method, url=path)

    def _parse_json(self, resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError as e:
            raise HttpError(
                f"响应不是有效 JSON：{resp.text[:200]}", status_code=resp.status_code
            ) from e
