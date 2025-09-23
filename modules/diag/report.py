# shared/diag/report.py
from __future__ import annotations
import json, os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

BASE = Path("reports")
EV_DIR = BASE / "events"
SM_DIR = BASE / "summary"
EV_DIR.mkdir(parents=True, exist_ok=True)
SM_DIR.mkdir(parents=True, exist_ok=True)

def _ts():
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def append_event(kind: str, payload: Dict[str, Any]):
    """Schreibt eine Event-Zeile im JSONL-Format."""
    day = datetime.utcnow().strftime("%Y%m%d")
    f = EV_DIR / f"{day}.jsonl"
    rec = {"ts": _ts(), "kind": kind, **payload}
    with f.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

def write_session_summary(title: str, lines: list[str]):
    """Kurze Textzusammenfassung anfügen."""
    day = datetime.utcnow().strftime("%Y%m%d")
    f = SM_DIR / f"{day}.txt"
    with f.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== {title} @ {_ts()} ===\n")
        for ln in lines:
            fh.write(ln.rstrip() + "\n")
