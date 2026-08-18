"""cli 层：JSON 信封输出、参数、环境变量、错误处理、skill。"""

import json

from typer.testing import CliRunner

from shadowbot_cli.api.models import Token
from shadowbot_cli.cli.app import app
from shadowbot_cli.errors import ApiError

runner = CliRunner()


class _FakeApi:
    """替身：记录传给 api 层的参数，返回预置结果或抛错。"""

    def __init__(self, token=None, error=None, seen=None):
        self._token = token
        self._error = error
        self.seen = seen if seen is not None else {}

    def login(self, access_key_id, access_key_secret):
        self.seen["id"] = access_key_id
        self.seen["secret"] = access_key_secret
        if self._error is not None:
            raise self._error
        return self._token


def _fake_api(monkeypatch, *, token=None, error=None) -> _FakeApi:
    fake = _FakeApi(token=token, error=error)
    monkeypatch.setattr("shadowbot_cli.cli.app.build_api_client", lambda: fake)
    return fake


def _load_json(result) -> dict:
    # stdout 只承载 JSON 信封；result.stderr 才是人类可读信息
    return json.loads(result.stdout)


# --- login ---
def test_login_success(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _fake_api(monkeypatch, token=Token(access_token="tok", expires_in=7200))
    result = runner.invoke(app, ["login", "--access-key-id", "key-id", "--access-key-secret", "key-secret"])
    assert result.exit_code == 0
    data = _load_json(result)
    assert data["success"] is True
    assert data["error"] is None
    assert data["data"]["expires_in"] == 7200
    assert "saved_to" in data["data"]
    assert result.stderr == ""  # 业务命令 stderr 保持为空，信息全在 JSON 里


def test_login_via_env_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    fake = _fake_api(monkeypatch, token=Token(access_token="tok", expires_in=7200))
    monkeypatch.setenv("SHADOWBOT_ACCESS_KEY_ID", "env-id")
    monkeypatch.setenv("SHADOWBOT_ACCESS_KEY_SECRET", "env-secret")
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 0
    assert fake.seen == {"id": "env-id", "secret": "env-secret"}
    assert _load_json(result)["success"] is True


def test_login_missing_credentials():
    result = runner.invoke(app, ["login"])
    assert result.exit_code == 2
    data = _load_json(result)
    assert data["success"] is False
    assert data["error"]["code"] == "usage_error"


def test_login_api_error(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _fake_api(monkeypatch, error=ApiError("获取令牌失败"))
    result = runner.invoke(app, ["login", "--access-key-id", "a", "--access-key-secret", "b"])
    assert result.exit_code == 1
    data = _load_json(result)
    assert data["success"] is False
    assert data["data"] is None
    assert data["error"]["code"] == "api_error"
    assert data["error"]["message"] == "获取令牌失败"
    assert result.stderr == ""


# --- version ---
def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    data = _load_json(result)
    assert data["success"] is True
    assert data["data"]["name"] == "shadowbot-cli"
    assert data["data"]["version"] == "0.1.0"


# --- skill ---
def test_skill_without_args_shows_usage():
    result = runner.invoke(app, ["skill"])
    assert result.exit_code == 0
    assert "shadowbot-cli skill <命令路径>" in result.stdout


def test_skill_reads_doc():
    # 直接输出 Markdown 原始内容，不套 JSON 信封
    result = runner.invoke(app, ["skill", "login"])
    assert result.exit_code == 0
    assert result.stdout.startswith("# shadowbot-cli login")
    assert "shadowbot-cli login --access-key-id" in result.stdout
    assert result.stderr == ""


def test_skill_falls_back_to_builtin_help():
    # skill 命令本身没有 markdown，应回退到内置帮助
    result = runner.invoke(app, ["skill", "skill"])
    assert result.exit_code == 0
    assert "查看命令的使用文档" in result.stdout


def test_skill_unknown_command():
    result = runner.invoke(app, ["skill", "not-exist"])
    assert result.exit_code == 1
    data = _load_json(result)
    assert data["success"] is False
    assert data["error"]["code"] == "usage_error"
    assert "未知命令" in data["error"]["message"]


def test_skill_rejects_path_traversal():
    result = runner.invoke(app, ["skill", "../../config"])
    assert result.exit_code == 1
    data = _load_json(result)
    assert data["success"] is False
    assert data["error"]["code"] == "usage_error"
