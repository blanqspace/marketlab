from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Sequence

from rich.console import Console

from marketlab.bootstrap.env import load_env
from marketlab.core.status import events_tail_agg
from marketlab.core.status import queue_depth as _queue_depth
from marketlab.ipc import bus
from marketlab.settings import AppSettings, get_settings

# Ensure .env is loaded early and mirror legacy env keys
try:
    load_env(mirror=True)
except Exception:
    pass

# --- Process wrapper ---------------------------------------------------------

@dataclass
class Proc:
    name: str
    args: list[str]
    env: dict[str, str]
    creationflags: int = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    popen: subprocess.Popen | None = None

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

    def pid(self) -> int | None:
        return int(self.popen.pid) if self.popen else None


# --- Utilities ---------------------------------------------------------------

def _root_dir() -> Path:
    # src/marketlab/supervisor.py -> repo root is parent of src
    return Path(__file__).resolve().parents[2]


def abs_ipc_db(root: Path) -> str:
    rt = root / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    return str((rt / "ctl.db").resolve())


def _with_path_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
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


def _get_status_for_cmd(db_path: str, cmd_id: str) -> str | None:
    con = sqlite3.connect(db_path)
    try:
        row = con.execute("SELECT status FROM commands WHERE cmd_id=?", (cmd_id,)).fetchone()
        return row[0] if row else None
    finally:
        con.close()


def health_ping(db_path: str, timeout_s: float = 3.0) -> dict[str, Any]:
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
    code = "from marketlab.daemon.worker import run_forever; run_forever()"
    args = [sys.executable, "-u", "-c", code]
    return Proc("worker", args, env)


def spawn_dashboard(db_path: str) -> Proc:
    env = _with_path_env({bus.DB_ENV: db_path})
    args = [sys.executable, "-m", "marketlab.tui.dashboard"]
    return Proc("dashboard", args, env)


def spawn_poller(db_path: str) -> Proc:
    """Spawn Telegram poller using current .env settings.

    Ensures same bus DB via IPC_DB and Python path.
    """
    env = _with_path_env({bus.DB_ENV: db_path})
    args = [sys.executable, "-m", "tools.tg_poller"]
    return Proc("poller", args, env)


_last_health: dict[str, Any] | None = None


def _statusline(db_path: str, worker: Proc | None, dash: Proc | None, poller: Proc | None = None) -> str:
    db_name = Path(db_path).name
    w_pid = worker.pid() if worker and worker.is_running() else None
    d_pid = dash.pid() if dash and dash.is_running() else None
    p_pid = poller.pid() if poller and poller.is_running() else None
    health_txt = "-" if _last_health is None else ("ok" if _last_health.get("ok") else "-")
    try:
        qd = _queue_depth(db_path)
    except Exception:
        qd = 0
    return f"DB={db_name}  worker={w_pid}  dashboard={d_pid}  poller={p_pid}  Health={health_txt}  QueueDepth={qd}"


def _print_header(db_path: str, worker: Proc | None, dash: Proc | None, poller: Proc | None) -> None:
    print(_statusline(db_path, worker, dash, poller))


def build_menu_panel(db_path: str, worker: Proc | None, dash: Proc | None, message: str = "", poller: Proc | None = None):
    """Construct a compact supervisor menu with statusline and optional one-line message."""
    from rich.panel import Panel
    from rich.table import Table
    status = _statusline(db_path, worker, dash, poller)
    tbl = Table.grid(padding=(0, 1))
    tbl.add_row(f"[bold]{status}[/bold]")
    tbl.add_row("")
    options = [
        "1 Start ALL",
        "2 Stop ALL",
        "3 Restart ALL",
        "4 Open Control-Menu",
        "5 Pause",
        "6 Resume",
        "7 Mode: Paper",
        "8 Mode: Live",
        "9 Confirm (Token/Index)",
        "10 Reject (Token/Index)",
        "11 Health Check",
        "r Refresh",
        "12 Tail Events (10)",
        "99 Exit",
    ]
    for line in options:
        tbl.add_row(line)
    if message:
        tbl.add_row("")
        tbl.add_row(f"[green]{message}[/green]")
    return Panel(tbl, title="Supervisor", border_style="cyan")


def enqueue(cmd: str, args: dict[str, Any]) -> str:
    """Enqueue without printing; used by supervisor dispatch."""
    return bus.enqueue(cmd, args, source="supervisor", ttl_sec=300)


def _resolve_token_or_index(arg: str) -> tuple[str, str | None]:
    """Return (mode, value). mode: 'token' or 'index'."""
    arg = (arg or "").strip()
    if not arg:
        return ("", None)
    if arg.isdigit():
        return ("index", arg)
    return ("token", arg)


def _resolve_token_from_index(idx_str: str) -> str | None:
    try:
        from marketlab.orders.store import list_tickets
    except Exception:
        return None
    try:
        idx = int(idx_str)
        rows: list[dict[str, Any]] = []
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



def dispatch(
    line: str,
    db_path: str,
    worker: Proc | None,
    dash: Proc | None,
    poller: Proc | None = None,
) -> tuple[Proc | None, Proc | None, Proc | None, str]:
    global _last_health
    """Dispatch a single menu choice; return updated procs and one-line message."""
    choice = (line or "").strip()
    if not choice:
        return worker, dash, poller, ""
    msg = ""
    head = choice.split()[0]
    if head == "1":
        ensure_bus(db_path)
        worker = worker or spawn_worker(db_path)
        dash = dash or spawn_dashboard(db_path)
        poller = poller or spawn_poller(db_path)
        if not worker.is_running():
            worker.start()
        if not dash.is_running():
            dash.start()
        if not poller.is_running():
            poller.start()
        msg = "OK: start all"
    elif head == "2":
        if worker:
            worker.stop(); worker = None
        if dash:
            dash.stop(); dash = None
        if poller:
            poller.stop(); poller = None
        msg = "OK: stop all"
    elif head == "3":
        if worker:
            worker.stop(); worker = None
        if dash:
            dash.stop(); dash = None
        if poller:
            poller.stop(); poller = None
        time.sleep(0.2)
        ensure_bus(db_path)
        worker = spawn_worker(db_path); worker.start()
        dash = spawn_dashboard(db_path); dash.start()
        poller = spawn_poller(db_path); poller.start()
        msg = "OK: restart all"
    elif head == "4":
        env = _with_path_env({bus.DB_ENV: db_path})
        subprocess.Popen([sys.executable, "-m", "marketlab", "control-menu"], env=env, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        msg = "OK: open control-menu"
    elif head == "5":
        enqueue("state.pause", {})
        msg = "OK: state.pause"
    elif head == "6":
        enqueue("state.resume", {})
        msg = "OK: state.resume"
    elif head == "7":
        enqueue("mode.switch", {"target": "paper", "args": {"symbols": ["AAPL"], "timeframe": "1m"}})
        msg = "OK: mode.paper"
    elif head == "8":
        enqueue("mode.switch", {"target": "live", "args": {"symbols": ["AAPL"], "timeframe": "1m"}})
        msg = "OK: mode.live"
    elif head == "9":
        arg = "".join(choice.split()[1:]) or input("Token/Index: ").strip()
        mode, val = _resolve_token_or_index(arg)
        tok = val if mode == "token" else _resolve_token_from_index(val or "")
        if tok:
            enqueue("orders.confirm", {"token": tok})
            msg = f"OK: orders.confirm -> {tok}"
        else:
            msg = "ERR: ungültig"
    elif head == "10":
        arg = "".join(choice.split()[1:]) or input("Token/Index: ").strip()
        yn = input("Sicher ablehnen? (y/n): ").strip().lower()
        if yn != "y":
            msg = "abgebrochen"
            return worker, dash, poller, msg
        mode, val = _resolve_token_or_index(arg)
        tok = val if mode == "token" else _resolve_token_from_index(val or "")
        if tok:
            enqueue("orders.reject", {"token": tok})
            msg = f"OK: orders.reject -> {tok}"
        else:
            msg = "ERR: ungültig"
    elif head == "11":
        res = health_ping(db_path, timeout_s=3)
        _last_health = res
        try:
            q = _queue_depth(db_path)
        except Exception:
            q = 0
        msg = f"health ok={bool(res.get('ok'))} queue={q}"
        if not res.get("ok"):
            if not (worker and worker.is_running()):
                worker = spawn_worker(db_path)
                worker.start()
    elif head.lower() == "r":
        # Recompute health and queue depth without side effects
        try:
            res = health_ping(db_path, timeout_s=1.0)
        except Exception:
            res = {"ok": False}
        _last_health = res
        _ = _queue_depth(db_path)  # compute to reflect in statusline next render
        msg = "OK: refresh"
    elif head == "12":
        try:
            ag = events_tail_agg(db_path, n=50)
        except Exception:
            ag = []
        for e in ag[:10]:
            ts = e.get("ts", "-")
            lvl = e.get("level", "-")
            m0 = e.get("message", "-")
            cnt = int(e.get("count", 1) or 1)
            suffix = f" x{cnt}" if cnt > 1 else ""
            print(f"{ts} {lvl} {m0}{suffix}")
        input("Weiter [Enter]")
    elif head == "99":
        if worker:
            worker.stop(); worker = None
        if dash:
            dash.stop(); dash = None
        raise SystemExit(0)
    else:
        msg = "unbekannte Auswahl"
    return worker, dash, poller, (msg or "").replace("\n", " ").strip()


def _mask_token(token: str | None) -> str:
    if not token:
        return "-"
    try:
        parts = str(token).split(":", 1)
        if len(parts) == 2 and parts[0].isdigit():
            return f"{parts[0]}:****"
        return (str(token)[:4] + "****") if token else "-"
    except Exception:
        return "-"


def _summary_line(settings: AppSettings) -> str:
    try:
        token_value = settings.telegram.bot_token.get_secret_value() if settings.telegram.bot_token else None
    except Exception:
        token_value = str(settings.telegram.bot_token) if settings.telegram.bot_token else None
    allow_cnt = len(settings.telegram.allowlist or [])
    brand = getattr(settings, "app_brand", "MarketLab")
    mode = getattr(settings, "env_mode", "DEV")
    db_name = os.path.basename(settings.ipc_db)
    return (
        f"config.summary brand={brand} mode={mode} db={db_name} "
        f"tg.enabled={'1' if settings.telegram.enabled else '0'} "
        f"tg.mock={'1' if settings.telegram.mock else '0'} "
        f"tg.chat={settings.telegram.chat_control or '-'} "
        f"tg.allow={allow_cnt} tg.token={_mask_token(token_value)}"
    )


def _health_check(db_path: str, timeout_s: float = 2.0) -> None:
    result = health_ping(db_path, timeout_s=timeout_s)
    ok_txt = "1" if result.get("ok") else "0"
    status = result.get("status", "-")
    events = result.get("events", 0)
    print(f"supervisor.health ok={ok_txt} status={status} events={events}", flush=True)


def _bus_poll_once(db_path: str) -> None:
    depth = int(_queue_depth(db_path))
    print(f"supervisor.bus queue_depth={depth}", flush=True)


def _kpis_update(db_path: str) -> None:
    events = events_tail_agg(db_path, n=5) or []
    latest = events[0] if events else {}
    level = latest.get("level", "-")
    latest_msg = str(latest.get("message", "-")).replace("\n", " ")[:80]
    count = len(events)
    print(f"supervisor.kpis events={count} latest_level={level} latest_msg={latest_msg}", flush=True)


def _stop_path() -> Path:
    root = _root_dir()
    stop_file = root / "runtime" / "stop"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    return stop_file


def run_daemon(interval: float) -> None:
    root = _root_dir()
    db_path = abs_ipc_db(root)
    os.environ[bus.DB_ENV] = db_path
    ensure_bus(db_path)
    stop_file = _stop_path()

    running = True

    def _sig_handler(*_: object) -> None:
        nonlocal running
        running = False

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    while running:
        if stop_file.exists():
            running = False
            break
        try:
            print(_summary_line(get_settings()), flush=True)
        except Exception as e:  # pragma: no cover
            print(f"supervisor.summary.error {e}", flush=True)
        try:
            _health_check(db_path)
        except Exception as e:  # pragma: no cover
            print(f"supervisor.health.error {e}", flush=True)
        try:
            _bus_poll_once(db_path)
        except Exception as e:  # pragma: no cover
            print(f"supervisor.bus.error {e}", flush=True)
        try:
            _kpis_update(db_path)
        except Exception as e:  # pragma: no cover
            print(f"supervisor.kpis.error {e}", flush=True)
        if stop_file.exists():
            running = False
            break
        deadline = time.time() + interval
        while running and time.time() < deadline:
            if stop_file.exists():
                running = False
                break
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.25, remaining))
    print("supervisor.stop", flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="marketlab.supervisor")
    parser.add_argument("--interval", type=float, default=2.0, help="Loop sleep interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Run a single supervisor cycle and exit.")
    args = parser.parse_args(argv)

    interval = max(float(args.interval), 0.1)
    if args.once:
        return 0

    try:
        run_daemon(interval=interval)
    except KeyboardInterrupt:
        print("supervisor.stop", flush=True)
    return 0


def run_supervisor() -> None:
    """Interactive static supervisor menu without Live rendering."""
    root = _root_dir()
    db_path = abs_ipc_db(root)
    os.environ[bus.DB_ENV] = db_path

    worker: Proc | None = None
    dash: Proc | None = None
    poller: Proc | None = None
    last_msg: str = ""

    console = Console(force_terminal=True, color_system="truecolor")
    while True:
        console.clear()
        print(_statusline(db_path, worker, dash, poller))
        print("1 Start ALL")
        print("2 Stop ALL")
        print("3 Restart ALL")
        print("4 Open Control-Menu")
        print("5 Pause")
        print("6 Resume")
        print("7 Mode: Paper")
        print("8 Mode: Live")
        print("9 Confirm (Token/Index)")
        print("10 Reject (Token/Index)")
        print("11 Health Check")
        print("r Refresh")
        print("12 Tail Events (10)")
        print("99 Exit")
        if last_msg:
            print(last_msg)
        try:
            choice = input("Auswahl: ").strip()
        except EOFError:
            break
        worker, dash, poller, last_msg = dispatch(choice, db_path, worker, dash, poller)


# Expose helpers for tests
__all__ = [
    "Proc",
    "abs_ipc_db",
    "ensure_bus",
    "health_ping",
    "enqueue",
    "spawn_worker",
    "spawn_dashboard",
    "spawn_poller",
    "dispatch",
    "run_supervisor",
    "_statusline",
    "run_daemon",
    "main",
]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
