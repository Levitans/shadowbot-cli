"""api 层：令牌响应解析、login 持久化、get_token 鉴权。"""

import pytest

from shadowbot_cli import app_cache, config
from shadowbot_cli.api.client import ApiClient, _parse_token
from shadowbot_cli.api.models import Token
from shadowbot_cli.api.rate_limits import rate_limit_for
from shadowbot_cli.errors import ApiError, AuthError, HttpError


# --- QPS 登记表 ---
def test_rate_limit_for_known_path():
    limit = rate_limit_for("/oapi/token/v2/token/create")
    assert limit is not None
    assert limit.rate == 20  # 文档：token 接口 20 次/秒
    assert limit.capacity == 20
    assert limit.name == "oapi/token/v2/token/create"


def test_rate_limit_table_matches_doc():
    # 抽查几个文档登记值
    assert rate_limit_for("/oapi/dispatch/v2/job/query").rate == 30
    assert rate_limit_for("/oapi/dispatch/v2/client/query").rate == 20
    assert rate_limit_for("/oapi/robot/v2/queryRobotParam").rate == 3
    assert rate_limit_for("/oapi/token/v2/signature/create").rate == 5


def test_rate_limit_for_unknown_path():
    assert rate_limit_for("/oapi/not/in/table") is None


class _FakeHttp:
    """替身：记录请求参数，返回预置响应或抛错。"""

    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def get(self, path, *, params=None, rate_limit=None, **kwargs):
        self.calls.append({"path": path, "params": params, "rate_limit": rate_limit})
        if self.error is not None:
            raise self.error
        return self.payload


# --- 响应解析 ---
def test_parse_token_flat():
    assert _parse_token({"access_token": "tok", "expires_in": 7200}) == Token("tok", 7200)


def test_parse_token_wrapped():
    assert _parse_token({"code": 0, "data": {"accessToken": "tok", "expiresIn": 3600}}) == Token("tok", 3600)


def test_parse_token_error():
    with pytest.raises(ApiError, match="bad key"):
        _parse_token({"code": 400, "message": "bad key"})


def test_parse_token_no_token():
    with pytest.raises(ApiError):
        _parse_token({"foo": "bar"})


# --- create_token ---
def test_create_token_passes_params_and_rate_limit():
    http = _FakeHttp(payload={"access_token": "tok", "expires_in": 7200})
    client = ApiClient(http=http)
    token = client.create_token("k1", "s1")
    assert token.access_token == "tok"
    assert http.calls[0]["path"] == "/oapi/token/v2/token/create"
    assert http.calls[0]["params"] == {"accessKeyId": "k1", "accessKeySecret": "s1"}
    assert http.calls[0]["rate_limit"] is not None  # 已从 QPS 登记表取到配置


def test_create_token_wraps_http_error():
    http = _FakeHttp(error=HttpError("connection refused"))
    client = ApiClient(http=http)
    with pytest.raises(ApiError, match="connection refused"):
        client.create_token("k", "s")


# --- login ---
def test_login_persists_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    http = _FakeHttp(payload={"access_token": "tok", "expires_in": 7200})
    token = ApiClient(http=http).login("k1", "s1")
    assert token.access_token == "tok"
    data = config.load()
    assert data["access_key_id"] == "k1"
    assert data["access_key_secret"] == "s1"
    assert data["access_token"] == "tok"


# --- get_token ---
def test_get_token_without_login(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(AuthError):
        ApiClient(http=_FakeHttp()).get_token()


def test_get_token_returns_valid(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save({"access_token": "tok", "expires_at": 9999999999})
    assert ApiClient(http=_FakeHttp()).get_token() == "tok"


# --- 应用查询 ---
APP_LIST_PATH = "/oapi/app/open/query/list"
APP_ONLINE_PATH = "/oapi/app/open/query/appOnlineDetailWithParam"
APP_VERSION_PATH = "/oapi/app/open/query/appVersionDetail"


class _FakeAppHttp:
    """替身：按 path 分发响应（支持可调用响应），记录请求。"""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def request(self, method, path, *, params=None, json=None, headers=None, rate_limit=None, **kwargs):
        self.calls.append({
            "method": method, "path": path, "params": params,
            "json": json, "headers": headers, "rate_limit": rate_limit,
        })
        resp = self.responses.get(path)
        if callable(resp):
            return resp(json or {}, params or {})
        if resp is not None:
            return resp
        return {"success": True, "code": 200, "data": None, "page": {}}


def _app_client(monkeypatch, tmp_path, responses):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    http = _FakeAppHttp(responses)
    client = ApiClient(http=http)
    monkeypatch.setattr(client, "get_token", lambda: "tok")
    return client, http


def test_query_app_list_by_name(monkeypatch, tmp_path):
    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: {"success": True, "code": 200, "data": [], "page": {"pages": 1}},
    })
    client.query_app_list(app_name="测试", page=2)
    call = http.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == APP_LIST_PATH
    assert call["json"] == {"page": "2", "size": "30", "appName": "测试"}
    assert call["headers"] == {"Authorization": "Bearer tok"}
    assert call["rate_limit"] is not None


def test_query_app_list_by_owner(monkeypatch, tmp_path):
    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: {"success": True, "code": 200, "data": [], "page": {"pages": 1}},
    })
    client.query_app_list(owner_account="guodong@fckjjs")
    assert http.calls[0]["json"] == {"page": "1", "size": "30", "ownerUserSearchKey": "guodong@fckjjs"}


def test_query_app_flow_params(monkeypatch, tmp_path):
    params = [{"name": "参数1", "direction": "In"}]
    client, http = _app_client(monkeypatch, tmp_path, {
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": params}},
    })
    assert client.query_app_flow_params("app-1") == params
    assert http.calls[0]["method"] == "GET"
    assert http.calls[0]["params"] == {"appId": "app-1"}


def test_query_app_flow_params_missing(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": None},
    })
    assert client.query_app_flow_params("app-1") == []


def test_query_app_instruction(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": "<p>说明</p>"}},
    })
    assert client.query_app_instruction("app-1") == "<p>说明</p>"


def test_call_raises_on_business_failure(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: {"success": False, "code": 500, "message": "boom"},
    })
    with pytest.raises(ApiError, match="boom"):
        client.query_app_list()


def _list_response(items, pages=1):
    return {"success": True, "code": 200, "data": items, "page": {"total": len(items), "pages": pages}}


def _app_item(app_id, *, version="3", app_type="app", name="应用"):
    return {"appId": app_id, "appName": name, "appType": app_type, "version": version,
            "ownerName": "果冻", "ownerAccount": "guodong@fckjjs"}


def test_list_apps_filters_and_enriches(monkeypatch, tmp_path):
    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([
            _app_item("a1", name="应用1"),
            _app_item("a2", name="未发版", version="未发版"),
            _app_item("a3", name="指令", app_type="activity"),
        ]),
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": [{"name": "p"}]}},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": "<p>ins</p>"}},
    })
    result = client.list_apps()
    assert result["total"] == 1
    item = result["list"][0]
    assert item["appId"] == "a1"
    assert item["appName"] == "应用1"
    assert item["ownerName"] == "果冻"
    assert item["ownerAccount"] == "guodong@fckjjs"
    assert item["instruction"] == "<p>ins</p>"
    assert item["flowParams"] == [{"name": "p"}]
    detail_calls = [c for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)]
    assert {c["path"] for c in detail_calls} == {APP_ONLINE_PATH, APP_VERSION_PATH}
    assert len(detail_calls) == 2


def test_list_apps_cache_hit_skips_detail(monkeypatch, tmp_path):
    responses = {
        APP_LIST_PATH: _list_response([_app_item("a1")]),
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": []}},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": ""}},
    }
    client, http = _app_client(monkeypatch, tmp_path, responses)
    client.list_apps()
    assert sum(1 for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)) == 2
    http.calls.clear()
    client.list_apps()
    assert sum(1 for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)) == 0


def test_list_apps_version_change_refetches(monkeypatch, tmp_path):
    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([_app_item("a1", version="3")]),
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": []}},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": ""}},
    })
    client.list_apps()
    http.responses[APP_LIST_PATH] = _list_response([_app_item("a1", version="4")])
    http.calls.clear()
    client.list_apps()
    assert sum(1 for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)) == 2


def test_list_apps_detail_failure_not_cached(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([_app_item("a1")]),
        APP_ONLINE_PATH: {"success": False, "code": 500, "message": "未发版"},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": "ins"}},
    })
    result = client.list_apps()
    item = result["list"][0]
    assert item["instruction"] == ""
    assert item["flowParams"] == []
    assert app_cache.load() == {}


def test_fetch_all_pages_loops(monkeypatch, tmp_path):
    def list_handler(body, params):
        page = int(body["page"])
        return _list_response([_app_item(f"a{page}")], pages=2)

    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: list_handler,
    })
    result = client.list_apps()
    assert result["total"] == 2
    assert [i["appId"] for i in result["list"]] == ["a1", "a2"]
    list_calls = [c for c in http.calls if c["path"] == APP_LIST_PATH]
    assert len(list_calls) == 2
