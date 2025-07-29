# 🗂️ Projektdateien (gezielte Übersicht)


## `..\main_runner.py`
- 📄 Zeilen: 75, 🧾 Kommentare: 1, ⚙️ Funktionen: 4

```python
from shared.logger import get_logger
from shared.config_loader import load_env, get_env_var, load_json_config
from shared.lock_tools import create_lock, remove_lock
from shared.telegram_notifier import send_telegram_alert
from shared.thread_tools import start_named_thread
from shared.file_utils import file_exists
from pathlib import Path
import time
import importlib

logger = get_logger("main_runner", log_to_console=True)

def cleanup_old_locks():
    """
    Entfernt alte/verwaiste Lock-Dateien aus runtime/locks/
    """
    lock_dir = Path("runtime/locks")
    if not lock_dir.exists():
        return
    for lockfile in lock_dir.glob("*.lock"):
        lockfile.unlink()
        logger.info(f"Alte Lock-Datei entfernt: {lockfile}")


def check_previous_errors():
    """
    Prüft letzte Fehlerlogs – optional erweiterbar für kritische Warnungen.
    """
    error_log_dir = Path("logs/errors")
    latest = max(error_log_dir.glob("*.log"), default=None, key=lambda f: f.stat().st_mtime) if error_log_dir.exists() else None
    if latest and latest.stat().st_size > 0:
        logger.warning(f"⚠️ Letzte Fehlerdatei enthält Einträge: {latest}")
        send_telegram_alert(f"⚠️ Fehler beim letzten Start gefunden: {latest.name}")


def start_activated_modules():
    config = load_json_config("config/startup.json")
    modules = config.get("modules", {})

    for modulename, active in modules.items():
        if active:
            try:
                logger.info(f"Starte Modul: {modulename} ✅")
                import importlib
                module_path = f"modules.{modulename}.main"
                module = importlib.import_module(module_path)
                module.run()
            except Exception as e:
                logger.error(f"❌ Fehler beim Start von Modul {modulename}: {e}")
                send_telegram_alert(f"❌ Fehler beim Start von Modul *{modulename}*:\n{e}")
        else:
            logger.info(f"Modul deaktiviert: {modulename}")

def main():
    logger.info("🚀 Starte System: main_runner")
    
    load_env()
    
    if not create_lock("main_runner"):
        logger.error("main_runner bereits aktiv. Abbruch.")
        return

    try:
        cleanup_old_locks()
        check_previous_errors()
        start_activated_modules()
    except Exception as e:
        logger.exception(f"Fehler beim Start: {e}")
        send_telegram_alert(f"❌ Hauptstartfehler: {e}")
    finally:
        # NICHT sofort Lock entfernen → bleibt aktiv, während Threads laufen
        logger.info("Systemstart abgeschlossen.")

if __name__ == "__main__":
    main()
```

modules\data_fetcher\main.py`
- 📄 Zeilen: 152, 🧾 Kommentare: 1, ⚙️ Funktionen: 6

```python
import csv
import io
import json
import time
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests

from shared.logger import get_logger
from shared.config_loader import load_env, get_env_var, load_json_config
from shared.file_utils import file_exists
from shared.telegram_notifier import send_telegram_alert

logger = get_logger("data_fetcher", log_to_console=False)
FAILED_JSON = Path("logs/errors/failed_requests.json")
FAILED_JSON.parent.mkdir(parents=True, exist_ok=True)


def _append_failed(entry: Dict[str, Any]) -> None:
    data: List[Dict[str, Any]] = []
    if file_exists(FAILED_JSON):
        try:
            data = json.loads(FAILED_JSON.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data.append(entry)
    FAILED_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _fetch_http(url: str, headers: Dict[str, str], timeout: float = 10.0) -> Optional[str]:
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            logger.error(f"HTTP {resp.status_code} für {url}")
            _append_failed({"url": url, "status": resp.status_code, "reason": resp.text[:200]})
            return None
        return resp.text
    except requests.Timeout:
        logger.error(f"Timeout > {timeout}s bei {url}")
        _append_failed({"url": url, "error": f"timeout>{timeout}s"})
        return None
    except requests.RequestException as e:
        logger.error(f"RequestException bei {url}: {e}")
        _append_failed({"url": url, "error": str(e)})
        return None


def _fetch_file(file_url: str) -> Optional[str]:
    path = file_url.replace("file://", "")
    p = Path(path)
    if not p.exists():
        logger.error(f"Lokale Datei nicht gefunden: {p}")
        _append_failed({"url": file_url, "error": "file_not_found"})
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Fehler beim Lesen lokaler Datei {p}: {e}")
        _append_failed({"url": file_url, "error": str(e)})
        return None


def _count_csv_rows(text: str) -> int:
    try:
        reader = csv.reader(io.StringIO(text))
        return sum(1 for _ in reader)
    except Exception:
        return len([ln for ln in text.splitlines() if ln.strip()])


def _process_task(task: Dict[str, Any], api_key: Optional[str]) -> bool:
    name = task.get("name", "unnamed_task")
    symbol = task.get("symbol", "UNKNOWN")
    url = task.get("url")
    active = task.get("active", False)

    if not active:
        logger.info(f"Task deaktiviert: {name}")
        return True
    if not url:
        logger.error(f"Task {name}: Keine URL angegeben.")
        _append_failed({"task": name, "symbol": symbol, "error": "missing_url"})
        send_telegram_alert(f"❌ Fehler im Task *{name}*: Keine URL")
        return False

    logger.info(f"Starte Abruf: {name} ({symbol}) → {url}")

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    if url.startswith("file://"):
        content = _fetch_file(url)
    else:
        content = _fetch_http(url, headers=headers)

    if content is None:
        logger.error(f"Abruf fehlgeschlagen: {name} ({symbol})")
        send_telegram_alert(f"❌ Abruf fehlgeschlagen: *{symbol}*")
        return False

    size_bytes = len(content.encode("utf-8"))
    if size_bytes < 500:
        logger.warning(f"{name}: Antwort sehr klein ({size_bytes} Bytes) – Verdacht auf unvollständige Daten.")

    rows = _count_csv_rows(content)
    logger.info(f"{name}: {rows} Datenzeilen empfangen.")

    if task.get("save", False):
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        path = data_dir / f"{symbol}.csv"
        path.write_text(content, encoding="utf-8")
        logger.info(f"{name}: Daten gespeichert unter {path}")

    logger.info(f"Abschluss: {name} ({symbol})")
    return True


def run():
    logger.info("🟢 Data-Fetcher gestartet")

    try:
        load_env()
        api_key = get_env_var("API_KEY", required=False)
        tasks_cfg = load_json_config("config/tasks.json", fallback=[])

        if not isinstance(tasks_cfg, list):
            logger.error("config/tasks.json: Erwartet Liste von Tasks.")
            return

        success_count = 0
        total_count = len(tasks_cfg)

        for task in tasks_cfg:
            try:
                if _process_task(task, api_key):
                    success_count += 1
            except Exception as e:
                logger.error(f"❌ Task fehlgeschlagen: {task.get('name')} → {e}")
                logger.debug(traceback.format_exc())

        logger.info(f"✅ Data-Fetcher abgeschlossen: {success_count}/{total_count} erfolgreich")

    except Exception as e:
        logger.error(f"❌ Hauptfehler im Data-Fetcher: {e}")
        logger.debug(traceback.format_exc())


# für Direktstarttest
if __name__ == "__main__":
    run()
```

## `..\modules\health\main.py`
- 📄 Zeilen: 60, 🧾 Kommentare: 0, ⚙️ Funktionen: 4

```python
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
```


## `..\shared\config_loader.py`
- 📄 Zeilen: 51, 🧾 Kommentare: 0, ⚙️ Funktionen: 3

```python
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

from shared.logger import get_logger

logger = get_logger("config_loader")


def load_env(env_path: Optional[str] = ".env") -> None:
    """
    Lädt Umgebungsvariablen aus .env-Datei.
    """
    env_file = Path(env_path)
    if not env_file.exists():
        logger.warning(f".env-Datei nicht gefunden: {env_path}")
        return

    load_dotenv(dotenv_path=env_file)
    logger.info(f".env geladen: {env_path}")


def get_env_var(key: str, required: bool = True) -> Optional[str]:
    """
    Gibt Umgebungsvariable zurück. Loggt Warnung, wenn nicht vorhanden.
    """
    value = os.getenv(key)
    if required and not value:
        logger.warning(f"Umgebungsvariable '{key}' fehlt!")
    return value


def load_json_config(path: str, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Lädt eine JSON-Konfigurationsdatei. Gibt Fallback zurück bei Fehlern.
    """
    config_path = Path(path)
    if not config_path.exists():
        logger.error(f"Konfigurationsdatei nicht gefunden: {path}")
        return fallback or {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Konfiguration geladen: {path}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Ungültige JSON-Struktur in {path}: {e}")
        return fallback or {}
```

## `..\shared\file_utils.py`
- 📄 Zeilen: 64, 🧾 Kommentare: 0, ⚙️ Funktionen: 6

```python
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from shared.logger import get_logger

logger = get_logger("file_utils")


def ensure_directory(path: Union[str, Path]) -> None:
    """
    Erstellt den Ordner, falls er nicht existiert.
    """
    Path(path).mkdir(parents=True, exist_ok=True)
    logger.debug(f"Verzeichnis sichergestellt: {path}")


def safe_write_text(path: Union[str, Path], content: str) -> None:
    """
    Schreibt Textinhalt sicher in eine Datei.
    """
    try:
        Path(path).write_text(content, encoding="utf-8")
        logger.debug(f"Text geschrieben nach: {path}")
    except Exception as e:
        logger.error(f"Fehler beim Schreiben nach {path}: {e}")


def safe_read_text(path: Union[str, Path]) -> Optional[str]:
    """
    Liest Textinhalt aus einer Datei, wenn vorhanden.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Lesefehler bei {path}: {e}")
        return None


def load_json_file(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    Lädt eine JSON-Datei als Dict.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Fehler beim Laden von JSON {path}: {e}")
        return None


def write_json_file(path: Union[str, Path], data: Dict[str, Any]) -> None:
    """
    Speichert ein Dict als JSON-Datei.
    """
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        Path(path).write_text(content, encoding="utf-8")
        logger.debug(f"JSON gespeichert nach: {path}")
    except Exception as e:
        logger.error(f"Fehler beim Speichern von JSON {path}: {e}")


def file_exists(path: Union[str, Path]) -> bool:
    return Path(path).exists()
```

## `..\shared\ibkr_client.py`
- 📄 Zeilen: 47, 🧾 Kommentare: 0, ⚙️ Funktionen: 5

```python
import os
import asyncio
from ib_insync import IB
from shared.logger import get_logger
from shared.config_loader import get_env_var

logger = get_logger("ibkr_client")

class IBKRClient:
    def __init__(self, client_id: int = None, module: str = None):
        self.client_id = client_id or self._get_client_id_from_env(module)
        self.host = get_env_var("TWS_HOST", required=False) or "127.0.0.1"
        self.port = int(get_env_var("TWS_PORT", required=False) or 4002)
        self.ib = IB()

    def _get_client_id_from_env(self, module: str = None) -> int:
        if module:
            env_var = f"CLIENT_ID_{module.upper()}"
            return int(os.getenv(env_var, os.getenv("CLIENT_ID_DEFAULT", 127)))
        return int(os.getenv("CLIENT_ID_DEFAULT", 127))

    def connect(self) -> IB:
        try:
            try:
                asyncio.get_event_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"✅ Verbunden mit IBKR @ {self.host}:{self.port} (Client ID: {self.client_id})")
            return self.ib
        except Exception as e:
            logger.error(f"❌ Verbindung zu IBKR fehlgeschlagen: {e}")
            raise ConnectionError(f"IBKR-Verbindung fehlgeschlagen: {e}")

    def disconnect(self):
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info(f"✅ Verbindung zu IBKR getrennt (Client ID: {self.client_id})")
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Trennen von IBKR: {e}")
        finally:
            self.ib = None

    def is_connected(self) -> bool:
        return self.ib.isConnected()
```

## `..\shared\lock_tools.py`
- 📄 Zeilen: 61, 🧾 Kommentare: 0, ⚙️ Funktionen: 5

```python
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
```

## `..\shared\logger.py`
- 📄 Zeilen: 52, 🧾 Kommentare: 6, ⚙️ Funktionen: 1

```python
import logging
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

LOG_DIR = Path("logs")

def get_logger(modulname: str, log_to_console: bool = False) -> logging.Logger:
    """
    Erstellt einen Logger mit täglicher Rotation.
    Log-Dateien werden gespeichert unter: logs/<modulname>/YYYY-MM-DD.log
    """

    # Logger einmalig erzeugen
    logger = logging.getLogger(modulname)
    if logger.handlers:
        return logger  # Logger bereits initialisiert

    logger.setLevel(logging.DEBUG)

    # Logverzeichnis erstellen, z. B. logs/data_fetcher/
    log_subdir = LOG_DIR / modulname
    log_subdir.mkdir(parents=True, exist_ok=True)

    # Dateiname nach heutigem Datum
    logfile_path = log_subdir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    # FileHandler mit täglicher Rotation (behält 7 Tage)
    file_handler = TimedRotatingFileHandler(
        filename=logfile_path,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        delay=False
    )

    # Formatierung: Zeit, Level, Nachricht
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Optional: Konsolen-Ausgabe
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
```

## `..\shared\telegram_notifier.py`
- 📄 Zeilen: 42, 🧾 Kommentare: 1, ⚙️ Funktionen: 1

```python
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

```

## `..\shared\thread_tools.py`
- 📄 Zeilen: 57, 🧾 Kommentare: 1, ⚙️ Funktionen: 3

```python
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
```