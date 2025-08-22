import requests
import os
import time
from typing import Optional
from shared.logger import get_logger
from shared.config_loader import get_env_var

logger = get_logger("telegram_notifier")

# Nur 1× laden – nicht doppelt aufrufen
BOT_TOKEN = get_env_var("BOT_TOKEN", required=False)
CHAT_ID = get_env_var("CHAT_ID", required=False)


def _send_message(payload: dict, retries: int = 2, delay: float = 1.5) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram BOT_TOKEN oder CHAT_ID fehlt – keine Nachricht gesendet.")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    for attempt in range(retries + 1):
        try:
            response = requests.post(url, json=payload, timeout=5)
            if response.status_code == 200:
                logger.info("📬 Telegram-Nachricht gesendet.")
                return True
            else:
                logger.error(f"❌ Telegram-Fehler (Versuch {attempt + 1}): Status {response.status_code} – {response.text}")
        except Exception as e:
            logger.warning(f"⚠️ Telegram-Sendefehler (Versuch {attempt + 1}): {e}")

        if attempt < retries:
            time.sleep(delay)

    return False


def send_telegram_alert(message: str, type: str = "alert") -> bool:
    """
    Sendet eine Telegram-Nachricht im Markdown-Format.
    Typen:
    - alert (❌)
    - warning (⚠️)
    - info (ℹ️)
    """
    prefix = {
        "alert": "❌ *Fehler:*",
        "warning": "⚠️ *Warnung:*",
        "info": "ℹ️ *Info:*"
    }.get(type, "")

    payload = {
        "chat_id": CHAT_ID,
        "text": f"{prefix}\n{message}",
        "parse_mode": "Markdown"
    }

    return _send_message(payload)
