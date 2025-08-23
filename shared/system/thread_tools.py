import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional, Any

from shared.utils.logger import get_logger

logger = get_logger("thread_tools")

# Globale Übersicht über aktive Threads
THREAD_STATUS: Dict[str, Dict[str, Any]] = {}

# Globale Stop-Signale
STOP_FLAGS: Dict[str, threading.Event] = {}


def start_named_thread(
    name: str,
    target: Callable[[threading.Event], None],
    args: tuple = (),
    daemon: bool = True,
    track: bool = True
) -> threading.Thread:
    """
    Startet einen benannten Thread und speichert Statusdaten, wenn track=True.
    Übergibt ein threading.Event (stop_flag) als erstes Argument.
    """

    stop_flag = threading.Event()
    STOP_FLAGS[name] = stop_flag

    def wrapped_target():
        try:
            logger.info(f"🟢 Thread '{name}' gestartet")

            if track:
                THREAD_STATUS[name] = {
                    "status": "running",
                    "start_time": datetime.now().isoformat(),
                    "thread": threading.current_thread(),
                    "starts": THREAD_STATUS.get(name, {}).get("starts", 0) + 1,
                }

            target(stop_flag, *args)

            if track:
                THREAD_STATUS[name]["status"] = "finished"
                THREAD_STATUS[name]["end_time"] = datetime.now().isoformat()

            logger.info(f"✅ Thread '{name}' abgeschlossen")
        except Exception as e:
            logger.exception(f"❌ Thread '{name}' abgestürzt: {e}")
            if track:
                THREAD_STATUS[name]["status"] = "error"
                THREAD_STATUS[name]["error"] = str(e)

    thread = threading.Thread(target=wrapped_target, name=name, daemon=daemon)
    thread.start()
    return thread


def stop_thread(name: str) -> bool:
    """
    Setzt das Stop-Flag für einen Thread (wenn vorhanden).
    """
    if name in STOP_FLAGS:
        STOP_FLAGS[name].set()
        logger.info(f"🛑 Stop-Signal für Thread '{name}' gesetzt.")
        return True
    else:
        logger.warning(f"⚠️ Kein Stop-Flag für Thread '{name}' gefunden.")
        return False


def get_thread_status() -> Dict[str, Dict[str, Any]]:
    """
    Gibt aktuelle Thread-Übersicht zurück.
    """
    return THREAD_STATUS


def get_thread_status_json() -> str:
    """
    Gibt Thread-Status als JSON-String zurück (z. B. für Telegram oder Monitoring).
    """
    import json
    try:
        export = {
            name: {
                "status": data.get("status"),
                "start_time": data.get("start_time"),
                "end_time": data.get("end_time", "-"),
                "starts": data.get("starts", 1),
            }
            for name, data in THREAD_STATUS.items()
        }
        return json.dumps(export, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"❌ Fehler beim Serialisieren von Thread-Status: {e}")
        return "{}"
