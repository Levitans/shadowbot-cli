"""app_cache：读写往返、TTL 过期、损坏兜底。"""

import json
import time

from shadowbot_cli import app_cache


def test_load_empty_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert app_cache.load() == {}


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    data = {"a1": {"version": "3", "instruction": "<p>i</p>", "flowParams": [], "cached_at": time.time()}}
    app_cache.save(data)
    assert app_cache.load() == data


def test_load_drops_expired(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    now = time.time()
    data = {
        "fresh": {"version": "3", "cached_at": now},
        "stale": {"version": "3", "cached_at": now - app_cache.CACHE_TTL - 10},
    }
    app_cache.save(data)
    loaded = app_cache.load()
    assert "fresh" in loaded
    assert "stale" not in loaded


def test_load_drops_invalid_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    app_cache.save({
        "bad": "not-a-dict",
        "good": {"version": "3", "cached_at": time.time()},
    })
    loaded = app_cache.load()
    assert "bad" not in loaded
    assert "good" in loaded


def test_corrupt_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    path = app_cache._path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert app_cache.load() == {}


# --- 列表缓存 ---
def test_list_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    items = [{"appId": "a1", "version": "3"}]
    app_cache.save_list("q", items)
    assert app_cache.load_list("q") == items


def test_list_cache_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert app_cache.load_list("nope") is None


def test_list_cache_expired_returns_none(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    app_cache.save_list("q", [{"appId": "a1"}])
    path = app_cache._list_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    data["q"]["cached_at"] = time.time() - app_cache.LIST_CACHE_TTL - 10
    path.write_text(json.dumps(data), encoding="utf-8")
    assert app_cache.load_list("q") is None


def test_list_cache_distinct_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    app_cache.save_list("q1", [{"appId": "a1"}])
    app_cache.save_list("q2", [{"appId": "a2"}])
    assert app_cache.load_list("q1") == [{"appId": "a1"}]
    assert app_cache.load_list("q2") == [{"appId": "a2"}]
