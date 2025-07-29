import socket
import requests
import logging
import time

from shared.config_loader import load_env
from shared.logger import get_logger
from shared.telegram_notifier import send_telegram_alert
import json

load_env()  # ⬅️ WICHTIG: direkt beim Start

logger = get_logger("health", log_to_console=False)

def check_tcp(name, host, port):
    try:
        with socket.create_connection((host, port), timeout=5):
            logger.info(f"✅ {name} erreichbar")
            return True
    except Exception:
        logger.error(f"❌ {name} NICHT erreichbar!")
        send_telegram_alert(f"❌ {name} nicht erreichbar (TCP {host}:{port})")  # ✅ Telegram bei Ausfall
        return False

def check_http(name, url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            logger.info(f"✅ {name} erreichbar")
            return True
        else:
            logger.error(f"❌ {name} NICHT erreichbar! Status {response.status_code}")
            send_telegram_alert(f"❌ {name} Down! Status: {response.status_code}")
            return False
    except Exception:
        logger.error(f"❌ {name} NICHT erreichbar!")
        send_telegram_alert(f"❌ {name} nicht erreichbar (HTTP {url})")  # ✅ Telegram bei Ausfall
        return False
def load_json_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def run():
    logger.info("🔍 Starte Healthcheck...")

    targets = load_json_config("config/healthcheck_config.json")
    success_count = 0
    success_count = 0

    for target in targets:
        name = target["name"]
        if target["type"] == "tcp":
            success_count += check_tcp(name, target["host"], target["port"])
        elif target["type"] == "http":
            success_count += check_http(name, target["url"])

    logger.info(f"✅ Healthcheck abgeschlossen: {success_count}/{len(targets)} Systeme erreichbar")

if __name__ == "__main__":
    run()
