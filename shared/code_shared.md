# 🗂️ Projektdateien (gezielte Übersicht)


## `..\shared\client_registry.py`
- 📄 Zeilen: 95, 🧾 Kommentare: 0, ⚙️ Funktionen: 10

```python
import os
import json
from pathlib import Path
from typing import Union, List, Optional, Dict

from shared.logger import get_logger
from shared.file_utils import load_json_file

logger = get_logger("client_registry")

DEFAULT_ID_MAP = {
    "data_manager": 101,
    "order_executor": 102,
    "realtime": 103,
    "account": 104,
    "symbol_fetcher_pool": list(range(105, 120)),
    "strategy_lab": 121
}

CONFIG_PATH = Path("config/client_ids.json")


class ClientRegistry:
    def __init__(self):
        self.id_map = self._load_ids()
        self.status_map: Dict[int, Dict[str, Union[str, bool]]] = {}

    def _load_ids(self) -> Dict[str, Union[int, List[int]]]:
        if CONFIG_PATH.exists():
            data = load_json_file(CONFIG_PATH, fallback=DEFAULT_ID_MAP, expected_type=dict)
            logger.info("✅ client_ids.json geladen")
            return data
        else:
            logger.warning("⚠️ client_ids.json nicht gefunden – verwende Default-Zuordnung")
            return DEFAULT_ID_MAP.copy()

    def get_client_id(self, module: str) -> Optional[int]:
        entry = self.id_map.get(module)
        if isinstance(entry, int):
            return entry
        elif isinstance(entry, list) and entry:
            return entry[0]
        logger.error(f"❌ Keine Client-ID für Modul '{module}' gefunden")
        return None

    def get_pool(self, key: str) -> List[int]:
        pool = self.id_map.get(key, [])
        if isinstance(pool, list):
            return pool
        return []

    def get_all_ids(self) -> List[int]:
        ids = []
        for val in self.id_map.values():
            if isinstance(val, int):
                ids.append(val)
            elif isinstance(val, list):
                ids.extend(val)
        return sorted(set(ids))

    def get_free_id_from_pool(self, pool_name: str) -> Optional[int]:
        pool = self.get_pool(pool_name)
        active_ids = set(self.status_map.keys())
        for cid in pool:
            if cid not in active_ids:
                logger.info(f"🟢 Freie Client-ID gefunden: {cid} aus Pool '{pool_name}'")
                return cid
        logger.warning(f"⚠️ Keine freie ID mehr im Pool '{pool_name}'")
        return None

    def assign_next_free_id(self, task_name: str, pool_name: str = "symbol_fetcher_pool") -> Optional[int]:
        cid = self.get_free_id_from_pool(pool_name)
        if cid is not None:
            self.set_status(cid, task_name, connected=False)
        return cid

    def set_status(self, client_id: int, task: str, connected: bool) -> None:
        self.status_map[client_id] = {
            "task": task,
            "connected": connected
        }

    def update_connected(self, client_id: int, connected: bool = True):
        if client_id in self.status_map:
            self.status_map[client_id]["connected"] = connected

    def get_status_report(self) -> str:
        lines = ["🧩 Client-ID-Status:"]
        for cid, info in sorted(self.status_map.items()):
            lines.append(f"  {cid}: {info.get('task')} – {'✅ verbunden' if info.get('connected') else '⛔️ getrennt'}")
        return "\n".join(lines)


registry = ClientRegistry()
registry.set_status(199, task="symbol_probe", connected=False)
```

## `..\shared\config_loader.py`
- 📄 Zeilen: 78, 🧾 Kommentare: 0, ⚙️ Funktionen: 4

```python
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional, Type, Union
from dotenv import load_dotenv
from shared.logger import get_logger

logger = get_logger("config_loader")


def _resolve_env_path(base_path: Optional[str] = ".env") -> Path:
    """
    Ermittelt den Pfad zur .env-Datei anhand von ENV_MODE (z. B. .env.dev)
    """
    env_mode = os.getenv("ENV_MODE", "").strip().lower()

    if env_mode:
        candidate = f"{base_path}.{env_mode}"
        candidate_path = Path(candidate)
        if candidate_path.exists():
            logger.info(f".env-Umgebung erkannt: {env_mode} → {candidate}")
            return candidate_path

    return Path(base_path)


def load_env(env_path: Optional[str] = ".env") -> None:
    """
    Lädt Umgebungsvariablen aus .env-Datei, unterstützt ENV_MODE
    """
    path = _resolve_env_path(env_path)

    if not path.exists():
        logger.warning(f".env-Datei nicht gefunden: {path}")
        return

    load_dotenv(dotenv_path=path)
    logger.info(f".env geladen: {path}")


def get_env_var(key: str, required: bool = True) -> Optional[str]:
    """
    Gibt Umgebungsvariable zurück. Loggt Warnung, wenn nicht vorhanden.
    """
    value = os.getenv(key)
    if required and not value:
        logger.warning(f"Umgebungsvariable '{key}' fehlt!")
    return value


def load_json_config(
    path: str,
    fallback: Optional[Any] = None,
    expected_type: Optional[Type] = dict
) -> Any:
    """
    Lädt eine JSON-Konfigurationsdatei. Prüft optional den Typ.
    """
    config_path = Path(path)
    if not config_path.exists():
        logger.error(f"⚠️ Konfigurationsdatei nicht gefunden: {path}")
        return fallback or ({} if expected_type == dict else [])

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

            if expected_type and not isinstance(data, expected_type):
                logger.error(f"❌ Typfehler in {path}: erwartet {expected_type.__name__}, erhalten {type(data).__name__}")
                return fallback or expected_type()  # dict() oder list() usw.

            logger.info(f"Konfiguration geladen: {path}")
            return data

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ungültige JSON-Struktur in {path}: {e}")
        return fallback or ({} if expected_type == dict else [])

```

## `..\shared\file_utils.py`
- 📄 Zeilen: 74, 🧾 Kommentare: 0, ⚙️ Funktionen: 6

```python
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union, Type

from shared.logger import get_logger

logger = get_logger("file_utils")


def ensure_directory(path: Union[str, Path]) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    logger.debug(f"📁 Verzeichnis sichergestellt: {path}")


def safe_write_text(path: Union[str, Path], content: str, backup: bool = False) -> None:
    try:
        path = Path(path)
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info(f"📄 Backup erstellt: {backup_path}")

        path.write_text(content, encoding="utf-8")
        logger.debug(f"📝 Text geschrieben nach: {path}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Schreiben nach {path}: {e}")


def safe_read_text(path: Union[str, Path]) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"⚠️ Lesefehler bei {path}: {e}")
        return None


def load_json_file(
    path: Union[str, Path],
    fallback: Optional[Any] = None,
    expected_type: Optional[Type] = dict
) -> Optional[Any]:
    try:
        text = safe_read_text(path)
        if text is None:
            return fallback or expected_type()

        data = json.loads(text)

        if expected_type and not isinstance(data, expected_type):
            logger.error(f"❌ Typfehler in {path}: erwartet {expected_type.__name__}, erhalten {type(data).__name__}")
            return fallback or expected_type()

        logger.debug(f"📥 JSON geladen: {path}")
        return data
    except Exception as e:
        logger.warning(f"⚠️ Fehler beim Laden von JSON {path}: {e}")
        return fallback or expected_type()


def write_json_file(
    path: Union[str, Path],
    data: Any,
    backup: bool = False
) -> None:
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        safe_write_text(path, content, backup=backup)
        logger.debug(f"📤 JSON gespeichert nach: {path}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Speichern von JSON {path}: {e}")


def file_exists(path: Union[str, Path]) -> bool:
    return Path(path).exists()
```

## `..\shared\ibkr_client.py`
- 📄 Zeilen: 110, 🧾 Kommentare: 1, ⚙️ Funktionen: 7

```python
#shared\ibkr_client.py
import os
import asyncio
from ib_insync import IB
from shared.logger import get_logger
from shared.client_registry import ClientRegistry

logger = get_logger("ibkr_client")

registry = ClientRegistry()


class IBKRClient:
    def __init__(self, client_id: int = None, module: str = None, task: str = None):
        """
        client_id = explizit angeben (optional)
        module = z. B. "data_manager", "symbol_fetcher_pool"
        task = optional: wird für Statusübersicht verwendet (z. B. "fetch_AAPL")
        """
        self.module = module
        self.task = task or module or "unbenannt"
        self.client_id = client_id or self._resolve_client_id()
        self.host = os.getenv("TWS_HOST", "127.0.0.1")
        self.port = int(os.getenv("TWS_PORT", 4002))
        self.ib = IB()

        registry.set_status(self.client_id, self.task, connected=False)

    def _resolve_client_id(self) -> int:
        if self.module:
            if self.module.endswith("_pool"):
                cid = registry.assign_next_free_id(task_name=self.task, pool_name=self.module)
                if cid is not None:
                    return cid
            else:
                cid = registry.get_client_id(self.module)
                if cid is not None:
                    return cid
        logger.warning("⚠️ Keine gültige client_id gefunden – verwende Fallback-ID 127")
        return 127

    def connect(self, auto_reconnect: bool = False) -> IB:
        """
        Stellt Verbindung her, meldet Status an Registry
        """
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.set_event_loop(asyncio.new_event_loop())

            self.ib.connect(self.host, self.port, clientId=self.client_id)
            logger.info(f"✅ Verbunden mit IBKR @ {self.host}:{self.port} (Client ID: {self.client_id})")
            registry.update_connected(self.client_id, connected=True)

            if auto_reconnect:
                self.ib.setCallback('disconnected', self._on_disconnect)

            return self.ib
        except Exception as e:
            logger.error(f"❌ Verbindung zu IBKR fehlgeschlagen: {e}")
            registry.update_connected(self.client_id, connected=False)
            raise ConnectionError(f"IBKR-Verbindung fehlgeschlagen: {e}")

    def _on_disconnect(self):
        logger.warning("⚠️ IBKR-Verbindung verloren – Status aktualisiert")
        registry.update_connected(self.client_id, connected=False)

    def disconnect(self):
        try:
            if self.ib.isConnected():
                self.ib.disconnect()
                logger.info(f"✅ Verbindung zu IBKR getrennt (Client ID: {self.client_id})")
        except Exception as e:
            logger.warning(f"⚠️ Fehler beim Trennen von IBKR: {e}")
        finally:
            registry.update_connected(self.client_id, connected=False)
            self.ib = IB()  # Reset

    def is_connected(self) -> bool:
        return self.ib.isConnected()

    def status(self) -> dict:
        if not self.is_connected():
            return {
                "connected": False,
                "client_id": self.client_id,
                "task": self.task,
                "host": self.host,
                "port": self.port
            }

        try:
            return {
                "connected": True,
                "client_id": self.client_id,
                "task": self.task,
                "host": self.host,
                "port": self.port,
                "server_time": str(self.ib.serverTime()),
                "tws_version": self.ib.twsConnectionTime(),
                "account_list": self.ib.managedAccounts()
            }
        except Exception as e:
            return {
                "connected": True,
                "client_id": self.client_id,
                "task": self.task,
                "warning": str(e)
            }
```

## `..\shared\ibkr_symbol_checker.py`
- 📄 Zeilen: 56, 🧾 Kommentare: 0, ⚙️ Funktionen: 2

```python
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from ib_insync import Stock
from shared.logger import get_logger
from shared.ibkr_client import IBKRClient
from shared.client_registry import registry
from shared.symbol_loader import cache_symbols

logger = get_logger("ibkr_symbol_checker")


def fetch_symbols_via_ibkr_fallback(candidates: Optional[List[str]] = None) -> List[str]:
    """
    Fragt bekannte Symbole bei IBKR ab – gibt nur gültige zurück.
    """
    logger.info("🌐 Hole Fallback-Symbole über IBKR...")

    if candidates is None:
        candidates = ["AAPL", "MSFT", "SPY", "GOOG", "TSLA", "ES", "NVDA", "QQQ", "AMZN", "META"]

    client_id = registry.get_client_id("symbol_probe") or 199
    ibkr = IBKRClient(client_id=client_id, module="symbol_probe")

    try:
        ib = ibkr.connect()
        valid_symbols = []

        def check_symbol(sym: str) -> Optional[str]:
            try:
                contract = Stock(sym, "SMART", "USD")
                details = ib.reqContractDetails(contract)
                if details:
                    logger.info(f"✅ Symbol gültig: {sym}")
                    return sym
                else:
                    logger.warning(f"❌ Symbol ungültig: {sym}")
            except Exception as e:
                logger.warning(f"⚠️ Fehler bei {sym}: {e}")
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_symbol, sym): sym for sym in candidates}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid_symbols.append(result)

        cache_symbols(valid_symbols)
        return valid_symbols

    except Exception as e:
        logger.error(f"❌ Fehler bei IBKR-Symbolprüfung: {e}")
        return []

    finally:
        ibkr.disconnect()
```

## `..\shared\lock_tools.py`
- 📄 Zeilen: 97, 🧾 Kommentare: 0, ⚙️ Funktionen: 6

```python
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
```

## `..\shared\logger.py`
- 📄 Zeilen: 71, 🧾 Kommentare: 3, ⚙️ Funktionen: 1

```python
import logging
import os
import json
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from typing import Optional

LOG_DIR = Path("logs")


def get_logger(
    modulname: str,
    log_to_console: bool = False,
    log_as_json: bool = False,
    log_level: Optional[str] = None
) -> logging.Logger:
    """
    Erstellt einen Logger mit täglicher Rotation.
    Unterstützt:
    - Log-Level aus Parameter oder ENV (LOG_LEVEL)
    - optional JSON-Formatierung
    - getrennte Log-Dateien pro Modul
    """
    logger = logging.getLogger(modulname)
    if logger.handlers:
        return logger  # Logger bereits initialisiert

    # Log-Level bestimmen
    level_str = log_level or os.getenv("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_str, logging.DEBUG)
    logger.setLevel(level)

    # Log-Datei
    log_subdir = LOG_DIR / modulname
    log_subdir.mkdir(parents=True, exist_ok=True)
    logfile_path = log_subdir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    # FileHandler
    file_handler = TimedRotatingFileHandler(
        filename=logfile_path,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        delay=False
    )

    if log_as_json:
        formatter = logging.Formatter(
            fmt=json.dumps({
                "time": "%(asctime)s",
                "level": "%(levelname)s",
                "message": "%(message)s"
            }),
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:
        formatter = logging.Formatter(
            fmt=f"[{modulname}] %(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
```

## `..\shared\symbol_data_router.py`
- 📄 Zeilen: 12, 🧾 Kommentare: 1, ⚙️ Funktionen: 1

```python
# shared/symbol_data_router.py

def get_data_method(symbol: str) -> str:
    """
    Gibt zurück: 'live', 'historical' oder 'none'
    """
    info = load_availability_for(symbol)
    if info.get("live"):
        return "live"
    elif info.get("historical"):
        return "historical"
    return "none"
```

## `..\shared\symbol_source.py`
- 📄 Zeilen: 30, 🧾 Kommentare: 1, ⚙️ Funktionen: 1

```python
from typing import List
from shared.logger import get_logger
from shared.symbol_loader import load_symbols_from_json, load_cached_symbols
from shared.ibkr_symbol_checker import fetch_symbols_via_ibkr_fallback

logger = get_logger("symbol_source")


def get_active_symbols() -> List[str]:
    """
    Hauptzugangspunkt für Symbolquelle.
    Versucht JSON → Cache → IBKR → sonst Warnung
    """
    sources = [
        load_symbols_from_json,
        # load_symbols_from_db,  # ← später möglich
        load_cached_symbols,
        fetch_symbols_via_ibkr_fallback
    ]

    for source in sources:
        try:
            symbols = source()
            if symbols:
                return symbols
        except Exception as e:
            logger.warning(f"⚠️ Fehler bei Symbolquelle {source.__name__}: {e}")

    logger.warning("⚠️ Keine aktiven Symbole gefunden.")
    return []
```

## `..\shared\telegram_notifier.py`
- 📄 Zeilen: 59, 🧾 Kommentare: 1, ⚙️ Funktionen: 2

```python
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
```

## `..\shared\thread_tools.py`
- 📄 Zeilen: 100, 🧾 Kommentare: 2, ⚙️ Funktionen: 5

```python
import threading
import time
from datetime import datetime
from typing import Callable, Dict, Optional, Any

from shared.logger import get_logger

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
```