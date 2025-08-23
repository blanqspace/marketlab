# 🗂️ Projektdateien (gezielte Übersicht)


## `..\modules\data_fetcher\live_market_data.py`
- 📄 Zeilen: 39, 🧾 Kommentare: 0, ⚙️ Funktionen: 1

```python
from ib_insync import Stock
from shared.ibkr_client import IBKRClient
from shared.logger import get_logger
from shared.lock_tools import create_lock, remove_lock

import time

logger = get_logger("live_market_data", log_to_console=True)

def fetch_realtime_data(symbol: str = "AAPL", duration_sec: int = 20):
    lock_name = f"live_data_{symbol.lower()}"
    if not create_lock(lock_name, note=f"Live-Daten {symbol}"):
        return

    try:
        ibkr = IBKRClient(module="realtime", task=f"live_{symbol}")
        ib = ibkr.connect()

        contract = Stock(symbol, "SMART", "USD")
        ib.reqMarketDataType(1)  # ← Diese Zeile ersetzt MarketDataType.Live
        ticker = ib.reqMktData(contract, "", False, False)

        logger.info(f"📡 Abonniere Live-Daten für {symbol} ({duration_sec} Sekunden) ...")

        start_time = time.time()
        while time.time() - start_time < duration_sec:
            ib.sleep(1)
            if ticker.last:
                logger.info(f"{symbol} → Last: {ticker.last} | Bid: {ticker.bid} | Ask: {ticker.ask}")

        ib.cancelMktData(contract)
        ibkr.disconnect()
        logger.info(f"🛑 Live-Daten für {symbol} beendet.")

    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen von Live-Daten für {symbol}: {e}")

    finally:
        remove_lock(lock_name)
```

## `..\modules\data_fetcher\main.py`
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

## `..\modules\symbol_fetcher\main.py`
- 📄 Zeilen: 56, 🧾 Kommentare: 0, ⚙️ Funktionen: 2

```python
from shared.ibkr_client import IBKRClient
from shared.thread_tools import start_named_thread
from shared.logger import get_logger
from shared.client_registry import registry
from shared.config_loader import load_json_config
import time

logger = get_logger("symbol_fetcher", log_to_console=True)

def fetch_task(symbol: str):
    try:
        client = IBKRClient(module="symbol_fetcher_pool", task=f"fetch_{symbol}")
        ib = client.connect()

        contract = ib.qualifyContracts(ib.stock(symbol))[0]

        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="5 mins",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1
        )

        logger.info(f"{symbol}: {len(bars)} Balken empfangen")
        client.disconnect()

    except Exception as e:
        logger.error(f"❌ Fehler bei {symbol}: {e}")

def run():
    logger.info("🚀 Symbol-Fetcher mit dynamischer Symbolquelle")
    symbol_tasks = load_json_config("config/symbol_tasks.json", fallback=[])

    active_symbols = [task["symbol"] for task in symbol_tasks if task.get("active", False)]

    if not active_symbols:
        logger.warning("⚠️ Keine aktiven Symbole gefunden.")
        return

    for symbol in active_symbols:
        start_named_thread(
            name=f"fetch_{symbol}",
            target=fetch_task,
            args=(symbol,),
            daemon=True
        )

    time.sleep(15)
    print("\n📊 IBKR-Statusübersicht:")
    print(registry.get_status_report())

if __name__ == "__main__":
    run()
```