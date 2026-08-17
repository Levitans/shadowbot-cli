""".env 加载：验证 cli.main() 使用的 find_dotenv(usecwd=True) 行为。"""

import os

from dotenv import find_dotenv, load_dotenv


def test_load_dotenv_from_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "SHADOWBOT_ACCESS_KEY_ID=from-dotenv\nSHADOWBOT_ACCESS_KEY_SECRET=from-dotenv-secret\n",
        encoding="utf-8",
    )
    load_dotenv(find_dotenv(usecwd=True))
    try:
        assert os.environ["SHADOWBOT_ACCESS_KEY_ID"] == "from-dotenv"
        assert os.environ["SHADOWBOT_ACCESS_KEY_SECRET"] == "from-dotenv-secret"
    finally:
        os.environ.pop("SHADOWBOT_ACCESS_KEY_ID", None)
        os.environ.pop("SHADOWBOT_ACCESS_KEY_SECRET", None)


def test_real_env_var_takes_precedence_over_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SHADOWBOT_ACCESS_KEY_ID", "from-shell")
    (tmp_path / ".env").write_text("SHADOWBOT_ACCESS_KEY_ID=from-dotenv\n", encoding="utf-8")
    load_dotenv(find_dotenv(usecwd=True))
    try:
        assert os.environ["SHADOWBOT_ACCESS_KEY_ID"] == "from-shell"
    finally:
        os.environ.pop("SHADOWBOT_ACCESS_KEY_ID", None)
