import requests
import os
from typing import Optional
from shared.logger import get_logger
from shared.config_loader import get_env_var

logger = get_logger("telegram_notifier")

# Hole API-Daten aus Umgebungsvariablen
BOT_TOKEN = get_env_var("BOT_TOKEN", required=False)
CHAT_ID = get_env_var("CHAT_ID", required=False)


def send_telegram_alert(message: str, silent: bool = False) -> Optional[bool]:
    """
    Sendet eine Nachricht an den konfigurierten Telegram-Chat.
    Gibt True bei Erfolg, False bei Fehlern, None wenn Token fehlt.
    """

    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("Telegram BOT_TOKEN oder CHAT_ID fehlt – keine Nachricht gesendet.")
        return None

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logger.info("Telegram-Nachricht erfolgreich gesendet.")
            return True
        else:
            logger.error(f"Telegram-Fehler: {response.status_code} – {response.text}")
            return False
    except requests.RequestException as e:
        if not silent:
            logger.error(f"Telegram-Verbindungsfehler: {e}")
        return False
