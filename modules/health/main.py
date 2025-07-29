import socket
import requests
import time
from shared.logger import get_logger
from shared.config_loader import load_json_config
from shared.telegram_notifier import send_telegram_alert

logger = get_logger("health")

def check_tcp(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except Exception:
        return False

def check_http(url: str, timeout: float = 5.0) -> bool:
    try:
        response = requests.get(url, timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False

def run():
    logger.info("🔍 Starte Healthcheck...")

    config = load_json_config("config/healthcheck_config.json")
    failed = []

    for item in config:
        name = item.get("name")
        check_type = item.get("type")

        if check_type == "tcp":
            host = item.get("host")
            port = item.get("port")
            result = check_tcp(host, port)
        elif check_type == "http":
            url = item.get("url")
            result = check_http(url)
        else:
            logger.warning(f"Unbekannter Check-Typ: {check_type}")
            continue

        if result:
            logger.info(f"✅ {name} erreichbar")
        else:
            logger.error(f"❌ {name} NICHT erreichbar!")
            failed.append(name)

    # Telegram-Benachrichtigung bei Ausfall
    if failed:
        msg = "🚨 *Healthcheck-Fehler*\n" + "\n".join([f"– {x}" for x in failed])
        send_telegram_alert(msg)

    logger.info("✅ Healthcheck abgeschlossen.")


if __name__ == "__main__":
    run()
