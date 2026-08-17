"""CLI 统一异常。

分层约定：
  - HttpError：http 层（网络错误 / 非 2xx / 响应解析失败）
  - ApiError：OpenAPI 层（接口业务失败，如 code != 0）
  - AuthError：OpenAPI 层（未登录 / 令牌过期）
CLI 层统一捕获 ShadowBotError 并格式化输出。
"""

from __future__ import annotations


class ShadowBotError(RuntimeError):
    """CLI 基础异常。"""


class HttpError(ShadowBotError):
    """HTTP 层异常。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        method: str | None = None,
        url: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.url = url


class ApiError(ShadowBotError):
    """OpenAPI 接口调用失败（业务错误，如 code != 0）。"""


class AuthError(ApiError):
    """未登录或令牌失效。"""
