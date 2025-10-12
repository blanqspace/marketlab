from __future__ import annotations

from typing import Optional

import os

from src.marketlab.settings import AppSettings, get_settings


def _mask_token(tok: Optional[str]) -> str:
    if not tok:
        return "-"
    try:
        parts = str(tok).split(":", 1)
        if len(parts) == 2 and parts[0].isdigit():
            return f"{parts[0]}:****"
        # fallback: show only first 4 chars
        return (tok[:4] + "****") if tok else "-"
    except Exception:
        return "-"


def load_env(mirror: bool = True, settings: Optional[AppSettings] = None) -> AppSettings:
    """Ensure .env is loaded via Settings() and optionally mirror key values into os.environ.

    - Always returns the resolved AppSettings instance.
    - When mirror=True, writes key settings back to os.environ for legacy code paths:
      IPC_DB, TELEGRAM_*, TG_*, EVENTS_REFRESH_SEC, KPIS_REFRESH_SEC, DASHBOARD_WARN_ONLY.
    - Emits a compact startup summary using print (config.summary).
    """
    s = settings or get_settings()

    if mirror:
        os.environ["IPC_DB"] = s.ipc_db
        # Refresh cadences + dashboard warning filter
        os.environ["EVENTS_REFRESH_SEC"] = str(int(s.events_refresh_sec))
        os.environ["KPIS_REFRESH_SEC"] = str(int(s.kpis_refresh_sec))
        os.environ["DASHBOARD_WARN_ONLY"] = str(int(s.dashboard_warn_only))
        # Telegram
        os.environ["TELEGRAM_ENABLED"] = "1" if s.telegram.enabled else "0"
        os.environ["TELEGRAM_MOCK"] = "1" if s.telegram.mock else "0"
        if s.telegram.bot_token and s.telegram.bot_token.get_secret_value():
            os.environ["TELEGRAM_BOT_TOKEN"] = s.telegram.bot_token.get_secret_value()
        if s.telegram.chat_control is not None:
            os.environ["TG_CHAT_CONTROL"] = str(int(s.telegram.chat_control))
        if s.telegram.allowlist:
            os.environ["TG_ALLOWLIST"] = ",".join(str(int(x)) for x in s.telegram.allowlist)
        os.environ["TELEGRAM_TIMEOUT_SEC"] = str(int(s.telegram.timeout_sec))
        os.environ["TELEGRAM_DEBUG"] = "1" if s.telegram.debug else "0"

    # Startup summary (non-sensitive)
    token_show = _mask_token(s.telegram.bot_token.get_secret_value() if s.telegram.bot_token else None)
    allow_cnt = len(s.telegram.allowlist or [])
    brand = s.app_brand if hasattr(s, "app_brand") else "MarketLab"
    mode = s.env_mode if hasattr(s, "env_mode") else "DEV"
    db_name = os.path.basename(s.ipc_db)
    print(
        f"config.summary brand={brand} mode={mode} db={db_name} tg.enabled={'1' if s.telegram.enabled else '0'} tg.mock={'1' if s.telegram.mock else '0'} tg.chat={s.telegram.chat_control or '-'} tg.allow={allow_cnt} tg.token={token_show}"
    )

    return s

