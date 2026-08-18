"""影刀 OpenAPI 业务层：一个方法对应一个接口。

职责：
  - 组装依赖（build_api_client）：跨进程限流器 → HTTP 客户端 → 业务客户端；
  - 每个接口一个方法（create_token / 未来的 list_tasks / run_task ...）；
  - 调用时从 rate_limits 登记表取该接口的 QPS，传给 http 层做限流；
  - 负责认证状态：令牌的获取、持久化、过期校验。

依赖关系：api 层依赖 http 层与 config，不依赖 cli 层。
"""

from __future__ import annotations

import time
from typing import Any

from .. import config
from ..errors import ApiError, AuthError, HttpError
from ..http.client import HttpClient
from ..http.rate_limiter import RateLimiter
from .models import Token
from .rate_limits import TOKEN_PATH, rate_limit_for

API_BASE = "https://api.yingdao.com"
# 令牌接口未返回 expires_in 时的兜底有效期（秒）
TOKEN_TTL_DEFAULT = 3600


def build_api_client() -> ApiClient:
    """组装默认依赖链。"""
    limiter = RateLimiter(config.state_dir() / "rate-limiter")
    http = HttpClient(base_url=API_BASE, rate_limiter=limiter)
    return ApiClient(http=http)


class ApiClient:
    def __init__(self, http: HttpClient):
        self._http = http

    # --- 认证 ---
    def create_token(self, access_key_id: str, access_key_secret: str) -> Token:
        """获取访问令牌（GET {TOKEN_PATH}）。"""
        try:
            payload = self._http.get(
                TOKEN_PATH,
                params={"accessKeyId": access_key_id, "accessKeySecret": access_key_secret},
                rate_limit=rate_limit_for(TOKEN_PATH),
            )
        except HttpError as e:
            raise ApiError(f"获取令牌失败：{e}") from e
        return _parse_token(payload)

    def login(self, access_key_id: str, access_key_secret: str) -> Token:
        """登录：换取令牌，并把凭据与令牌持久化到本地配置。"""
        token = self.create_token(access_key_id, access_key_secret)
        config.save(
            {
                "access_key_id": access_key_id,
                "access_key_secret": access_key_secret,
                "access_token": token.access_token,
                "expires_at": time.time() + token.expires_in,
            }
        )
        return token

    def get_token(self) -> str:
        """读取有效令牌；未登录或过期抛 AuthError。后续接口鉴权时使用。"""
        cfg = config.load()
        token = cfg.get("access_token")
        expires_at = cfg.get("expires_at", 0)
        if not token or time.time() > expires_at:
            raise AuthError("未登录或令牌已过期，请先运行 login 命令")
        return token


# --- 响应解析 ---
def _lookup(payload: dict[str, Any], *names: str) -> Any:
    """在响应（含可能的 data 包装层）里大小写不敏感地找键。"""
    layers: list[dict[str, Any]] = [payload]
    inner = payload.get("data")
    if isinstance(inner, dict):
        layers.append(inner)
    for d in layers:
        for name in names:
            for key, value in d.items():
                if str(key).lower() == name.lower():
                    return value
    return None


def _parse_token(payload: Any) -> Token:
    """兼容扁平 / {code,data,message} 包装等响应结构，返回 Token。"""
    if not isinstance(payload, dict):
        raise ApiError(f"令牌接口响应格式异常：{payload!r}")
    token = _lookup(payload, "access_token", "accessToken", "token", "accesskey")
    if not token:
        code = _lookup(payload, "code")
        message = _lookup(payload, "message", "msg", "error")
        detail = f"（code={code}）{message}" if message else "请确认 Access Key 是否有效"
        raise ApiError(f"获取令牌失败：{detail}")

    expires_in = _lookup(payload, "expires_in", "expiresIn", "expire")
    if isinstance(expires_in, (int, float)) and not isinstance(expires_in, bool):
        expires_in = int(expires_in)
    else:
        expires_in = TOKEN_TTL_DEFAULT
    return Token(access_token=str(token), expires_in=expires_in)
