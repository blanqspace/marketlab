# shared/core/config_loader.py
from __future__ import annotations
import os
from dotenv import load_dotenv, find_dotenv

REQUIRED_ENV = ["TWS_HOST","TWS_PORT","CLIENT_ID_MAIN","TELEGRAM_ENABLED"]
OPTIONAL_DEFAULTS = {"TELEGRAM_AUTOSTART":"0","TELEGRAM_MOCK":"0"}

_loaded = False

def load_env():
    """Lade .env → OS-ENV → Defaults. Validierung für Pflicht-Variablen.
    Stoppt hart bei Fehler. Loggt nur Token-Längen, nie Klartext.
    """
    import os, json
    from pathlib import Path
    from shared.utils.logger import get_logger
    logger = get_logger("config_loader")

    # .env zuerst laden
    env_path = Path(".env")
    if env_path.exists():
        try:
            load_dotenv(dotenv_path=env_path, override=False)  # OS-ENV dominiert
            logger.info("config_loader: .env loaded")
        except Exception as e:
            logger.warning(f"config_loader: dotenv load failed: {e}")

    env = dict(os.environ)
    # Defaults setzen
    for k, v in OPTIONAL_DEFAULTS.items():
        env.setdefault(k, v)

    # Pflicht prüfen
    missing = [k for k in REQUIRED_ENV if not str(env.get(k, '')).strip()]
    if missing:
        logger.error(f"config_loader: missing required ENV: {missing}")
        raise SystemExit(f"Missing required ENV: {missing}")

    # Telegram-Pflichtfelder nur bei Enabled
    tel_enabled = str(env.get("TELEGRAM_ENABLED","0")) == "1"
    if tel_enabled:
        for k in ["TELEGRAM_BOT_TOKEN","TG_CHAT_CONTROL"]:
            if not str(env.get(k,'')).strip():
                logger.error(f"config_loader: missing Telegram ENV: {k}")
                raise SystemExit(f"Missing Telegram ENV: {k}")
        token = env.get("TELEGRAM_BOT_TOKEN","")
        logger.info(f"config_loader: telegram token length={len(token)}")

    # Numerik prüfen
    try:
        int(env["TWS_PORT"])
        int(env["CLIENT_ID_MAIN"])
    except Exception as e:
        raise SystemExit(f"Invalid numeric ENV: {e}")

    logger.info("config_loader: ENV validated: OK")
    return env

