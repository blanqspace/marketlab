import os
import signal
import psutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from shared.logger import get_logger

LOCK_DIR = Path("runtime/locks")
LOCK_DIR.mkdir(parents=True, exist_ok=True)

logger = get_logger("lock_tools")


def get_lock_path(name: str) -> Path:
    return LOCK_DIR / f"{name}.lock"


def create_lock(name: str) -> bool:
    """
    Erstellt Lock-Datei mit aktuellem PID. Gibt False zurück, wenn bereits aktiv.
    """
    path = get_lock_path(name)
    if path.exists():
        pid = read_pid(path)
        if pid and is_process_alive(pid):
            logger.warning(f"Lock '{name}' bereits aktiv (PID {pid}) – Abbruch.")
            return False
        else:
            logger.warning(f"Lock '{name}' ist verwaist (PID {pid}) – wird ersetzt.")
            remove_lock(name)

    with open(path, "w") as f:
        f.write(f"{os.getpid()},{datetime.now().isoformat()}")
    logger.info(f"Lock erstellt: {path} (PID {os.getpid()})")
    return True


def read_pid(path: Path) -> Optional[int]:
    try:
        content = path.read_text()
        pid_str = content.strip().split(",")[0]
        return int(pid_str)
    except Exception:
        return None


def is_process_alive(pid: int) -> bool:
    try:
        p = psutil.Process(pid)
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def remove_lock(name: str) -> None:
    path = get_lock_path(name)
    if path.exists():
        path.unlink()
        logger.info(f"Lock entfernt: {path}")
