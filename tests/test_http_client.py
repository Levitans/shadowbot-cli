"""http 层：请求构造、错误归一、重试。"""

import httpx
import pytest

from shadowbot_cli.errors import HttpError
from shadowbot_cli.http.client import HttpClient
from shadowbot_cli.http.rate_limiter import RateLimiter


def _client(handler, tmp_path, *, retries=1):
    limiter = RateLimiter(tmp_path / "rl")
    return HttpClient(
        base_url="https://api.example.com",
        rate_limiter=limiter,
        retries=retries,
        transport=httpx.MockTransport(handler),
        _sleep=lambda s: None,  # 测试里退避不真的睡
    )


def test_get_parses_json(tmp_path):
    calls = {}

    def handler(request):
        calls["path"] = request.url.path
        calls["params"] = dict(request.url.params)
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, tmp_path)
    assert client.get("/a", params={"x": "1"}) == {"ok": True}
    assert calls == {"path": "/a", "params": {"x": "1"}}


def test_4xx_raises_http_error(tmp_path):
    client = _client(lambda r: httpx.Response(404, text="nope"), tmp_path)
    with pytest.raises(HttpError) as excinfo:
        client.get("/a")
    assert excinfo.value.status_code == 404


def test_retries_then_succeeds(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, tmp_path, retries=2)
    assert client.get("/a") == {"ok": True}
    assert calls["n"] == 2


def test_retries_exhausted(tmp_path):
    client = _client(lambda r: httpx.Response(500, text="boom"), tmp_path, retries=2)
    with pytest.raises(HttpError, match="重试"):
        client.get("/a")


def test_non_json_raises(tmp_path):
    client = _client(lambda r: httpx.Response(200, text="<html>"), tmp_path)
    with pytest.raises(HttpError, match="JSON"):
        client.get("/a")


def test_post_files_multipart(tmp_path):
    calls = {}

    def handler(request):
        calls["content_type"] = request.headers["content-type"]
        calls["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    client = _client(handler, tmp_path)
    result = client.post("/upload", files={"file": ("a.txt", b"hello")})
    assert result == {"ok": True}
    assert calls["content_type"].startswith("multipart/form-data")
    assert b"hello" in calls["body"]
