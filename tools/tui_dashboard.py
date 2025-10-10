"""Text-only Rich TUI: stdin-only command interface (no hotkeys).

Commands (type and press Enter):
- status | s
- pause | p
- resume | r
- stop | x
- quit | q
- orders list
- orders confirm --all  (PENDING + CONFIRMED_TG → CONFIRMED)
- orders confirm <ORDER_ID>
- orders reject <ORDER_ID>
"""

import sys, threading, queue, time, json
import os, tempfile, hashlib
from typing import Any
from collections import deque
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich import box
from src.marketlab.core.status import snapshot
from src.marketlab.orders.store import list_tickets, set_state, first_by_state

print("Starting TUI dashboard…", flush=True)


CMDQ = queue.Queue()
LAST_MSG = ""
LOG_LINES = deque(maxlen=200)
LAST_HASH = None
LAST_HEARTBEAT = 0.0
LAST_HEADER_TICK = 0.0
LAST_COUNTS = {}
HEART_FRAMES = ["·", "∙", "•", "∙"]

LOCK = os.path.join(tempfile.gettempdir(), "marketlab_tui.lock")
console = Console(force_terminal=True, color_system="truecolor")


def _s(x: Any) -> str:
    # Schutz: Ellipsis, None, Nicht-Strings → String
    if x is Ellipsis:
        return "…"
    try:
        return str(x)
    except Exception:
        return "<unprintable>"


def log(msg: str, level: str = "info"):
    try:
        ts = snapshot().get('ts', "--")
    except Exception:
        ts = "--"
    colors = {"info": "white", "ok": "green", "warn": "yellow", "err": "red"}
    color = colors.get(level, "white")
    LOG_LINES.appendleft(f"[{color}] [{_s(ts)}] {_s(msg)}[/]")


# stable hash über wesentliche Teile zur Change-Erkennung
def _state_hash():
    s = snapshot()
    key = json.dumps({
        "counts": s["orders"]["counts"],
        "run_state": s["run_state"],
        "mode": s["mode"],
        "tg": s["telegram"],
        "processed": s.get("processed"),
    }, sort_keys=True)
    return hashlib.md5(key.encode()).hexdigest()


def _header():
    s = {}
    try:
        s = snapshot() or {}
    except Exception:
        pass
    t = Table.grid(expand=True)
    t.add_column(justify="left"); t.add_column(justify="right")

    # Heartbeat frame (changes every 0.5s)
    hb = HEART_FRAMES[int(time.time() * 2) % len(HEART_FRAMES)]

    # Colored run state
    state = s.get('run_state', 'UNKNOWN')
    state_color = {
        'RUN': 'green',
        'PAUSE': 'yellow',
        'EXIT': 'red',
    }.get(state, 'white')

    # Left: mode, colored state, processed, heartbeat
    left = (
        f"Mode: {_s(s.get('mode','-'))} | "
        f"[bold {state_color}]State: {_s(state)}[/bold {state_color}] | "
        f"Processed: {_s(s.get('processed','-'))} {hb}"
    )

    # Right: TG status + mock flag + live UTC clock
    tg = s.get('telegram', {}) or {}
    tg_text = (
        "TG: [green]enabled[/]" if tg.get('enabled') else "TG: [red]disabled[/]"
    )
    time_text = f"[cyan]{time.strftime('%H:%M:%S UTC', time.gmtime())}[/cyan]"
    right = f"{tg_text} | mock: {'[yellow]true[/]' if tg.get('mock') else '[red]false[/]'} | {time_text}"

    t.add_row(left, right)
    return Panel(t, title="MarketLab Dashboard", border_style="cyan", padding=(1,2))


def _orders_panel():
    tbl = Table(box=box.SIMPLE_HEAVY, expand=True)
    tbl.add_column("ID", overflow="fold", max_width=34)
    tbl.add_column("Symbol"); tbl.add_column("Side"); tbl.add_column("Qty"); tbl.add_column("Type"); tbl.add_column("State")
    rows = []
    for st in ("PENDING","CONFIRMED_TG","CONFIRMED"):
        try:
            rows.extend(list_tickets(st) or [])
        except Exception:
            pass
    for t in rows[:20]:
        tbl.add_row(
            _s(t.get("id")), _s(t.get("symbol")), _s(t.get("side")),
            _s(t.get("qty")), _s(t.get("type")), _s(t.get("state"))
        )
    return Panel(tbl, title="Orders (Top 20)")


def _events_panel():
    global LAST_MSG
    try:
        s = snapshot() or {}
    except Exception:
        s = {}
    counts = s.get('orders', {}).get('counts', {})
    pending_preview = s.get('orders', {}).get('pending_preview', [])

    # Build a single markup-enabled string to avoid flicker
    lines = []
    lines.append(f"Counts: {_s(counts)}")
    lines.append(f"Pending: {len(pending_preview)} shown")
    lines.append("")
    lines.append("Type commands and press Enter")
    lines.append("Commands: status|s, pause|p, resume|r, stop|x, quit|q,")
    lines.append("          orders list | orders confirm --all | orders confirm <ID> | orders reject <ID>")
    lines.append("")
    if LAST_MSG:
        lines.append(f"Result: {_s(LAST_MSG)}")
        lines.append("")

    # last 10 logs with colors
    for ln in list(LOG_LINES)[:10]:
        lines.append(_s(ln))

    content = "\n".join(_s(x) for x in lines)
    return Panel(content, title="Events / Command")


def render():
    lo = Layout()
    lo.split_column(
        Layout(_header(), size=5),
        Layout(name="body")
    )
    lo["body"].split_row(
        Layout(_orders_panel(), ratio=3),
        Layout(_events_panel(), ratio=2)
    )
    return lo


def _confirm_first():
    t = first_by_state("CONFIRMED_TG") or first_by_state("PENDING")
    if t:
        set_state(t["id"], "CONFIRMED")
    return t


def _reject_first():
    t = first_by_state("PENDING") or first_by_state("CONFIRMED_TG")
    if t:
        set_state(t["id"], "REJECTED")
    return t


def _handle_command(cmd: str) -> str:
    parts = cmd.strip().split()
    if not parts:
        return "noop"

    head = parts[0].lower()

    if head in ("q", "quit"):
        return "__QUIT__"
    if head in ("x", "stop"):
        from src.marketlab.core.state_manager import STATE
        STATE.set_state("EXIT")
        log("stop requested")
        return "__QUIT__"
    if head in ("s", "status"):
        log("status requested", level="info")
        return "status logged"
    if head in ("p", "pause"):
        from src.marketlab.core.state_manager import STATE
        STATE.set_state("PAUSE")
        log("paused")
        return "paused"
    if head in ("r", "resume"):
        from src.marketlab.core.state_manager import STATE
        STATE.set_state("RUN")
        log("resumed")
        return "resumed"

    if head == "orders":
        if len(parts) >= 2 and parts[1] == "list":
            rows = sum([list_tickets(st) for st in ("PENDING","CONFIRMED_TG","CONFIRMED","REJECTED","CANCELED","EXECUTED")], [])
            n = len(rows)
            log(f"orders list -> {n}", level="info")
            return f"{n} orders"
        if len(parts) >= 3 and parts[1] == "confirm":
            if parts[2] == "--all":
                n = 0
                for t in list_tickets("PENDING"):
                    set_state(t["id"], "CONFIRMED"); n += 1
                for t in list_tickets("CONFIRMED_TG"):
                    set_state(t["id"], "CONFIRMED"); n += 1
                log(f"orders confirm --all -> {n}", level="ok")
                return f"confirmed {n}"
            set_state(parts[2], "CONFIRMED")
            log(f"confirmed {parts[2]}", level="ok")
            return f"confirmed {parts[2]}"
        if len(parts) >= 3 and parts[1] == "reject":
            set_state(parts[2], "REJECTED")
            log(f"rejected {parts[2]}", level="warn")
            return f"rejected {parts[2]}"
        return "orders: unknown subcommand"

    # Convenience commands map to confirm/reject first
    if head == "confirm":
        t = _confirm_first()
        if t:
            log(f"confirm first {t['id']}", level="ok")
            return "confirm first"
        return "no pending"
    if head == "reject":
        t = _reject_first()
        if t:
            log(f"reject first {t['id']}", level="warn")
            return "reject first"
        return "no pending"

    return "unknown command"


def _input_reader():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                time.sleep(0.1); continue
            line = line.strip()
            if line:
                CMDQ.put(line)
        except Exception:
            time.sleep(0.2)


def main():
    global LAST_MSG, LAST_HASH, LAST_HEARTBEAT, LAST_COUNTS, LAST_HEADER_TICK
    # single-instance guard
    if os.path.exists(LOCK):
        return
    open(LOCK, "w").close()

    t = threading.Thread(target=_input_reader, daemon=True)
    t.start()
    LAST_HASH = _state_hash()
    LAST_HEARTBEAT = time.time()
    LAST_HEADER_TICK = time.time()
    try:
        with Live(render(), refresh_per_second=4, screen=False, auto_refresh=False, transient=False, console=console) as live:
            while True:
                # process commands
                try:
                    cmd = CMDQ.get_nowait()
                    res = _handle_command(cmd)
                    if res == "__QUIT__":
                        log("exiting", level="info")
                        LAST_MSG = "exiting"
                        try:
                            live.update(render(), refresh=True)
                        except Exception as e:
                            console.print(f"[red]Render error:[/] {_s(e)}")
                            break
                        break
                    LAST_MSG = res
                    try:
                        live.update(render(), refresh=True)
                    except Exception as e:
                        console.print(f"[red]Render error:[/] {_s(e)}")
                        break
                except queue.Empty:
                    pass
                # Zustand prüfen (hash-basiert) + Heartbeat
                try:
                    h = _state_hash()
                except Exception:
                    h = None
                now = time.time()
                # Count delta logging on state change
                try:
                    if h is not None and h != LAST_HASH:
                        s2 = snapshot()
                        cur_counts = s2.get('orders', {}).get('counts', {}) or {}
                        if LAST_COUNTS:
                            keys = set(LAST_COUNTS) | set(cur_counts)
                            for k in sorted(keys):
                                old = int(LAST_COUNTS.get(k, 0) or 0)
                                new = int(cur_counts.get(k, 0) or 0)
                                if new != old:
                                    diff = new - old
                                    level = "ok" if diff > 0 else "warn"
                                    sign = "+" if diff > 0 else ""
                                    log(f"• {k}: {sign}{diff}", level=level)
                        LAST_COUNTS = dict(cur_counts)
                except Exception:
                    pass

                # Heartbeat: gentle header update every 0.5s, even without state change
                if (now - LAST_HEADER_TICK) > 0.5:
                    LAST_HEADER_TICK = now
                    try:
                        live.update(render(), refresh=True)
                    except Exception as e:
                        console.print(f"[red]Render error:[/] {_s(e)}")
                        break

                # State-/Count-Änderungen + 5-Sekunden-Heartbeat
                if (h is not None and h != LAST_HASH) or (now - LAST_HEARTBEAT) > 5.0:
                    LAST_HASH = h
                    LAST_HEARTBEAT = now
                    try:
                        live.update(render(), refresh=True)
                    except Exception as e:
                        console.print(f"[red]Render error:[/] {_s(e)}")
                        break
                time.sleep(0.1)
    except (KeyboardInterrupt, BrokenPipeError, OSError):
        LAST_MSG = "exiting (Ctrl+C)"
        log(LAST_MSG)
    finally:
        try:
            if os.path.exists(LOCK):
                os.remove(LOCK)
        except Exception:
            pass
def main():
    global LAST_MSG, LAST_HASH, LAST_HEARTBEAT, LAST_COUNTS, LAST_HEADER_TICK
    print("Starting TUI dashboard…", flush=True)

    # Input-Thread STARTEN
    t = threading.Thread(target=_input_reader, daemon=True)
    t.start()

    def safe_render():
        try:
            return render()
        except Exception as e:
            return Panel(f"Render failed: {e}", title="Error")
    try:
        with Live(safe_render(), refresh_per_second=2, screen=False,
                  auto_refresh=False, transient=False, console=console) as live:
            LAST_HASH = _state_hash()
            LAST_HEARTBEAT = time.time()
            while True:
                # 1) Befehle aus Queue verarbeiten
                try:
                    cmd = CMDQ.get_nowait()
                    res = _handle_command(cmd)
                    if res == "__QUIT__":
                        log("exiting"); LAST_MSG = "exiting"
                        live.update(safe_render(), refresh=True)
                        break
                    LAST_MSG = res
                    live.update(safe_render(), refresh=True)
                except queue.Empty:
                    pass

                # 2) Periodischer Refresh (Heartbeat / State-Änderung)
                h = _state_hash()
                now = time.time()
                if (h != LAST_HASH) or (now - LAST_HEARTBEAT) > 5.0:
                    LAST_HASH = h; LAST_HEARTBEAT = now
                    live.update(safe_render(), refresh=True)

                time.sleep(0.1)
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
