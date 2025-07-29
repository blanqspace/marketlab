import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional

from shared.logger import get_logger

logger = get_logger("thread_tools")

# Globale Übersicht über aktive Threads
THREAD_STATUS: Dict[str, Dict[str, any]] = {}


def start_named_thread(
    name: str,
    target: Callable,
    args: tuple = (),
    daemon: bool = True,
    track: bool = True,
) -> threading.Thread:
    """
    Startet einen benannten Thread und speichert Statusdaten, wenn track=True.
    """

    def wrapped_target():
        try:
            logger.info(f"🟢 Thread '{name}' gestartet")
            if track:
                THREAD_STATUS[name] = {
                    "status": "running",
                    "start_time": datetime.now().isoformat(),
                    "thread": threading.current_thread(),
                }

            target(*args)

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


def get_thread_status() -> Dict[str, Dict[str, any]]:
    """
    Gibt aktuelle Thread-Übersicht zurück.
    """
    return THREAD_STATUS
