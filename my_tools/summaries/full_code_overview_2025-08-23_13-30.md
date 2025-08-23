# 🗂️ Vollständiger Projektinhalt (Codeübersicht)


## `live_fx_viewer.py`
- 📄 Zeilen: 276, 🧾 Kommentare: 17, ⚙️ Funktionen: 11

```python
import time
import threading
import os
import csv
import math
from datetime import datetime
from ib_insync import Forex
from shared.ibkr_client.ibkr_client import IBKRClient
from shared.logger.logger import get_logger

# ---- Optionale Farben sicher behandeln -------------------------------------
HAS_COLOR = False
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except Exception:
    class _S:
        RESET_ALL = ""
    Fore = Style = _S()

logger = get_logger("live_fx_dashboard", log_to_console=False)
stop_flag = False

# ---- Utils ------------------------------------------------------------------
def input_listener():
    global stop_flag
    while True:
        if input().strip().lower() == "q":
            stop_flag = True
            break

def clear_line():
    print("\r\033[2K", end="")

def export_to_csv(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, mode="a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "bid", "ask", "spread"])
        writer.writerow(row)

def _to_float(x):
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
        return float(x)
    except Exception:
        return None

def _fmt_price(x):
    return f"{x:.5f}" if x is not None else "-"

def _pip_info(spread):
    if spread is None:
        return "-", "Pips"
    pips = round(spread * 10000, 1)
    unit = "Pip" if abs(pips) == 1 else "Pips"
    return pips, unit

def _flash(text, active):
    if not active:
        return text
    if HAS_COLOR:
        return f"{Fore.YELLOW}⚡ {text}{Style.RESET_ALL}"
    return f"⚡ {text}"

def _has_quotes(ticker):
    return (ticker is not None) and (
        _to_float(ticker.bid) is not None or _to_float(ticker.ask) is not None
    )

# ---- Marktdaten-Strategien --------------------------------------------------
def _subscribe_with_fallback(ib, contract, timeout=2.5):
    """
    Versucht nacheinander: Live(1) → Delayed(3) → Delayed-Frozen(4).
    Gibt (ticker, md_type) zurück; md_type ∈ {0,1,3,4}.
    """
    # Live
    try:
        ib.reqMarketDataType(1)
    except Exception:
        pass
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 1

    # Aufräumen + Delayed
    try:
        ib.cancelMktData(t)
    except Exception:
        pass
    ib.sleep(0.1)

    ib.reqMarketDataType(3)
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 3

    # Aufräumen + Delayed-Frozen (einige Konten liefern so eher Werte)
    try:
        ib.cancelMktData(t)
    except Exception:
        pass
    ib.sleep(0.1)

    ib.reqMarketDataType(4)  # Delayed-Frozen
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 4

    return t, 0

# ---- Hauptanzeige -----------------------------------------------------------
def _snapshot_poll(ib, contract, timeout=2.0):
    """
    Holt einmalig Bid/Ask per Snapshot (Polling).
    """
    try:
        ticker = ib.reqMktData(contract, "", True, False)
        ib.sleep(timeout)
        bid = _to_float(ticker.bid)
        ask = _to_float(ticker.ask)
        try:
            ib.cancelMktData(ticker)
        except Exception:
            pass
        return bid, ask
    except Exception:
        return None, None

def display_live_feed(symbol="EURUSD", duration=60, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=1.5):
    """
    Falls weder Live noch Delayed Updates liefern, wird automatisch auf Snapshot-Polling umgestellt.
    """
    global stop_flag
    stop_flag = False  # Reset bei erneutem Aufruf

    # Vorab-Check: Contract existiert?
    ibkr_probe = IBKRClient(module="fx_probe", task=f"check_{symbol}")
    ib_probe = ibkr_probe.connect()
    try:
        if not ib_probe.reqContractDetails(Forex(symbol)):
            print(f"❌ Keine Marktdaten für {symbol}")
            return
    finally:
        ibkr_probe.disconnect()

    print(f"🌐 Starte Live-Dashboard für {symbol} (Dauer: {duration}s, Abbruch: 'q')")
    threading.Thread(target=input_listener, daemon=True).start()

    ibkr = IBKRClient(module="fx_live", task=f"dashboard_{symbol}")
    ib = ibkr.connect()

    ticker = None
    mode = "stream"   # 'stream' oder 'snapshot'
    md_type = 0       # 1=Live, 3=Delayed

    try:
        contract = Forex(symbol)
        ticker, md_type = _subscribe_with_fallback(ib, contract, timeout=2.5)

        header_note = "(Live)" if md_type == 1 else "(Delayed)" if md_type == 3 else "(keine Daten)"
        print(f"\n📡 FX Live Dashboard – klassisch  {header_note}")
        print("-" * 60)
        print("Zeit     , Bid         | Ask         → Spread")
        print("-" * 60)
        print("Drücke 'q' + Enter zum Beenden")
        print("")
        print("Drücke 'q' + Enter zum Beenden")

        prev_bid = prev_ask = None
        bid_flash_end = ask_flash_end = 0.0
        log_path = os.path.join("logs", f"{symbol.lower()}_{datetime.now().date()}.csv")
        start_time = time.time()
        last_update_time = time.time()
        warned_stream_dead = False

        # Falls Stream komplett leer bleibt, direkt in Snapshot-Modus wechseln
        if md_type == 0:
            mode = "snapshot"
            print("ℹ️  Wechsel auf Snapshot-Modus (weder Live noch Delayed Stream verfügbar).")

        while not stop_flag and (time.time() - start_time < duration):
            now = time.time()

            if mode == "stream":
                ib.sleep(0.3)
                bid = _to_float(ticker.bid)
                ask = _to_float(ticker.ask)
            else:
                # Snapshot-Polling
                bid, ask = _snapshot_poll(ib, contract, timeout=2.0)
                if mode == "snapshot":
                    # Begrenze Polling-Frequenz
                    time.sleep(snapshot_interval)

            spread = (ask - bid) if (bid is not None and ask is not None) else None

            updated = False
            if bid != prev_bid:
                bid_flash_end = now + flash_duration
                prev_bid = bid
                updated = True
            if ask != prev_ask:
                ask_flash_end = now + flash_duration
                prev_ask = ask
                updated = True

            # Stream-Watchdog → Snapshot-Fallback
            if mode == "stream" and (now - last_update_time) > no_update_watchdog:
                if not warned_stream_dead:
                    print("\n⚠️  Keine Stream-Updates. Ursache: konkurrierende Live-Sitzung (10197) "
                          "oder kein Abo. Schalte auf Snapshot-Modus um.")
                    warned_stream_dead = True
                mode = "snapshot"
                # Stream sauber abbestellen
                try:
                    if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                        ib.cancelMktData(ticker)
                except Exception:
                    pass
                # Hinweis in Kopfzeile aktualisieren
                print("ℹ️  Datenquelle: verzögerte Snapshots.")
                continue

            if updated:
                last_update_time = now
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # CSV: leere Felder statt 'nan'
                export_to_csv(
                    log_path,
                    [
                        timestamp,
                        f"{bid:.5f}" if bid is not None else "",
                        f"{ask:.5f}" if ask is not None else "",
                        f"{spread:.5f}" if spread is not None else ""
                    ]
                )
                logger.info(f"{timestamp} | {symbol} | BID: {bid} | ASK: {ask} | SPREAD: {spread}")

                # Cursor 2 Zeilen hoch (Datenzeile + Hinweiszeile)
                print("\033[2F", end="")
                clear_line()
                ts_short = datetime.now().strftime("%H:%M:%S")
                bid_txt = _flash(_fmt_price(bid), now < bid_flash_end)
                ask_txt = _flash(_fmt_price(ask), now < ask_flash_end)
                pips, unit = _pip_info(spread)
                spread_txt = "-" if spread is None else f"{spread:.5f}"
                print(f"{ts_short}, Bid: {bid_txt} | Ask: {ask_txt} → Spread: {spread_txt} ({pips} {unit})")
                clear_line()
                src = "Live" if (mode == "stream" and md_type == 1) else "Delayed Stream" if (mode == "stream" and md_type == 3) else "Snapshot (Delayed)"
                print(f"Drücke 'q' + Enter zum Beenden  • Quelle: {src}")

        print("\n🛑 Live-Dashboard beendet.")
    finally:
        try:
            if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                ib.cancelMktData(ticker)
        except Exception:
            pass
        ibkr.disconnect()

if __name__ == "__main__":
    # Hinweis: Schließe andere TWS/Gateway-Sitzungen, wenn du Live erwartest.
    display_live_feed(symbol="EURUSD", duration=120, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=1.5)
```

## `main.py`
- 📄 Zeilen: 54, 🧾 Kommentare: 8, ⚙️ Funktionen: 1

```python
# main.py
import atexit
import sys
from pathlib import Path

from tools.log_summary import summarize_logs, send_telegram_errors  # ← sicherstellen, dass import korrekt
from shared.logger.logger import get_logger

logger = get_logger("main_runner", log_to_console=True)

# Exit-Funktion
def summarize_and_exit():
    summary = summarize_logs()
    critical_found = False
    summary_lines = []

    summary_lines.append("📋 Fehlerübersicht (beim Beenden des Programms):\n")

    for module, count, last_line, all_errors in summary:
        if count > 0:
            summary_lines.append(f"\n🔧 Modul: {module} ({count} Fehler)")
            for err in all_errors:
                summary_lines.append(f"  {err}")
            if any("CRITICAL" in e or "ERROR" in e for e in all_errors):
                critical_found = True

    summary_text = "\n".join(summary_lines)

    # ⬇️ Speicherort definieren
    report_path = Path("reports/error_summary.txt")
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(summary_text, encoding="utf-8")

    # 🖨️ Terminal-Ausgabe NUR als Zusammenfassung
    print("\n📋 Fehlerübersicht (heute):")
    for module, count, *_ in summary:
        if count > 0:
            print(f"- {module}: {count} Fehler")
    if any(count > 0 for module, count, *_ in summary):
        print("→ Details siehe reports/error_summary.txt")

    # 📬 Telegram nur bei echten Fehlern
    if critical_found:
        send_telegram_errors(summary)

    # ⛔️ Exit-Code setzen, wenn Fehler
    if critical_found:
        sys.exit(1)

atexit.register(summarize_and_exit)

# 🧠 Start deiner Anwendung
print("🚀 Starte robust_lab...")
# ... dein restlicher Code ...
```

## `sanity_check.py`
- 📄 Zeilen: 54, 🧾 Kommentare: 0, ⚙️ Funktionen: 3

```python
import os
from datetime import datetime

EXCLUDE_FILES = ["__init__.py", ".env"]
EXCLUDE_DIRS = [".git", "__pycache__", "venv", "env", ".idea", ".vscode"]
output_lines = ["# 🗂️ Vollständiger Projektinhalt mit Code\n"]

def count_lines(lines):
    total = len(lines)
    comments = len([l for l in lines if l.strip().startswith("#")])
    functions = len([l for l in lines if l.strip().startswith("def ")])
    return total, comments, functions

def scan_file(path):
    if os.path.basename(path) in EXCLUDE_FILES:
        return

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total, comments, functions = count_lines(lines)
    rel_path = os.path.relpath(path, os.getcwd())

    output_lines.append(f"\n## `{rel_path}`")
    output_lines.append(f"- 📄 Zeilen: {total}")
    output_lines.append(f"- 🧾 Kommentare: {comments}")
    output_lines.append(f"- ⚙️ Funktionen: {functions}\n")
    output_lines.append("```python")
    output_lines.extend([l.rstrip("\n") for l in lines])
    output_lines.append("```")

def scan_project(root="."):
    print("📢 Scanne Projekt...")
    for root_dir, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root_dir, file)
                scan_file(full_path)

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    summary_dir = os.path.join(script_dir, "summaries")
    os.makedirs(summary_dir, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    summary_filename = f"full_code_overview_{now}.md"
    output_path = os.path.join(summary_dir, summary_filename)

    scan_project(".")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Übersicht gespeichert in:\n{output_path}")
```

## `modules\data_fetcher\live_market_data.py`
- 📄 Zeilen: 39, 🧾 Kommentare: 0, ⚙️ Funktionen: 1

```python
from ib_insync import Stock
from shared.ibkr_client.ibkr_client import IBKRClient
from shared.logger.logger import get_logger
from shared.lock_tools.lock_tools import create_lock, remove_lock

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

## `modules\data_fetcher\main.py`
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

from shared.logger.logger import get_logger
from shared.config_loader.config_loader import load_env, get_env_var, load_json_config
from shared.file_utils.file_utils import file_exists
from shared.telegram_notifier.telegram_notifier import send_telegram_alert

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

## `modules\health\main.py`
- 📄 Zeilen: 60, 🧾 Kommentare: 0, ⚙️ Funktionen: 4

```python
import socket
import requests
import logging
import time

from shared.config_loader.config_loader import load_env
from shared.logger.logger import get_logger
from shared.telegram_notifier.telegram_notifier import send_telegram_alert
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

## `modules\symbol_fetcher\main.py`
- 📄 Zeilen: 56, 🧾 Kommentare: 0, ⚙️ Funktionen: 2

```python
from shared.ibkr_client.ibkr_client import IBKRClient
from shared.thread_tools.thread_tools import start_named_thread
from shared.logger.logger import get_logger
from shared.client_registry.client_registry import registry
from shared.config_loader.config_loader import load_json_config
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

## `my_tools\create_feature_sandbox.py`
- 📄 Zeilen: 126, 🧾 Kommentare: 15, ⚙️ Funktionen: 4

```python
import os
from datetime import datetime

# 🔧 Pfade
DEV_LAB_ROOT = r"C:\Users\shaba\OneDrive\Anlagen\dev_lab\\"
INTEGRATION_LOG_PATH = r"C:\Users\shaba\OneDrive\Anlagen\engine3\integration_log.md"

# 📦 Kategorien für Feature-Typen
CATEGORIES = {
    "1": "Strategie",
    "2": "Datenquelle / Datenmanager",
    "3": "UI-Komponente / Menü",
    "4": "Visualisierung / Anzeige",
    "5": "Tool / Utility",
    "6": "Konfiguration / Struktur",
    "7": "Tests / Testumgebung",
}

# 📁 Vorlage für neue Feature-Ordner
TEMPLATE_FILES = {
    "main.py": '''\
# main.py
# Einstiegspunkt für dein Feature

from core import run_feature

if __name__ == "__main__":
    run_feature()
''',
    "core.py": '''\
# core.py
# Hier kommt deine Hauptlogik hin

def run_feature():
    print("🔧 Feature läuft... (hier deine Logik einfügen)")
''',
    "test_runner.py": '''\
# test_runner.py
# Testlogik für dein Feature

def run_tests():
    print("🧪 Tests ausführen...")
    # Beispiel-Testcode hier

if __name__ == "__main__":
    run_tests()
''',
    "notes.md": '''\
# 🧠 Feature-Dokumentation

## Ziel:
Beschreibe hier kurz, was dieses Feature tun soll.

## Status:
- [ ] Prototyp läuft
- [ ] getestet mit echten Daten
- [ ] bereit zur Integration

## Geplante Integration:
→ Modul: z. B. signal_scanner/tools
→ Zieldatei: z. B. symbol_selector.py
'''
}

def create_feature_folder(name, category):
    base_path = os.path.join(DEV_LAB_ROOT, name)
    os.makedirs(base_path, exist_ok=True)
    os.makedirs(os.path.join(base_path, "data"), exist_ok=True)

    print(f"\n📁 Erstelle Feature-Ordner: {base_path}")

    for filename, content in TEMPLATE_FILES.items():
        path = os.path.join(base_path, filename)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"✅ {filename} erstellt.")
        else:
            print(f"⚠️ {filename} existiert bereits – übersprungen.")

    append_integration_log_entry(name, category)
    print(f"\n📂 '{name}' ({category}) ist bereit in dev_lab.")

def append_integration_log_entry(name, category):
    now_str = datetime.now().strftime("%Y-%m-%d")
    entry = f"""\n
---

## 🧩 {name}
**Kategorie**: {category}  
**Erstellt am**: {now_str}  
**Quelle**: dev_lab/{name}/  
**Geplante Integration**: [Bitte ausfüllen]  
**Status**: 🟡 in Entwicklung
"""

    os.makedirs(os.path.dirname(INTEGRATION_LOG_PATH), exist_ok=True)

    if not os.path.exists(INTEGRATION_LOG_PATH):
        with open(INTEGRATION_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("# 🔄 Integration Log – engine3\n")

    with open(INTEGRATION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry)

    print("📝 Integrationseintrag ergänzt (integration_log.md).")

if __name__ == "__main__":
    print("🆕 Neues Modul/Komponente anlegen in dev_lab/")

    feature_name = input("🔤 Name eingeben (z. B. breakout_filter): ").strip()
    if not feature_name:
        print("❌ Kein Name eingegeben. Vorgang abgebrochen.")
        exit()

    print("\n📂 Wähle Kategorie:")
    for key, label in CATEGORIES.items():
        print(f"{key}. {label}")

    category_choice = input("\n🗂️ Nummer der Kategorie eingeben: ").strip()
    category = CATEGORIES.get(category_choice)

    if not category:
        print("❌ Ungültige Auswahl. Vorgang abgebrochen.")
    else:
        create_feature_folder(feature_name, category)
```

## `my_tools\full_code_overview.py`
- 📄 Zeilen: 55, 🧾 Kommentare: 3, ⚙️ Funktionen: 3

```python
import os
from datetime import datetime

EXCLUDE_FILES = ["__init__.py", ".env"]
EXCLUDE_DIRS = [".git", "__pycache__"]
output_lines = ["# 🗂️ Vollständiger Projektinhalt (Codeübersicht)\n"]

def count_lines(lines):
    total = len(lines)
    comments = len([l for l in lines if l.strip().startswith("#")])
    return total, comments

def scan_file(path):
    rel_path = os.path.relpath(path, os.getcwd())
    if any(excl in rel_path for excl in EXCLUDE_FILES):
        return

    with open(path, "r", encoding="utf-8") as file:
        lines = file.readlines()

    total, comments = count_lines(lines)
    functions = len([l for l in lines if l.strip().startswith("def ")])
    
    output_lines.append(f"\n## `{rel_path}`")
    output_lines.append(f"- 📄 Zeilen: {total}, 🧾 Kommentare: {comments}, ⚙️ Funktionen: {functions}\n")
    output_lines.append("```python")
    output_lines.extend([l.rstrip("\n") for l in lines])
    output_lines.append("```")

def scan_project(root="."):
    print("📢 Scanne alle Python-Dateien mit vollständigem Inhalt...")
    for root_dir, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py") and file not in EXCLUDE_FILES:
                full_path = os.path.join(root_dir, file)
                scan_file(full_path)

if __name__ == "__main__":
    # 📁 Zielordner: my_tools/summaries
    script_dir = os.path.dirname(os.path.abspath(__file__))
    summary_dir = os.path.join(script_dir, "summaries")
    os.makedirs(summary_dir, exist_ok=True)

    # 📅 Dateiname mit Datum & Uhrzeit
    now = datetime.now().strftime("%Y-%m-%d_%H-%M")
    summary_filename = f"full_code_overview_{now}.md"
    output_path = os.path.join(summary_dir, summary_filename)

    # 🔍 Scan starten und Datei speichern
    scan_project(".")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Übersicht gespeichert in:\n{output_path}")
```

## `my_tools\scan_target.py`
- 📄 Zeilen: 111, 🧾 Kommentare: 5, ⚙️ Funktionen: 6

```python
import os
import json

EXCLUDE_FILES = ["__init__.py", ".env"]
EXCLUDE_DIRS = [".git", "__pycache__"]
ALLOWED_EXTS = {".py", ".json"}  # ← JSON zulassen
output_lines = ["# 🗂️ Projektdateien (gezielte Übersicht)\n"]

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

def count_lines(lines, ext):
    total = len(lines)
    if ext == ".py":
        comments = sum(1 for l in lines if l.lstrip().startswith("#"))
    else:
        comments = 0  # JSON hat keine Kommentare im Standard
    return total, comments

def detect_code_fence(ext):
    return "python" if ext == ".py" else "json" if ext == ".json" else ""

def scan_file(path):
    rel_path = os.path.relpath(path, PROJECT_ROOT)
    if any(excl in rel_path for excl in EXCLUDE_FILES):
        return

    ext = os.path.splitext(path)[1].lower()
    try:
        with open(path, "r", encoding="utf-8") as file:
            text = file.read()
    except UnicodeDecodeError:
        output_lines.append(f"\n## `{rel_path}`")
        output_lines.append("⚠️ Konnte Datei nicht lesen (Unicode-Fehler)\n")
        return

    # Für JSON optional schön formatieren (failsafe bei invalider JSON)
    if ext == ".json":
        try:
            text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except Exception:
            # Falls keine valide JSON: Rohtext verwenden
            pass

    lines = text.splitlines()
    total, comments = count_lines(lines, ext)

    functions = 0
    if ext == ".py":
        functions = sum(1 for l in lines if l.lstrip().startswith("def "))

    fence = detect_code_fence(ext)

    output_lines.append(f"\n## `{rel_path}`")
    output_lines.append(f"- 📄 Zeilen: {total}, 🧾 Kommentare: {comments}, ⚙️ Funktionen: {functions}\n")
    output_lines.append(f"```{fence}")
    output_lines.extend(lines)
    output_lines.append("```")

def path_is_allowed_file(path):
    return os.path.isfile(path) and os.path.splitext(path)[1].lower() in ALLOWED_EXTS

def scan_target(rel_input):
    full_path = os.path.join(PROJECT_ROOT, rel_input)

    if path_is_allowed_file(full_path):
        scan_file(full_path)

    elif os.path.isdir(full_path):
        for root_dir, dirs, files in os.walk(full_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in ALLOWED_EXTS and fname not in EXCLUDE_FILES:
                    scan_file(os.path.join(root_dir, fname))
    else:
        print(f"\n❌ Pfad ungültig oder nicht gefunden: `{rel_input}`\n")
        return False

    return True

def start():
    print("🔍 Engine3-Datei-Scanner\n")
    print("💡 Gib ein Verzeichnis oder eine Datei relativ zum Projekt ein (z. B. `modules/signal_scanner` oder `modules/signal_scanner/core.py`).")
    print("⬅️ Leere Eingabe = Abbruch")

    while True:
        user_input = input("\n📂 Pfad eingeben: ").strip()
        if not user_input:
            print("🚪 Vorgang abgebrochen.")
            return

        if scan_target(user_input):
            break  # nur wenn erfolgreich -> speichern

    # 🔧 Speicherort berechnen (allgemein über splitext)
    name_part, _ = os.path.splitext(os.path.basename(user_input))
    output_name = f"code_{name_part}.md"

    # 📁 Speicherziel: gleicher Ort wie Eingabe
    target_path = os.path.join(PROJECT_ROOT, user_input)
    target_dir = os.path.dirname(target_path) if os.path.isfile(target_path) else target_path
    output_file = os.path.join(target_dir, output_name)

    # 💾 Datei speichern
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))

    print(f"\n✅ Übersicht gespeichert unter:\n{output_file}")

if __name__ == "__main__":
    start()
```

## `my_tools\summarize_project.py`
- 📄 Zeilen: 88, 🧾 Kommentare: 5, ⚙️ Funktionen: 4

```python
import os
import ast
import json
from datetime import datetime
import subprocess

# 📁 Absoluter Pfad zur Datei, fix in my_tools/summaries
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
summary_dir = os.path.join(SCRIPT_DIR, "summaries")
os.makedirs(summary_dir, exist_ok=True)

# 🕒 Dateiname mit Datum & Uhrzeit
from datetime import datetime
now = datetime.now().strftime("%Y-%m-%d_%H-%M")
summary_filename = f"summarize_project_{now}.md"
SUMMARY_PATH = os.path.join(summary_dir, summary_filename)

# 📂 Basis fürs Scannen bleibt das Hauptprojekt (eine Ebene höher)
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# 🔍 Scan-Ergebnis
summary = []

# 🔒 Ausgeschlossene Pfade
EXCLUDED = ['.env', '__pycache__']

def is_valid_file(filename):
    return filename.endswith(('.py', '.json')) and not any(x in filename for x in EXCLUDED)

def summarize_python_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read())
        functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
        classes = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
        globals_ = [n.targets[0].id for n in ast.walk(tree)
                    if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)]
        imports = [n.names[0].name for n in ast.walk(tree) if isinstance(n, ast.Import)]
        return functions, classes, globals_, imports
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        return [], [], [], []

def summarize_json_keys(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict):
            return list(data.keys())
        return []
    except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError):
        return []

def scan_project():
    for root, _, files in os.walk(PROJECT_ROOT):
        if any(ex in root for ex in EXCLUDED):
            continue
        for file in files:
            if not is_valid_file(file):
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, PROJECT_ROOT)
            summary.append(f"\n### {rel_path}")

            if file.endswith('.py'):
                funcs, classes, globals_, imports = summarize_python_file(full_path)
                if imports:
                    summary.append(f"- 📦 Imports: {', '.join(sorted(set(imports)))}")
                if classes:
                    summary.append(f"- 🧩 Klassen: {', '.join(classes)}")
                if funcs:
                    summary.append(f"- ⚙️ Funktionen: {', '.join(funcs)}")
                if globals_:
                    summary.append(f"- 🧠 Globale Variablen: {', '.join(globals_)}")

            elif file.endswith('.json'):
                keys = summarize_json_keys(full_path)
                if keys:
                    summary.append(f"- 🔑 JSON-Schlüssel: {', '.join(keys)}")

if __name__ == "__main__":
    summary.append("# 🔍 Projektüberblick")
    summary.append(f"📁 Basisverzeichnis: `{PROJECT_ROOT}`\n")
    scan_project()

    with open(SUMMARY_PATH, 'w', encoding='utf-8') as f:
        f.write("\n".join(summary))

    print(f"\n✅ Übersicht wurde gespeichert unter:\n{SUMMARY_PATH}")
```

## `shared\ibkr_symbol_checker.py`
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

## `shared\core\client_registry.py`
- 📄 Zeilen: 95, 🧾 Kommentare: 0, ⚙️ Funktionen: 10

```python
import os
import json
from pathlib import Path
from typing import Union, List, Optional, Dict

from shared.utils.logger import get_logger
from shared.utils.file_utils import load_json_file

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

## `shared\core\config_loader.py`
- 📄 Zeilen: 78, 🧾 Kommentare: 0, ⚙️ Funktionen: 4

```python
import os
import json
from pathlib import Path
from typing import Any, Dict, Optional, Type, Union
from dotenv import load_dotenv
from shared.utils.logger import get_logger

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

## `shared\ibkr\ibkr_client.py`
- 📄 Zeilen: 110, 🧾 Kommentare: 1, ⚙️ Funktionen: 7

```python
#shared\ibkr_client.py
import os
import asyncio
from ib_insync import IB
from shared.utils.logger import get_logger
from shared.core.client_registry import ClientRegistry

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

## `shared\ibkr\ibkr_symbol_checker.py`
- 📄 Zeilen: 55, 🧾 Kommentare: 0, ⚙️ Funktionen: 2

```python
from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from ib_insync import Stock
from shared.utils.logger import get_logger
from shared.ibkr.ibkr_client import IBKRClient
from shared.core.client_registry import registry

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

## `shared\ibkr\symbol_data_router.py`
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

## `shared\symbols\symbol_source.py`
- 📄 Zeilen: 30, 🧾 Kommentare: 1, ⚙️ Funktionen: 1

```python
from typing import List
from shared.utils.logger import get_logger
from shared.ibkr.ibkr_symbol_checker import fetch_symbols_via_ibkr_fallback


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

## `shared\system\telegram_notifier.py`
- 📄 Zeilen: 59, 🧾 Kommentare: 1, ⚙️ Funktionen: 2

```python
import requests
import os
import time
from typing import Optional
from shared.utils.logger import get_logger
from shared.core.config_loader import get_env_var

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

## `shared\system\thread_tools.py`
- 📄 Zeilen: 100, 🧾 Kommentare: 2, ⚙️ Funktionen: 5

```python
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
```

## `shared\utils\file_utils.py`
- 📄 Zeilen: 74, 🧾 Kommentare: 0, ⚙️ Funktionen: 6

```python
import json
from pathlib import Path
from typing import Any, Optional, Union, Type

from shared.utils.logger import get_logger

logger = get_logger("file_utils")


def ensure_directory(path: Union[str, Path]) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    logger.debug("📁 Verzeichnis sichergestellt: %s", path)


def safe_write_text(path: Union[str, Path], content: str, backup: bool = False) -> None:
    try:
        path = Path(path)
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("📄 Backup erstellt: %s", backup_path)

        path.write_text(content, encoding="utf-8")
        logger.debug(f"📝 Text geschrieben nach: {path}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Schreiben nach {path}: {e}")


def safe_read_text(path: Union[str, Path]) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, IOError) as e:
        logger.warning("⚠️ Lesefehler bei %s: %s", path, e)
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

## `shared\utils\lock_tools.py`
- 📄 Zeilen: 97, 🧾 Kommentare: 0, ⚙️ Funktionen: 6

```python
import os
import signal
import psutil
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

from shared.utils.logger import get_logger

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

## `shared\utils\logger.py`
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

## `tools\log_summary.py`
- 📄 Zeilen: 54, 🧾 Kommentare: 0, ⚙️ Funktionen: 3

```python
import os
from pathlib import Path
from datetime import datetime
import re
from shared.telegram_notifier.telegram_notifier import send_telegram_alert  # Wichtig!

LOG_DIR = Path("logs")
KEYWORDS = ["ERROR", "Exception", "CRITICAL", "WARNING", "Traceback"]

def summarize_logs(date: str = None):
    summary = []
    date_str = date or datetime.now().strftime("%Y-%m-%d")

    for module_dir in LOG_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        log_file = module_dir / f"{date_str}.log"
        if not log_file.exists():
            continue

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            errors = [line.strip() for line in lines if any(k in line for k in KEYWORDS)]
            if errors:
                summary.append((module_dir.name, len(errors), errors[-1].strip(), errors))
            else:
                summary.append((module_dir.name, 0, "OK", []))

    return summary

def send_telegram_errors(summary):
    """Sende kritische Fehler per Telegram."""
    error_lines = []

    for module, count, _, all_errors in summary:
        if count == 0:
            continue
        error_lines.append(f"🔧 {module} ({count} Fehler)")
        for line in all_errors[-3:]:  # Nur letzte 3 Fehler pro Modul senden
            error_lines.append(f"  {line}")
    
    if error_lines:
        message = "⚠️ Fehler beim robust_lab:\n\n" + "\n".join(error_lines)
        send_telegram_alert(message)
        
def print_summary():
    print("\n🔍 Log-Übersicht (heute):\n")
    summary = summarize_logs()
    for module, count, last, _ in summary:
        status = "✅ OK" if count == 0 else f"❗️{count} Fehler"
        print(f"{module:<20} | {status:<15} | Letzter Eintrag: {last[:80]}")

if __name__ == "__main__":
    print_summary()
```

## `ui\console_view.py`
- 📄 Zeilen: 0, 🧾 Kommentare: 0, ⚙️ Funktionen: 0

```python
```