import requests
import os
from typing import Optional
from shared.logger import get_logger
from shared.config_loader import get_env_var
import os
import requests
import logging

logger = get_logger("telegram_notifier")

# Hole API-Daten aus Umgebungsvariablen
BOT_TOKEN = get_env_var("BOT_TOKEN", required=False)
CHAT_ID = get_env_var("CHAT_ID", required=False)

def send_telegram_alert(message: str) -> bool:
    token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not token or not chat_id:
        logging.warning("Telegram BOT_TOKEN oder CHAT_ID fehlt – keine Nachricht gesendet.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        if response.status_code == 200:
            logging.info("✅ Telegram-Nachricht erfolgreich gesendet.")
            return True
        else:
            logging.error(f"❌ Telegram-Fehler: Status {response.status_code} – {response.text}")
            return False
    except Exception as e:
        logging.error(f"❌ Telegram-Sendefehler: {e}")
        return False

