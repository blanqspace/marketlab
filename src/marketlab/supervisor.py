from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Optional, Dict, Any, Tuple, List

from src.marketlab.ipc import bus
from src.marketlab.settings import get_settings


# --- Process wrapper ---------------------------------------------------------

@dataclass
class Proc:
    name: str
    args: List[str]
    env: Dict[str, str]
    creationflags: int = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    popen: Optional[subprocess.Popen] = None

    def start(self) -> int:
        if self.is_running():
            return int(self.popen.pid)  # type: ignore[arg-type]
        # Ensure same env + overrides
        proc_env = os.environ.copy()
        proc_env.update(self.env or {})
        self.popen = subprocess.Popen(
            self.args,
            env=proc_env,
            creationflags=self.creationflags,
        )
        return int(self.popen.pid)

    def stop(self) -> None:
        if not self.popen:
            return
        try:
            if self.is_running():
                self.popen.terminate()
                try:
                    self.popen.wait(timeout=2)
                except Exception:
                    self.popen.kill()
        finally:
            self.popen = None

    def is_running(self) -> bool:
        return bool(self.popen and self.popen.poll() is None)

    def pid(self) -> Optional[int]:
        return int(self.popen.pid) if self.popen else None


# --- Utilities ---------------------------------------------------------------

def _root_dir() -> Path:
    # src/marketlab/supervisor.py -> repo root is parent of src
    return Path(__file__).resolve().parents[2]


def abs_ipc_db(root: Path) -> str:
    rt = root / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    return str((rt / "ctl.db").resolve())


def _with_path_env(base_env: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = dict(base_env or {})
    root = _root_dir()
    src_path = str((root / "src").resolve())
    existing = os.environ.get("PYTHONPATH") or env.get("PYTHONPATH") or ""
    if existing:
        env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}"
    else:
        env["PYTHONPATH"] = src_path
    return env


def ensure_bus(db_path: str) -> None:
    # Use env to point bus to the correct DB
    os.environ[bus.DB_ENV] = db_path
    bus.bus_init()


def _get_status_for_cmd(db_path: str, cmd_id: str) -> Optional[str]:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT status FROM commands WHERE cmd_id=?", (cmd_id,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def health_ping(db_path: str, timeout_s: float = 3.0) -> Dict[str, Any]:
    """Enqueue a state.pause and wait until processed or timeout.

    Returns: { 'ok': bool, 'status': 'DONE'|'NEW'|'ERROR', 'events': int }
    """
    os.environ[bus.DB_ENV] = db_path
    bus.bus_init()
    cmd_id = bus.enqueue("state.pause", {}, source="supervisor", ttl_sec=30)

    status = "NEW"
    deadline = time.time() + float(timeout_s)
    while time.time() < deadline:
        st = _get_status_for_cmd(db_path, cmd_id)
        if st in ("DONE", "ERROR"):
            status = st
            break
        time.sleep(0.1)
    else:
        # fell through timeout without update
        status = _get_status_for_cmd(db_path, cmd_id) or "NEW"

    events = bus.tail_events(10) or []
    return {"ok": status == "DONE", "status": status, "events": len(events)}


def spawn_worker(db_path: str) -> Proc:
    s = get_settings()
    env = {
        bus.DB_ENV: db_path,
        "ORDERS_TWO_MAN_RULE": "1" if s.orders_two_man_rule else "0",
        "CONFIRM_STRICT": "1" if s.confirm_strict else "0",
    }
    env = _with_path_env(env)
    # Use -c to call run_forever, as module has no __main__
    code = "from src.marketlab.daemon.worker import run_forever; run_forever()"
    args = [sys.executable, "-u", "-c", code]
    return Proc("worker", args, env)


def spawn_dashboard(db_path: str) -> Proc:
    env = _with_path_env({bus.DB_ENV: db_path})
    args = [sys.executable, "-m", "tools.tui_dashboard"]
    return Proc("dashboard", args, env)


def _print_header(db_path: str, worker: Optional[Proc], dash: Optional[Proc]) -> None:
    root = _root_dir()
    db_name = Path(db_path).name
    w_pid = worker.pid() if worker and worker.is_running() else None
    d_pid = dash.pid() if dash and dash.is_running() else None
    print(f"DB={db_name}  root={root}")
    print(f"worker PID={w_pid}  dashboard PID={d_pid}")


def _enqueue(cmd: str, args: Dict[str, Any]) -> str:
    cid = bus.enqueue(cmd, args, source="supervisor", ttl_sec=300)
    print(json.dumps({"enqueued": cmd, "cmd_id": cid}))
    return cid


def _resolve_token_or_index(arg: str) -> Tuple[str, Optional[str]]:
    """Return (mode, value). mode: 'token' or 'index'."""
    arg = (arg or "").strip()
    if not arg:
        return ("", None)
    if arg.isdigit():
        return ("index", arg)
    return ("token", arg)


def _resolve_token_from_index(idx_str: str) -> Optional[str]:
    try:
        from src.marketlab.orders.store import list_tickets
    except Exception:
        return None
    try:
        idx = int(idx_str)
        rows: List[Dict[str, Any]] = []
        for st in ("PENDING", "CONFIRMED_TG", "CONFIRMED"):
            part = list_tickets(st) or []
            rows.extend(part)
        if not rows:
            return None
        if 1 <= idx <= len(rows):
            tok = rows[idx - 1].get("token")
            return str(tok) if tok else None
        return None
    except Exception:
        return None


def _handle_menu_input(line: str, db_path: str, worker: Optional[Proc], dash: Optional[Proc]) -> Tuple[Optional[Proc], Optional[Proc]]:
    choice = (line or "").strip()
    if not choice:
        return worker, dash
    match choice.split()[0]:
        case "1":
            ensure_bus(db_path)
            worker = worker or spawn_worker(db_path)
            dash = dash or spawn_dashboard(db_path)
            if not worker.is_running():
                worker.start()
            if not dash.is_running():
                dash.start()
            print("started: worker + dashboard")
        case "2":
            if worker:
                worker.stop(); worker = None
            if dash:
                dash.stop(); dash = None
            print("stopped: worker + dashboard")
        case "3":
            if worker:
                worker.stop(); worker = None
            if dash:
                dash.stop(); dash = None
            time.sleep(0.2)
            ensure_bus(db_path)
            worker = spawn_worker(db_path); worker.start()
            dash = spawn_dashboard(db_path); dash.start()
            print("restarted: worker + dashboard")
        case "4":
            # open control-menu in new console
            env = _with_path_env({bus.DB_ENV: db_path})
            subprocess.Popen([sys.executable, "-m", "marketlab", "control-menu"], env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
            print("opened: control-menu")
        case "5":
            _enqueue("state.pause", {})
        case "6":
            _enqueue("state.resume", {})
        case "7":
            _enqueue("mode.switch", {"target": "paper", "args": {"symbols": ["AAPL"], "timeframe": "1m"}})
        case "8":
            _enqueue("mode.switch", {"target": "live", "args": {"symbols": ["AAPL"], "timeframe": "1m"}})
        case "9":
            arg = "".join(choice.split()[1:]) or input("Token oder Index: ").strip()
            mode, val = _resolve_token_or_index(arg)
            tok = val if mode == "token" else _resolve_token_from_index(val or "")
            if tok:
                _enqueue("orders.confirm", {"token": tok})
            else:
                print("keine gültige Eingabe")
        case "10":
            arg = "".join(choice.split()[1:]) or input("Token oder Index: ").strip()
            yn = input("Sicher ablehnen? (y/n): ").strip().lower()
            if yn != "y":
                print("abgebrochen")
                return worker, dash
            mode, val = _resolve_token_or_index(arg)
            tok = val if mode == "token" else _resolve_token_from_index(val or "")
            if tok:
                _enqueue("orders.reject", {"token": tok})
            else:
                print("keine gültige Eingabe")
        case "11":
            res = health_ping(db_path, timeout_s=3)
            print(json.dumps(res))
            if not res.get("ok"):
                # self-heal: if worker is down, restart worker only
                if not (worker and worker.is_running()):
                    worker = spawn_worker(db_path)
                    worker.start()
                    print("worker restarted")
                else:
                    print("Warnung: Commands bleiben NEW. Prüfe IPC_DB in allen Fenstern.")
        case "12":
            evs = bus.tail_events(10) or []
            for e in evs:
                ts = getattr(e, "ts", "-")
                lvl = getattr(e, "level", "-")
                msg = getattr(e, "message", "-")
                print(f"{ts} {lvl} {msg}")
        case "99":
            if worker:
                worker.stop(); worker = None
            if dash:
                dash.stop(); dash = None
            print("exit")
            raise SystemExit(0)
        case _:
            print("unbekannte Auswahl")
    return worker, dash


def run_supervisor() -> None:
    root = _root_dir()
    db_path = abs_ipc_db(root)
    os.environ[bus.DB_ENV] = db_path

    worker: Optional[Proc] = None
    dash: Optional[Proc] = None

    while True:
        _print_header(db_path, worker, dash)
        print(
            """
1 Start All
2 Stop All
3 Restart All
4 Open Control-Menu
5 Pause
6 Resume
7 Mode: Paper
8 Mode: Live
9 Confirm (Token/Index)
10 Reject  (Token/Index)
11 Health Check
12 Tail Events
99 Exit
""".strip()
        )
        try:
            line = input(
                "Auswahl: "
            )
        except EOFError:
            break
        worker, dash = _handle_menu_input(line, db_path, worker, dash)


# Expose helpers for tests
__all__ = [
    "Proc",
    "abs_ipc_db",
    "ensure_bus",
    "health_ping",
    "spawn_worker",
    "spawn_dashboard",
    "run_supervisor",
]
