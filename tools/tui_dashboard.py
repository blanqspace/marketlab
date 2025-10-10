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
import os, tempfile
from collections import deque
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich import box
from src.marketlab.core.status import snapshot
from src.marketlab.orders.store import list_tickets, set_state, first_by_state

CMDQ = queue.Queue()
LAST_MSG = ""
LOG_LINES = deque(maxlen=200)

LOCK = os.path.join(tempfile.gettempdir(), "marketlab_tui.lock")

def log(msg: str):
    try:
        LOG_LINES.appendleft(f"[{snapshot()['ts']}] {msg}")
    except Exception:
        LOG_LINES.appendleft(msg)


def _header():
    s = snapshot()
    t = Table.grid(expand=True)
    t.add_column(justify="left"); t.add_column(justify="right")
    left = f"Mode: {s['mode']} | State: {s['run_state']} | Processed: {s['processed']}"
    right = f"TG enabled: {s['telegram']['enabled']} mock: {s['telegram']['mock']} | {s['ts']}"
    t.add_row(left, right)
    return Panel(t, title="MarketLab Dashboard", border_style="cyan", padding=(1,2))


def _orders_panel():
    tbl = Table(box=box.SIMPLE_HEAVY, expand=True)
    tbl.add_column("ID", overflow="fold", max_width=34)
    tbl.add_column("Symbol"); tbl.add_column("Side"); tbl.add_column("Qty"); tbl.add_column("Type"); tbl.add_column("State")
    rows = sum([list_tickets(st) for st in ("PENDING","CONFIRMED_TG","CONFIRMED")], [])
    for t in rows[:20]:
        tbl.add_row(t["id"], t["symbol"], t["side"], str(t["qty"]), t["type"], t["state"])
    return Panel(tbl, title="Orders (Top 20)")


def _events_panel():
    global LAST_MSG
    s = snapshot()
    txt = Text()
    txt.append(f"Counts: {s['orders']['counts']}\n")
    txt.append(f"Pending preview: {len(s['orders']['pending_preview'])} shown\n\n")
    txt.append("Type commands and press Enter\n")
    txt.append("Commands: status|s, pause|p, resume|r, stop|x, quit|q,\n")
    txt.append("          orders list | orders confirm --all | orders confirm <ID> | orders reject <ID>\n\n")
    if LAST_MSG:
        txt.append(f"Result: {LAST_MSG}\n\n")
    for ln in list(LOG_LINES)[:10]:
        txt.append(f"{ln}\n")
    return Panel(txt, title="Events / Command")


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
        log("status requested")
        try:
            LOG_LINES.appendleft(json.dumps(snapshot(), ensure_ascii=False)[:1000])
        except Exception:
            pass
        return "status printed"
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
            log(f"orders list -> {n}")
            return f"{n} orders"
        if len(parts) >= 3 and parts[1] == "confirm":
            if parts[2] == "--all":
                n = 0
                for t in list_tickets("PENDING"):
                    set_state(t["id"], "CONFIRMED"); n += 1
                for t in list_tickets("CONFIRMED_TG"):
                    set_state(t["id"], "CONFIRMED"); n += 1
                log(f"orders confirm --all -> {n}")
                return f"confirmed {n}"
            set_state(parts[2], "CONFIRMED")
            log(f"confirmed {parts[2]}")
            return f"confirmed {parts[2]}"
        if len(parts) >= 3 and parts[1] == "reject":
            set_state(parts[2], "REJECTED")
            log(f"rejected {parts[2]}")
            return f"rejected {parts[2]}"
        return "orders: unknown subcommand"

    # Convenience commands map to confirm/reject first
    if head == "confirm":
        t = _confirm_first()
        if t:
            log(f"confirm first {t['id']}")
            return "confirm first"
        return "no pending"
    if head == "reject":
        t = _reject_first()
        if t:
            log(f"reject first {t['id']}")
            return "reject first"
        return "no pending"

    return "unknown command"


def _input_reader():
    while True:
        try:
            line = input()
            if line is not None:
                CMDQ.put(line.strip())
        except EOFError:
            time.sleep(0.1)
        except Exception:
            time.sleep(0.2)


def main():
    global LAST_MSG
    # single-instance guard
    if os.path.exists(LOCK):
        print("TUI already running.")
        return
    open(LOCK, "w").close()

    t = threading.Thread(target=_input_reader, daemon=True)
    t.start()
    last_draw = 0.0
    try:
        with Live(render(), refresh_per_second=1, screen=False, auto_refresh=False) as live:
            while True:
                # timed redraw
                if time.time() - last_draw > 1.0:
                    last_draw = time.time()
                    live.update(render(), refresh=True)
                # process commands
                try:
                    cmd = CMDQ.get_nowait()
                    res = _handle_command(cmd)
                    if res == "__QUIT__":
                        log("exiting")
                        LAST_MSG = "exiting"
                        live.update(render(), refresh=True)
                        break
                    LAST_MSG = res
                    live.update(render(), refresh=True)
                except queue.Empty:
                    time.sleep(0.05)
    except KeyboardInterrupt:
        LAST_MSG = "exiting (Ctrl+C)"
        log(LAST_MSG)
    finally:
        try:
            if os.path.exists(LOCK):
                os.remove(LOCK)
        except Exception:
            pass

if __name__ == "__main__":
    main()
