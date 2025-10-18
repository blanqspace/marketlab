import json, time
from pathlib import Path

RUNTIME_DIR = Path("runtime")

def _ensure_runtime():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

def read_runtime_state():
    _ensure_runtime()
    p = RUNTIME_DIR / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def write_runtime_state(state: dict):
    _ensure_runtime()
    (RUNTIME_DIR / "state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def write_heartbeat(loop_enabled: bool, safe_mode: bool, last_run_id: str|None):
    _ensure_runtime()
    hb = {"ts": int(time.time()), "loop_enabled": loop_enabled, "safe_mode": safe_mode, "last_run_id": last_run_id}
    (RUNTIME_DIR / "heartbeat.json").write_text(
        json.dumps(hb, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

def ensure_reports_dir(kind: str):
    d = Path("reports") / kind
    d.mkdir(parents=True, exist_ok=True)
    return d
