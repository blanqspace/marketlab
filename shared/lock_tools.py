import os
import signal
import psutil
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from shared.logger import get_logger

LOCK_DIR = Path("runtime/locks")
LOCK_DIR.mkdir(parents=True, exist_ok=True)

logger = get_logger("lock_tools")


def get_lock_path(name: str) -> Path:
    return LOCK_DIR / f"{name}.lock"


def create_lock(name: str, note: Optional[str] = None) -> bool:
    """
    Erstellt Lock-Datei mit PID und optionaler Notiz.
    Gibt False zurück, wenn Lock aktiv ist.
    """
    path = get_lock_path(name)

    if path.exists():
        pid = read_pid(path)
        if pid and is_process_alive(pid):
            logger.warning(f"⛔ Lock '{name}' aktiv (PID {pid}) – Start abgebrochen.")
            return False
        else:
            logger.info(f"♻️ Lock '{name}' ist verwaist (PID {pid}) – wird ersetzt.")
            remove_lock(name)

    lock_data = {
        "pid": os.getpid(),
        "timestamp": datetime.now().isoformat(),
        "note": note or ""
    }

    try:
        path.write_text(json.dumps(lock_data, indent=2))
        logger.info(f"🔐 Lock erstellt: {path} (PID {lock_data['pid']})")
        return True
    except Exception as e:
        logger.error(f"❌ Fehler beim Erstellen von Lock {name}: {e}")
        return False


def read_pid(path: Path) -> Optional[int]:
    try:
        data = json.loads(path.read_text())
        return int(data.get("pid", 0))
    except Exception as e:
        logger.warning(f"⚠️ Lock-Datei beschädigt: {path} – {e}")
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
        logger.info(f"🗑️ Lock entfernt: {path}")


def get_active_locks() -> List[Dict[str, Any]]:
    """
    Gibt Liste aller vorhandenen Locks mit PID, Status, Note.
    """
    locks: List[Dict[str, Any]] = []

    for path in LOCK_DIR.glob("*.lock"):
        try:
            data = json.loads(path.read_text())
            pid = int(data.get("pid", 0))
            status = "aktiv" if is_process_alive(pid) else "verwaist"
            locks.append({
                "name": path.stem,
                "pid": pid,
                "status": status,
                "timestamp": data.get("timestamp"),
                "note": data.get("note", "")
            })
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Lesen von Lock {path}: {e}")

    return locks
