# shared/diag/report.py
from __future__ import annotations
import json, os, uuid
from pathlib import Path
from datetime import datetime, timezone, date
from typing import Any, Dict, Iterable, Tuple, Optional
from collections import Counter

ROOT   = Path(__file__).resolve().parents[2]
EV_DIR = ROOT / "reports" / "events"
SM_DIR = ROOT / "reports" / "summary"
RT_DIR = ROOT / "runtime"
EV_DIR.mkdir(parents=True, exist_ok=True)
SM_DIR.mkdir(parents=True, exist_ok=True)
RT_DIR.mkdir(parents=True, exist_ok=True)

SESSION_FILE = RT_DIR / "session_id.txt"

def _ts(dt: Optional[datetime]=None) -> str:
    return (dt or datetime.now(timezone.utc)).isoformat(timespec="seconds")

def _datestr(d: Optional[date]=None) -> str:
    d = d or datetime.now(timezone.utc).date()
    return d.strftime("%Y%m%d")

def _today_paths(day: Optional[datetime]=None) -> Tuple[Path, Path, Path]:
    d = (day or datetime.now(timezone.utc)).date()
    ds = _datestr(d)
    ev_file  = EV_DIR / f"{ds}.jsonl"
    txt_file = SM_DIR / f"{ds}.txt"
    json_file= SM_DIR / f"{ds}.json"
    return ev_file, txt_file, json_file

# ── Session Steuerung ───────────────────────────────────────────────────────
def start_session(session_id: Optional[str]=None) -> str:
    sid = session_id or uuid.uuid4().hex[:12]
    SESSION_FILE.write_text(sid, encoding="utf-8")
    os.environ["ROBUST_SESSION_ID"] = sid
    return sid

def current_session() -> str:
    sid = os.environ.get("ROBUST_SESSION_ID")
    if sid:
        return sid
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text(encoding="utf-8").strip()
    return start_session()

# ── Events API ──────────────────────────────────────────────────────────────
def append_event(kind: str, payload: Dict[str, Any] | None = None) -> None:
    ev_file, _, _ = _today_paths(None)
    ev = {
        "ts": _ts(),
        "session": current_session(),
        "kind": str(kind),
        "payload": payload or {}
    }
    with ev_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ev, ensure_ascii=False) + "\n")

def _read_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except Exception:
                continue
    return out

# ── Aggregation/Stats ──────────────────────────────────────────────────────
def _counter_pairs(counter: Counter, top_n: int = 5) -> list[tuple[str, int]]:
    return [(k, counter[k]) for k in counter.most_common(top_n)]

def compute_session_stats(day: Optional[datetime]=None, session_id: Optional[str]=None) -> Dict[str, Any]:
    ev_file, _, _ = _today_paths(day)
    events_all = _read_jsonl(ev_file)
    sid = session_id or current_session()

    # Nur Events der Session
    events = [e for e in events_all if e.get("session") == sid]

    orders_sent = orders_errors = orders_autocancel = orders_dryrun = 0
    order_statuses: Counter = Counter()
    order_symbols: Counter = Counter()

    data_ingests = data_errors = 0
    data_symbols: Counter = Counter()
    data_bars: Counter = Counter()
    data_durations: Counter = Counter()

    bt_total = 0
    bt_by_kind: Counter = Counter()
    error_msgs: Counter = Counter()

    for ev in events:
        kind = ev.get("kind", "")
        p = ev.get("payload", {}) or {}

        if kind == "order_sent":
            orders_sent += 1
            sym = (p.get("symbol") or "").upper()
            if sym:
                order_symbols[sym] += 1
            st = p.get("status")
            if st:
                order_statuses[st] += 1

        elif kind == "order_error":
            orders_errors += 1
            error_msgs[p.get("message") or p.get("error") or "order_error"] += 1

        elif kind == "order_autocancel":
            orders_autocancel += 1

        elif kind == "order_dryrun":
            orders_dryrun += 1

        elif kind == "data_ingest":
            data_ingests += 1
            sym = (p.get("symbol") or "").upper()
            if sym:
                data_symbols[sym] += 1
            if p.get("barsize"):   data_bars[p["barsize"]] += 1
            if p.get("duration"):  data_durations[p["duration"]] += 1

        elif kind == "data_error":
            data_errors += 1
            error_msgs[p.get("message") or p.get("error") or "data_error"] += 1

        elif kind == "backtest":
            bt_total += 1
            bt_by_kind[p.get("strategy") or "unknown"] += 1

        elif kind == "error":
            error_msgs[p.get("message") or "error"] += 1

    return {
        "session": sid,
        "orders": {
            "sent": orders_sent,
            "errors": orders_errors,
            "autocancel": orders_autocancel,
            "dryrun": orders_dryrun,
            "top_symbols": _counter_pairs(order_symbols),
            "statuses": dict(order_statuses),
        },
        "data": {
            "ingests": data_ingests,
            "errors": data_errors,
            "top_symbols": _counter_pairs(data_symbols),
            "top_barsizes": _counter_pairs(data_bars),
            "top_durations": _counter_pairs(data_durations),
        },
        "backtests": {
            "total": bt_total,
            "by_kind": dict(bt_by_kind),
        },
        "errors_top": _counter_pairs(error_msgs),
    }

# ── Session-Report (nur diese Sitzung) ─────────────────────────────────────
def write_session_summary(title: str, lines: list[str] | None = None, day: datetime | None = None):
    ev_file, txt_file, json_file = _today_paths(day)
    stats = compute_session_stats(day)

    # Session-Dateien (eindeutig pro Lauf)
    sid = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    sess_dir = SM_DIR / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    sess_txt = sess_dir / f"{sid}.txt"
    sess_json = sess_dir / f"{sid}.json"

    # Text-Report NUR für diese Sitzung
    with sess_txt.open("w", encoding="utf-8") as fh:
        fh.write(f"=== {title} @ {_ts()} ===\n")

        o = stats.get("orders", {})
        d = stats.get("data", {})
        b = stats.get("backtests", {})

        fh.write(
            f"Orders: sent={o.get('sent', 0)}  errors={o.get('errors', 0)}  "
            f"autocancel={o.get('autocancel', 0)}  dryrun={o.get('dryrun', 0)}\n"
        )

        top_syms = o.get("top_symbols") or []
        if top_syms:
            fh.write("Top Symbole (Orders): " + ", ".join([f"{s}×{n}" for s, n in top_syms]) + "\n")

        statuses = o.get("statuses") or {}
        if statuses:
            fh.write("Statuses: " + ", ".join([f"{k}:{v}" for k, v in statuses.items()]) + "\n")

        fh.write(f"Datenabrufe: {d.get('ingests', 0)}  errors={d.get('errors', 0)}\n")

        d_syms = d.get("top_symbols") or []
        if d_syms:
            fh.write("Top Symbole (Data): " + ", ".join([f"{s}×{n}" for s, n in d_syms]) + "\n")

        d_bars = d.get("top_barsizes") or []
        if d_bars:
            fh.write("Barsizes: " + ", ".join([f"{s}×{n}" for s, n in d_bars]) + "\n")

        d_durs = d.get("top_durations") or []
        if d_durs:
            fh.write("Durations: " + ", ".join([f"{s}×{n}" for s, n in d_durs]) + "\n")

        fh.write(f"Backtests: total={b.get('total', 0)}")
        by_kind = b.get("by_kind") or {}
        if by_kind:
            fh.write("  by_kind: " + ", ".join([f"{k}:{v}" for k, v in by_kind.items()]))
        fh.write("\n")

        errors_top = stats.get("errors_top") or []
        if errors_top:
            fh.write("Fehler (Top): " + "; ".join([f"{m}×{c}" for m, c in errors_top]) + "\n")

        if lines:
            for ln in lines:
                fh.write(ln.rstrip() + "\n")

        fh.write(f"Events:  {ev_file}\n")
        fh.write(f"JSON:    {sess_json}\n")

    # JSON-Report NUR für diese Sitzung
    with sess_json.open("w", encoding="utf-8") as jf:
        json.dump(stats, jf, indent=2, ensure_ascii=False)

    # Tages-Summary: nur Verweis auf Session + aktuelles Tages-JSON
    txt_file.parent.mkdir(parents=True, exist_ok=True)
    with txt_file.open("a", encoding="utf-8") as fh:
        fh.write(f"\n=== {title} @ {_ts()} ===\n")
        fh.write("Siehe Session: " + str(sess_txt) + "\n")

    json_file.parent.mkdir(parents=True, exist_ok=True)
    with json_file.open("w", encoding="utf-8") as jf:
        json.dump(stats, jf, indent=2, ensure_ascii=False)

    return {
        "session_txt": sess_txt,
        "session_json": sess_json,
        "day_txt": txt_file,
        "day_json": json_file,
        "events": ev_file,
    }
