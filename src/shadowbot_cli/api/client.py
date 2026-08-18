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

from .. import app_cache, config
from ..errors import ApiError, AuthError, HttpError
from ..http.client import HttpClient
from ..http.rate_limiter import RateLimiter
from .models import Token
from .rate_limits import (
    APP_LIST_PATH,
    APP_ONLINE_DETAIL_PATH,
    APP_VERSION_DETAIL_PATH,
    CLIENT_GROUP_LIST_PATH,
    CLIENT_LIST_PATH,
    TOKEN_PATH,
    rate_limit_for,
)

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
        """读取有效令牌；过期时用已保存的 key/secret 自动换取新令牌。

        login 后凭据与令牌都会持久化到 config：令牌过期无需重新 login，
        直接用保存的 key/secret 静默续期；只有 key/secret 缺失或无效才抛 AuthError。
        """
        cfg = config.load()
        token = cfg.get("access_token")
        expires_at = cfg.get("expires_at", 0)
        if token and time.time() <= expires_at:
            return str(token)

        key_id = cfg.get("access_key_id")
        key_secret = cfg.get("access_key_secret")
        if not key_id or not key_secret:
            raise AuthError("未登录，请先运行 login 命令")

        # 令牌缺失或过期：用保存的凭据换取新令牌
        try:
            refreshed = self.create_token(str(key_id), str(key_secret))
        except ApiError as e:
            raise AuthError(
                f"无法自动获取令牌，Access Key 可能已失效，请重新运行 login 命令（{e}）"
            ) from e
        config.save(
            {
                **cfg,
                "access_token": refreshed.access_token,
                "expires_at": time.time() + refreshed.expires_in,
            }
        )
        return refreshed.access_token

    # --- 应用查询 ---
    def _call(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一鉴权 + 限流 + 业务错误判定的请求入口（应用查询接口共用）。

        令牌来自 get_token（未登录抛 AuthError）；限流按路径从登记表取。
        影刀成功时 success=true、code=200/0，否则抛 ApiError。
        """
        token = self.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            payload = self._http.request(
                method, path, params=params, json=json,
                headers=headers, rate_limit=rate_limit_for(path),
            )
        except HttpError as e:
            raise ApiError(f"请求 {path} 失败：{e}") from e
        if not isinstance(payload, dict):
            raise ApiError(f"接口响应格式异常：{payload!r}")
        code = _lookup(payload, "code")
        if _lookup(payload, "success") is False or (code is not None and str(code) not in ("200", "0")):
            raise ApiError(f"接口调用失败：{_lookup(payload, 'message', 'msg', 'error') or '未知错误'}")
        return payload

    def query_app_list(
        self,
        *,
        page: int = 1,
        size: int = 30,
        app_name: str | None = None,
        owner_account: str | None = None,
    ) -> dict[str, Any]:
        """查询应用列表（POST APP_LIST_PATH），返回 {"list": [...], "page": {...}}。"""
        body: dict[str, str] = {"page": str(page), "size": str(size)}
        if app_name:
            body["appName"] = app_name
        elif owner_account:
            body["ownerUserSearchKey"] = owner_account
        payload = self._call("POST", APP_LIST_PATH, json=body)
        data = payload.get("data")
        items = data if isinstance(data, list) else []
        page_info = payload.get("page")
        return {"list": items, "page": page_info if isinstance(page_info, dict) else {}}

    def query_app_flow_params(self, app_id: str) -> list[dict[str, Any]]:
        """查询线上版本参数（GET APP_ONLINE_DETAIL_PATH），返回 data.flowParams。"""
        payload = self._call("GET", APP_ONLINE_DETAIL_PATH, params={"appId": app_id})
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        params = data.get("flowParams")
        return params if isinstance(params, list) else []

    def query_app_instruction(self, app_id: str) -> str:
        """查询应用说明（GET APP_VERSION_DETAIL_PATH），返回 data.instruction。"""
        payload = self._call("GET", APP_VERSION_DETAIL_PATH, params={"appId": app_id})
        data = payload.get("data")
        if not isinstance(data, dict):
            return ""
        return data.get("instruction") or ""

    def _fetch_all_pages(
        self, *, app_name: str | None, owner_account: str | None
    ) -> list[dict[str, Any]]:
        """循环拉取列表全部分页并累加返回。

        列表不缓存：version 是判断详情缓存是否过期的信号，必须每次拿最新值，
        否则应用升级后列表仍返回旧版本，详情缓存无法感知。
        size 取 100（实测接口支持）减少页数。
        """
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            res = self.query_app_list(page=page, size=100, app_name=app_name, owner_account=owner_account)
            items.extend(res["list"])
            try:
                pages = int(res["page"].get("pages", 1) or 1)
            except (TypeError, ValueError):
                pages = 1
            if page >= pages:
                break
            page += 1
        return items

    def _fetch_detail(self, app_id: str, version: str) -> dict[str, Any] | None:
        """拉取单个应用的 instruction + flowParams；任一失败返回 None（不写缓存）。"""
        try:
            return {
                "version": version,
                "instruction": self.query_app_instruction(app_id),
                "flowParams": self.query_app_flow_params(app_id),
            }
        except AuthError:
            raise
        except ApiError:
            return None

    def list_apps(
        self,
        *,
        app_name: str | None = None,
        owner_account: str | None = None,
        include_all: bool = False,
    ) -> dict[str, Any]:
        """查询已发版应用，附带参数说明与使用说明（带本地缓存）。

        默认只返回 appType=app、已发版、且带使用说明（instruction）的应用——
        Agent 靠说明判断用途，没有说明的应用对 Agent 没有意义。无说明的应用
        同样按 appId+version 缓存（命中即复用），只是不出现在结果里。
        --include-all 关闭全部过滤，原样返回。
        """
        all_items = self._fetch_all_pages(app_name=app_name, owner_account=owner_account)
        cache = app_cache.load()
        result: list[dict[str, Any]] = []
        for item in all_items:
            if not include_all and (item.get("appType") != "app" or item.get("version") == "未发版"):
                continue
            app_id = item.get("appId")
            version = str(item.get("version"))
            entry = cache.get(app_id)
            if entry and entry.get("version") == version:
                entry["cached_at"] = time.time()
            else:
                entry = self._fetch_detail(app_id, version)
                if entry is not None:
                    entry["cached_at"] = time.time()
                    cache[app_id] = entry
            if not include_all and not (entry or {}).get("instruction"):
                continue  # 无使用说明，Agent 无法判断用途，不出现在结果里（缓存已复用）
            result.append({
                "appId": app_id,
                "appName": item.get("appName"),
                "ownerName": item.get("ownerName"),
                "ownerAccount": item.get("ownerAccount"),
                "instruction": (entry or {}).get("instruction", ""),
                "flowParams": (entry or {}).get("flowParams", []),
            })
        app_cache.save(cache)
        return {"list": result, "total": len(result)}

    # --- 机器人管理 ---
    def _fetch_all(self, path: str) -> list[dict[str, Any]]:
        """循环拉取列表接口全部分页并累加返回（size 取 100 减少页数）。

        分页终止条件同 _fetch_all_pages：读响应 page.pages。
        """
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            payload = self._call("POST", path, json={"page": page, "size": 100})
            data = payload.get("data")
            items.extend(data if isinstance(data, list) else [])
            page_info = payload.get("page")
            try:
                pages = int((page_info if isinstance(page_info, dict) else {}).get("pages", 1) or 1)
            except (TypeError, ValueError):
                pages = 1
            if page >= pages:
                break
            page += 1
        return items

    def list_robot_groups(self) -> dict[str, Any]:
        """查询机器人组列表（POST CLIENT_GROUP_LIST_PATH），返回 {"list": [...], "total": N}。"""
        items = self._fetch_all(CLIENT_GROUP_LIST_PATH)
        return {"list": items, "total": len(items)}

    def list_robots(self) -> dict[str, Any]:
        """查询机器人列表（POST CLIENT_LIST_PATH），返回 {"list": [...], "total": N}。

        每条只保留 robotClientUuid / robotClientName / status 三个字段，
        接口返回的 IP、机器名、版本等对 Agent 判断用途没有帮助，一律裁掉。
        """
        items = self._fetch_all(CLIENT_LIST_PATH)
        result = [
            {
                "robotClientUuid": r.get("robotClientUuid"),
                "robotClientName": r.get("robotClientName"),
                "status": r.get("status"),
            }
            for r in items
        ]
        return {"list": result, "total": len(result)}


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
