"""config 模块：XDG 目录、读写、权限。"""

import stat
from pathlib import Path

from shadowbot_cli import config


def test_config_dir_defaults_to_home_config(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert config.config_dir() == Path.home() / ".config" / "shadowbot-cli"


def test_config_dir_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.config_dir() == tmp_path / "shadowbot-cli"


def test_state_dir_defaults(monkeypatch):
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert config.state_dir() == Path.home() / ".local" / "state" / "shadowbot-cli"


def test_state_dir_honors_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert config.state_dir() == tmp_path / "shadowbot-cli"


def test_load_returns_empty_when_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.load() == {}


def test_save_and_load_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    data = {"access_key_id": "id", "access_token": "tok", "expires_at": 123.0}
    config.save(data)
    assert config.load() == data


def test_saved_file_is_0600(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save({"access_token": "tok"})
    mode = stat.S_IMODE(config.config_file().stat().st_mode)
    assert mode == 0o600


def test_load_handles_corrupted_file(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.config_file().parent.mkdir(parents=True, exist_ok=True)
    config.config_file().write_text("{ not valid json")
    assert config.load() == {}
