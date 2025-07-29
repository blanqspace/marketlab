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
