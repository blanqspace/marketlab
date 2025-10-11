"""Read-only MarketLab TUI Dashboard.

- No input, no hotkeys, no screen=True.
- Polls events and orders periodically and re-renders without flicker.
"""

from __future__ import annotations

import time
from typing import Any

from rich.live import Live
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich import box

from src.marketlab.ipc.bus import tail_events
from src.marketlab.orders.store import list_tickets
from src.marketlab.core.status import snapshot
import os
from src.marketlab.settings import get_settings


def _heartbeat_frame(now: float) -> str:
    frames = ["∙", "•", "●", "•"]
    idx = int(now) % len(frames)
    return frames[idx]


def _header() -> Panel:
    now = time.time()
    hb = _heartbeat_frame(now)
    s: dict[str, Any] = {}
    try:
        s = snapshot() or {}
    except Exception:
        s = {}
    state = s.get("run_state", "RUN")
    mode = s.get("mode", "-")
    left = f"Mode: {mode}  |  [bold]State:[/] {state} {hb}"
    app_settings = get_settings()
    # Ensure bus reads the same DB path
    os.environ["IPC_DB"] = app_settings.ipc_db
    db_name = os.path.basename(app_settings.ipc_db)
    right = f"[cyan]{time.strftime('%H:%M:%S UTC', time.gmtime())}[/cyan]  DB={db_name}"
    g = Table.grid(expand=True); g.add_column(justify="left"); g.add_column(justify="right")
    g.add_row(left, right)
    return Panel(g, title="MarketLab Dashboard", border_style="cyan", padding=(0,2))


def _orders_panel() -> Panel:
    tbl = Table(box=box.SIMPLE_HEAVY, expand=True)
    # Show token-only, no internal ID
    tbl.add_column("Tok", width=6)
    tbl.add_column("Symbol"); tbl.add_column("Side"); tbl.add_column("Qty"); tbl.add_column("Type"); tbl.add_column("State")
    rows: list[dict[str, Any]] = []
    try:
        for st in ("PENDING", "CONFIRMED_TG", "CONFIRMED"):
            items = list_tickets(st) or []
            rows.extend(items)
    except Exception:
        rows = []
    if not rows:
        tbl.add_row("—", "—", "—", "—", "—", "—")
    else:
        for t in rows[:20]:
            tbl.add_row(
                str(t.get("token", "-"))[:6],
                str(t.get("symbol", "-")),
                str(t.get("side", "-")),
                str(t.get("qty", "-")),
                str(t.get("type", "-")),
                str(t.get("state", "-")),
            )
    return Panel(tbl, title="Orders (Top 20)", border_style="magenta")


def _events_panel() -> Panel:
    tbl = Table(box=box.SIMPLE, expand=True)
    tbl.add_column("TS", width=19)
    tbl.add_column("lvl", width=6)
    tbl.add_column("msg", overflow="fold")
    try:
        events = tail_events(20) or []
    except Exception:
        events = []
    if not events:
        tbl.add_row("—", "—", "No events yet")
    else:
        for ev in events:
            # bus.Event objects
            ts = getattr(ev, "ts", "-")
            lvl = getattr(ev, "level", "-")
            msg = getattr(ev, "message", "-")
            ctx = getattr(ev, "fields", {}) or {}
            if isinstance(ts, (int, float)):
                ts = time.strftime("%H:%M:%S", time.gmtime(ts))
            # show token only if present in context
            if "token" in ctx:
                msg = f"{msg} token={ctx.get('token')}"
            tbl.add_row(str(ts), str(lvl), str(msg))
    return Panel(tbl, title="Events (tail)", border_style="blue")


def render():
    # robustes Layout mit klaren Größen
    root = Layout(name="root")
    root.split_column(
        Layout(_header(), name="hdr", size=3),
        Layout(name="body")
    )
    root["body"].split_row(
        Layout(_orders_panel(), name="orders", ratio=2),
        Layout(_events_panel(), name="events", ratio=2),
    )
    return root


def main():  # pragma: no cover
    console = Console(force_terminal=True, color_system="truecolor")
    # erste Ausgabe, falls Rich-Terminal falsch erkannt wird
    console.print("[cyan]Starting MarketLab Dashboard...[/cyan]")
    # Wichtig: auto_refresh=False → explizit updaten
    with Live(render(), refresh_per_second=2, screen=False, auto_refresh=False, transient=False, console=console) as live:
        while True:
            live.update(render(), refresh=True)   # <-- fehlte
            time.sleep(1.0)

if __name__ == "__main__":  # wichtig für `python -m tools.tui_dashboard`
    try:
        main()
    except KeyboardInterrupt:
        pass
