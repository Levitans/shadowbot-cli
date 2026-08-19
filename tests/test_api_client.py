"""api 层：令牌响应解析、login 持久化、get_token 鉴权。"""

import pytest

from shadowbot_cli import app_cache, config
from shadowbot_cli.api.client import ApiClient, _parse_token, _split_flow_params
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



def test_get_token_auto_refreshes_expired(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save(
        {
            "access_key_id": "k1",
            "access_key_secret": "s1",
            "access_token": "old",
            "expires_at": 0,  # 已过期
        }
    )
    http = _FakeHttp(payload={"access_token": "new", "expires_in": 7200})
    assert ApiClient(http=http).get_token() == "new"
    # 用保存的 key/secret 换取新令牌，并写回新令牌与有效期
    assert http.calls[0]["params"] == {"accessKeyId": "k1", "accessKeySecret": "s1"}
    data = config.load()
    assert data["access_token"] == "new"
    assert data["access_key_id"] == "k1"
    assert data["access_key_secret"] == "s1"
    assert data["expires_at"] > 0


def test_get_token_auto_refreshes_missing_token(monkeypatch, tmp_path):
    # 令牌缺失但凭据在：也应自动续期，而不是要求重新 login
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save({"access_key_id": "k1", "access_key_secret": "s1"})
    http = _FakeHttp(payload={"access_token": "new", "expires_in": 7200})
    assert ApiClient(http=http).get_token() == "new"


def test_get_token_refresh_failure_raises_auth_error(monkeypatch, tmp_path):
    # 凭据失效：自动续期失败时抛 AuthError（而非静默或 api_error）
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save(
        {
            "access_key_id": "bad",
            "access_key_secret": "bad",
            "access_token": "old",
            "expires_at": 0,
        }
    )
    http = _FakeHttp(payload={"code": 400, "message": "bad key"})
    with pytest.raises(AuthError, match="Access Key 可能已失效"):
        ApiClient(http=http).get_token()


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


def test_split_flow_params():
    params = [
        {"name": "入参1", "direction": "In", "type": "str", "value": "abc", "description": "描述", "kind": "Text"},
        {"name": "出参1", "direction": "Out", "type": "int", "value": "0", "description": "", "kind": "Expression"},
        {"name": "无方向", "type": "bool", "value": "False", "kind": "Text"},
        "non-dict-item",
    ]
    result = _split_flow_params(params)
    # 入参：direction=In 或缺失；出参：direction=Out；direction/kind 一律剔除
    assert result == {
        "input": [
            {"name": "入参1", "type": "str", "value": "abc", "description": "描述"},
            {"name": "无方向", "type": "bool", "value": "False"},  # 缺失键自然省略
            "non-dict-item",
        ],
        "output": [{"name": "出参1", "type": "int", "value": "0", "description": ""}],
    }
    # 入参列表本身不被原地修改（缓存 dict 是共享引用）
    assert params[0] == {"name": "入参1", "direction": "In", "type": "str", "value": "abc", "description": "描述", "kind": "Text"}
    assert params[1]["direction"] == "Out"


def test_split_flow_params_empty():
    assert _split_flow_params([]) == {"input": [], "output": []}


def test_list_apps_filters_and_enriches(monkeypatch, tmp_path):
    def instruction_handler(json, params):
        app_id = params.get("appId")
        return {"success": True, "code": 200, "data": {"instruction": "" if app_id == "a4" else "<p>ins</p>"}}

    def flow_handler(json, params):
        app_id = params.get("appId")
        return {"success": True, "code": 200, "data": {
            "flowParams": [{"name": "p", "direction": "In", "kind": "Text"}] if app_id == "a1" else []
        }}

    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([
            _app_item("a1", name="应用1"),
            _app_item("a2", name="未发版", version="未发版"),
            _app_item("a3", name="指令", app_type="activity"),
            _app_item("a4", name="无说明", version="2"),
        ]),
        APP_ONLINE_PATH: flow_handler,
        APP_VERSION_PATH: instruction_handler,
    })
    result = client.list_apps()
    assert [i["appId"] for i in result["list"]] == ["a1"]  # a4 无说明 → 过滤
    assert result["total"] == 1
    item = result["list"][0]
    assert item["appName"] == "应用1"
    assert item["ownerName"] == "果冻"
    assert item["ownerAccount"] == "guodong@fckjjs"
    assert item["instruction"] == "<p>ins</p>"
    assert item["flowParams"] == {"input": [{"name": "p"}], "output": []}
    # a2/a3 在拉详情前已被过滤；a1/a4 各拉 2 个详情接口 = 4 次
    detail_calls = [c for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)]
    assert {c["path"] for c in detail_calls} == {APP_ONLINE_PATH, APP_VERSION_PATH}
    assert len(detail_calls) == 4


def test_list_apps_no_instruction_filtered_and_cached(monkeypatch, tmp_path):
    responses = {
        APP_LIST_PATH: _list_response([_app_item("a1")]),
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": []}},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": ""}},
    }
    client, http = _app_client(monkeypatch, tmp_path, responses)
    assert client.list_apps()["list"] == []  # 无 instruction → 不返回
    assert sum(1 for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)) == 2
    http.calls.clear()
    assert client.list_apps()["list"] == []  # 仍不返回，且命中缓存不再拉详情
    assert sum(1 for c in http.calls if c["path"] in (APP_ONLINE_PATH, APP_VERSION_PATH)) == 0


def test_list_apps_include_all_keeps_no_instruction(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([_app_item("a1")]),
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": []}},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": ""}},
    })
    result = client.list_apps(include_all=True)
    assert [i["appId"] for i in result["list"]] == ["a1"]  # include_all 不过滤


def test_list_apps_version_change_refetches(monkeypatch, tmp_path):
    # 列表不缓存：每次重拉列表，version 从 3 变 4 → 详情缓存失效 → 重拉
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


def test_list_apps_list_always_fetched(monkeypatch, tmp_path):
    # 即使详情全部命中缓存，列表接口也每次必调（列表不缓存）
    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([_app_item("a1")]),
        APP_ONLINE_PATH: {"success": True, "code": 200, "data": {"flowParams": []}},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": ""}},
    })
    client.list_apps()
    first = sum(1 for c in http.calls if c["path"] == APP_LIST_PATH)
    http.calls.clear()
    client.list_apps()
    second = sum(1 for c in http.calls if c["path"] == APP_LIST_PATH)
    assert first == 1
    assert second == 1  # 列表接口每次都拉


def test_list_apps_detail_failure_not_cached(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: _list_response([_app_item("a1")]),
        APP_ONLINE_PATH: {"success": False, "code": 500, "message": "未发版"},
        APP_VERSION_PATH: {"success": True, "code": 200, "data": {"instruction": "ins"}},
    })
    result = client.list_apps()
    assert result["list"] == []  # 详情失败 → 视为无说明，不返回
    assert app_cache.load() == {}  # 且失败不写缓存


def test_fetch_all_pages_loops(monkeypatch, tmp_path):
    def list_handler(body, params):
        page = int(body["page"])
        return _list_response([_app_item(f"a{page}")], pages=2)

    def instruction_handler(json, params):
        return {"success": True, "code": 200, "data": {"instruction": "<p>ins</p>"}}

    client, http = _app_client(monkeypatch, tmp_path, {
        APP_LIST_PATH: list_handler,
        APP_VERSION_PATH: instruction_handler,
    })
    result = client.list_apps()
    assert result["total"] == 2
    assert [i["appId"] for i in result["list"]] == ["a1", "a2"]
    list_calls = [c for c in http.calls if c["path"] == APP_LIST_PATH]
    assert len(list_calls) == 2


# --- 机器人管理 ---
CLIENT_LIST_PATH = "/oapi/dispatch/v2/client/list"
CLIENT_GROUP_LIST_PATH = "/oapi/dispatch/v2/client/group/list"


def _group_item(uuid, name):
    return {"robotClientGroupUuid": uuid, "robotClientGroupName": name}


def _robot_item(uuid, name, status="offline"):
    # 模拟接口真实返回：除三个保留字段外还带 IP、机器名等冗余字段
    return {
        "robotClientUuid": uuid,
        "robotClientName": name,
        "status": status,
        "clientIp": "192.168.1.1",
        "machineName": "LAPTOP-X",
        "clientVersion": "6.0.30",
        "robotClientGroupUuids": [],
    }


def test_list_robot_groups(monkeypatch, tmp_path):
    client, http = _app_client(monkeypatch, tmp_path, {
        CLIENT_GROUP_LIST_PATH: _list_response([_group_item("g1", "桉夏"), _group_item("g2", "测试")]),
    })
    result = client.list_robot_groups()
    assert result["total"] == 2
    assert result["list"][0] == {"robotClientGroupUuid": "g1", "robotClientGroupName": "桉夏"}
    call = http.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == CLIENT_GROUP_LIST_PATH
    assert call["json"] == {"page": 1, "size": 100}
    assert call["headers"] == {"Authorization": "Bearer tok"}
    assert call["rate_limit"] is not None


def test_list_robot_groups_paginates(monkeypatch, tmp_path):
    def handler(body, params):
        return _list_response([_group_item(f"g{body['page']}", "组")], pages=2)

    client, http = _app_client(monkeypatch, tmp_path, {CLIENT_GROUP_LIST_PATH: handler})
    result = client.list_robot_groups()
    assert [g["robotClientGroupUuid"] for g in result["list"]] == ["g1", "g2"]
    assert sum(1 for c in http.calls if c["path"] == CLIENT_GROUP_LIST_PATH) == 2


def test_list_robots_trims_fields(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        CLIENT_LIST_PATH: _list_response([_robot_item("r1", "桉夏@fckjjs", "online")]),
    })
    result = client.list_robots()
    assert result["total"] == 1
    # 只保留三个字段，IP/机器名/版本等一律裁掉
    assert result["list"][0] == {
        "robotClientUuid": "r1",
        "robotClientName": "桉夏@fckjjs",
        "status": "online",
    }


def test_list_robots_paginates(monkeypatch, tmp_path):
    def handler(body, params):
        return _list_response([_robot_item(f"r{body['page']}", "机器人")], pages=2)

    client, http = _app_client(monkeypatch, tmp_path, {CLIENT_LIST_PATH: handler})
    result = client.list_robots()
    assert result["total"] == 2
    assert [r["robotClientUuid"] for r in result["list"]] == ["r1", "r2"]
    assert sum(1 for c in http.calls if c["path"] == CLIENT_LIST_PATH) == 2


def test_list_robots_empty_data(monkeypatch, tmp_path):
    client, _ = _app_client(monkeypatch, tmp_path, {
        CLIENT_LIST_PATH: {"success": True, "code": 200, "data": None, "page": {}},
    })
    assert client.list_robots() == {"list": [], "total": 0}

