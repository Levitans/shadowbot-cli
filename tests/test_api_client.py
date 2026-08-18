"""api 层：令牌响应解析、login 持久化、get_token 鉴权。"""

import pytest

from shadowbot_cli import config
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
