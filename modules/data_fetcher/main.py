import csv
import io
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

import requests

from shared.logger import get_logger
from shared.config_loader import load_env, get_env_var, load_json_config
from shared.file_utils import file_exists

logger = get_logger("data_fetcher")

FAILED_JSON = Path("logs/errors/failed_requests.json")
FAILED_JSON.parent.mkdir(parents=True, exist_ok=True)


def _append_failed(entry: Dict[str, Any]) -> None:
    """Hängt einen kompakten Fehler-Eintrag an logs/errors/failed_requests.json an."""
    data: List[Dict[str, Any]] = []
    if file_exists(FAILED_JSON):
        try:
            data = json.loads(FAILED_JSON.read_text(encoding="utf-8"))
        except Exception:
            data = []
    data.append(entry)
    FAILED_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _fetch_http(url: str, headers: Dict[str, str], timeout: float = 10.0) -> Optional[str]:
    """HTTP(S)-Abruf; gibt Text zurück oder None bei Fehler."""
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
    """Liest lokalen CSV-Content aus file://Pfad."""
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
    """Zählt CSV-Zeilen (inkl. Header, wenn vorhanden)."""
    try:
        reader = csv.reader(io.StringIO(text))
        return sum(1 for _ in reader)
    except Exception:
        # Falls kein echtes CSV, fallback: Zeilen zählen
        return len([ln for ln in text.splitlines() if ln.strip()])


def _process_task(task: Dict[str, Any], api_key: Optional[str]) -> None:
    name = task.get("name", "unnamed_task")
    symbol = task.get("symbol", "UNKNOWN")
    url = task.get("url")
    active = task.get("active", False)

    if not active:
        logger.info(f"Task deaktiviert: {name}")
        return
    if not url:
        logger.error(f"Task {name}: Keine URL angegeben.")
        _append_failed({"task": name, "symbol": symbol, "error": "missing_url"})
        return

    logger.info(f"Starte Abruf: {name} ({symbol}) → {url}")

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    if url.startswith("file://"):
        content = _fetch_file(url)
    else:
        content = _fetch_http(url, headers=headers, timeout=10.0)

    if content is None:
        logger.error(f"Abruf fehlgeschlagen: {name} ({symbol})")
        return

    # Content-Length prüfen (Text-basiert)
    size_bytes = len(content.encode("utf-8"))
    if size_bytes < 500:
        logger.warning(f"{name}: Antwort sehr klein ({size_bytes} Bytes) – Verdacht auf unvollständige Daten.")

    # CSV-Zeilen zählen
    rows = _count_csv_rows(content)
    logger.info(f"{name}: {rows} Datenzeilen empfangen.")

    logger.info(f"Abschluss: {name} ({symbol})")


def run():
    logger.info("🟢 Data-Fetcher gestartet")

    # .env laden (idempotent; im main_runner meist bereits geschehen)
    load_env()
    api_key = get_env_var("API_KEY", required=False)

    # Tasks laden
    tasks_cfg = load_json_config("config/tasks.json", fallback=[])
    if not isinstance(tasks_cfg, list):
        logger.error("config/tasks.json: Erwartet Liste von Tasks.")
        return

    for task in tasks_cfg:
        _process_task(task, api_key)

    logger.info("✅ Data-Fetcher abgeschlossen")


if __name__ == "__main__":
    run()
