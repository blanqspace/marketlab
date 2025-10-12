from __future__ import annotations

import importlib
import os
from types import SimpleNamespace


class _DummySecret:
    def __init__(self, v: str):
        self._v = v

    def get_secret_value(self) -> str:
        return self._v


def test_bootstrap_load_env_mirrors_keys(monkeypatch):
    # Prepare dummy settings object
    telegram = SimpleNamespace(
        enabled=True,
        mock=False,
        bot_token=_DummySecret("1234:xyzxxxxxxxxxxxxxxxxxxxxx"),
        chat_control=-100123,
        timeout_sec=30,
        debug=True,
        allowlist=[1, 2, 3],
    )
    app = SimpleNamespace(
        env_mode="DEV",
        app_brand="MarketLab",
        ipc_db="runtime/ctl.db",
        events_refresh_sec=7,
        kpis_refresh_sec=17,
        dashboard_warn_only=1,
        telegram=telegram,
    )

    # Patch get_settings used by bootstrap
    import src.marketlab.settings as settings_mod
    monkeypatch.setattr(settings_mod, "get_settings", lambda: app, raising=True)

    import src.marketlab.bootstrap.env as bootstrap
    importlib.reload(bootstrap)

    # Call loader
    s = bootstrap.load_env(mirror=True)
    assert s is app

    # Mirrors
    assert os.getenv("IPC_DB") == "runtime/ctl.db"
    assert os.getenv("EVENTS_REFRESH_SEC") == "7"
    assert os.getenv("KPIS_REFRESH_SEC") == "17"
    assert os.getenv("DASHBOARD_WARN_ONLY") == "1"
    assert os.getenv("TELEGRAM_ENABLED") == "1"
    assert os.getenv("TELEGRAM_MOCK") == "0"
    assert os.getenv("TELEGRAM_BOT_TOKEN", "").startswith("1234:")
    assert os.getenv("TG_CHAT_CONTROL") == "-100123"
    assert os.getenv("TG_ALLOWLIST") == "1,2,3"
    assert os.getenv("TELEGRAM_TIMEOUT_SEC") == "30"
    assert os.getenv("TELEGRAM_DEBUG") == "1"

