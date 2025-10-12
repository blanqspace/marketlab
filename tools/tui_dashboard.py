"""Read-only MarketLab TUI Dashboard.

- No input, no hotkeys, no screen=True.
- Adaptive refresh for events/orders/KPIs to minimize flicker.
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

from src.marketlab.ipc.bus import tail_events, get_state
from src.marketlab.orders.store import list_tickets
from src.marketlab.core.status import snapshot, snapshot_kpis, events_tail_agg
import os
from src.marketlab.settings import get_settings
from src.marketlab.bootstrap.env import load_env
from src.marketlab.core.timefmt import parse_iso, fmt_mm_ss


def _heartbeat_frame(now: float) -> str:
    frames = ["∙", "•", "●", "•"]
    idx = int(now) % len(frames)
    return frames[idx]


def _header() -> Panel:
    now = time.time()
    hb = _heartbeat_frame(now)
    # stable state/mode from app_state
    try:
        state = get_state("state", "INIT")
    except Exception:
        state = "INIT"
    try:
        mode = get_state("mode", "-")
    except Exception:
        mode = "-"
    app_settings = get_settings()
    # Use central settings for DB path (no direct OS env access)
    dbp = app_settings.ipc_db
    db_name = os.path.basename(dbp)
    # Uptime from worker_start_ts
    uptime_txt = "--:--"
    try:
        start = get_state("worker_start_ts", "")
        if start:
            from datetime import datetime, timezone
            now_dt = datetime.now(timezone.utc)
            delta = now_dt - parse_iso(start)
            uptime_txt = fmt_mm_ss(delta)
    except Exception:
        pass
    left = f"Mode: {mode}  |  [bold]State:[/] {state} {hb}  |  Uptime: {uptime_txt}"
    # include worker pid when available via KPIs (do not force every tick)
    try:
        k = snapshot_kpis(app_settings.ipc_db)
        wpid = k.get("worker_pid")
        if wpid:
            left += f"  |  W-PID: {wpid}"
    except Exception:
        pass
    right = f"[cyan]{time.strftime('%H:%M:%S UTC', time.gmtime())}[/cyan]  DB={db_name}"
    g = Table.grid(expand=True); g.add_column(justify="left"); g.add_column(justify="right")
    g.add_row(left, right)
    return Panel(g, title="MarketLab Dashboard", border_style="cyan", padding=(0,2))


def _label_event(ev: dict[str, Any]) -> str:
    """Return a clear label for an aggregated event row."""
    try:
        raw_msg = str(ev.get("message", "-"))
        fields = ev.get("fields") or {}
        token = fields.get("token")
        # normalize sources list
        srcs: list[str] = []
        if isinstance(fields.get("sources"), list):
            srcs = [str(s) for s in fields.get("sources") if str(s).strip()]
        elif fields.get("source"):
            srcs = [str(fields.get("source"))]
        srcs = sorted(list({s for s in srcs if s}))
        if raw_msg == "orders.confirm.pending":
            return f"Order Bestätigung ausstehend {token or '-'} [{'+'.join(srcs)}]"
        if raw_msg == "orders.confirm.ok":
            return f"Order bestätigt {token or '-'} [{'+'.join(srcs)}]"
        if raw_msg == "orders.reject.ok":
            return f"Order abgelehnt {token or '-'} [{'+'.join(srcs)}]"
        if raw_msg == "state.changed":
            st = fields.get("state") or "-"
            return f"State geändert → {st}"
        return raw_msg
    except Exception:
        return str(ev.get("message", "-"))


def _orders_panel(filter_str: str = "") -> Panel:
    tbl = Table(box=box.SIMPLE_HEAVY, expand=True)
    # Show token-only, no internal ID
    tbl.add_column("Tok", width=10)
    tbl.add_column("Symbol"); tbl.add_column("Side"); tbl.add_column("Qty"); tbl.add_column("Type"); tbl.add_column("State"); tbl.add_column("Age(s)"); tbl.add_column("TTL(s)")
    rows: list[dict[str, Any]] = []
    try:
        for st in ("PENDING", "CONFIRMED_TG", "CONFIRMED"):
            items = list_tickets(st) or []
            rows.extend(items)
    except Exception:
        rows = []
    # Optional filters: symbol=..., state=...
    f_symbol = None; f_state = None
    for part in (filter_str or "").split():
        if part.lower().startswith("symbol="):
            f_symbol = part.split("=",1)[1].strip().upper()
        if part.lower().startswith("state="):
            f_state = part.split("=",1)[1].strip().upper()
    def _match(r: dict) -> bool:
        ok = True
        if f_symbol:
            ok = ok and str(r.get("symbol","-")).upper() == f_symbol
        if f_state:
            ok = ok and str(r.get("state","-")).upper() == f_state
        return ok
    rows = [r for r in rows if _match(r)]
    if not rows:
        tbl.add_row("-", "-", "-", "-", "-", "-", "-", "-")
    else:
        from datetime import datetime, timezone
        for t in rows[:20]:
            tok = str(t.get("token", "-"))[:6]
            # Add source badges based on recent approvals (heuristic via events)
            badges = ""
            try:
                dbp = os.getenv("IPC_DB") or get_settings().ipc_db
                evs = events_tail_agg(dbp, 200)
                srcs = set()
                for e in evs:
                    f = e.get("fields") or {}
                    if f.get("token") == t.get("token") and e.get("message") == "orders.confirm.pending":
                        # prefer list of sources when available
                        if isinstance(f.get("sources"), list):
                            for s in f.get("sources"):
                                s_l = (str(s) or "").lower()
                                if s_l:
                                    srcs.add(s_l)
                        else:
                            s = (f.get("source") or "").lower()
                            if s:
                                srcs.add(s)
                if "telegram" in srcs:
                    badges += " [TG]"
                if any(s for s in srcs if s != "telegram"):
                    badges += " [PC]"
            except Exception:
                pass
            tok_show = (tok + badges).strip()
            # age and ttl left
            cr = t.get("created_at"); ex = t.get("expires_at")
            def _to_dt(x):
                try:
                    return datetime.fromisoformat(str(x))
                except Exception:
                    try:
                        return datetime.fromisoformat(str(x).replace("Z","+00:00"))
                    except Exception:
                        return None
            now_dt = datetime.now(timezone.utc)
            age_s = ttl_s = "-"
            dcr = _to_dt(cr); dex = _to_dt(ex)
            if dcr:
                age_s = str(int((now_dt - dcr).total_seconds()))
            if dex:
                ttl_s = str(int((dex - now_dt).total_seconds()))
            tbl.add_row(
                tok_show,
                str(t.get("symbol", "-")),
                str(t.get("side", "-")),
                str(t.get("qty", "-")),
                str(t.get("type", "-")),
                str(t.get("state", "-")),
                age_s,
                ttl_s,
            )
    return Panel(tbl, title="Orders (Top 20)", border_style="magenta")


def _events_panel(filter_str: str = "") -> Panel:
    tbl = Table(box=box.SIMPLE, expand=True)
    tbl.add_column("Δt", width=6)
    tbl.add_column("UTC", width=9)
    tbl.add_column("lvl", width=6)
    tbl.add_column("msg", overflow="fold")
    # filter: filter=warn -> show warn/error only; allow env override
    try:
        warn_cfg = int(get_settings().dashboard_warn_only)
    except Exception:
        warn_cfg = 0
    warn_only = bool(warn_cfg) or any(part.lower() == "filter=warn" for part in (filter_str or "").split())
    try:
        dbp = os.getenv("IPC_DB") or get_settings().ipc_db
        events = events_tail_agg(dbp, n=100) or []
    except Exception:
        events = []
    if not events:
        tbl.add_row("-", "-", "-", "No events yet")
    else:
        now = int(time.time())
        for ev in events[:30]:
            lvl = str(ev.get("level", "-"))
            if warn_only and lvl.lower() not in ("warn", "error"):
                continue
            ts = int(ev.get("ts", 0)) if ev.get("ts") else 0
            rel = now - ts
            rel_s = f"-{rel//60:02d}:{rel%60:02d}"
            utc = time.strftime("%H:%M:%S", time.gmtime(ts)) if ts else "-"
            msg = _label_event(ev)
            cnt = int(ev.get("count", 1))
            if cnt > 1:
                msg = f"{msg} x{cnt}"
            tbl.add_row(rel_s, f"[dim]{utc}[/dim]", lvl, msg)
    return Panel(tbl, title="Events (agg)", border_style="blue")


def _kpi_panel() -> Panel:
    # show compact KPIs (5m window)
    dbp = os.getenv("IPC_DB") or get_settings().ipc_db
    try:
        k = snapshot_kpis(dbp)
    except Exception:
        k = {}
    tbl = Table(box=box.MINIMAL_DOUBLE_HEAD, expand=True)
    tbl.add_column("metric", width=16)
    tbl.add_column("value")
    cc = k.get("cmd_counts_5m", {}) or {}
    tbl.add_row("cmd_counts_5m", f"N={cc.get('NEW',0)} D={cc.get('DONE',0)} E={cc.get('ERROR',0)}")
    tbl.add_row("events_per_min", f"{k.get('events_per_min',0):.2f}")
    age = k.get("last_event_age", -1)
    tbl.add_row("last_event_age", f"{age}s")
    osum = k.get("orders_summary", {}) or {}
    tbl.add_row("orders", f"p={osum.get('pending',0)} c={osum.get('confirmed',0)} r={osum.get('rejected',0)}")
    tbl.add_row("two_man_pending", str(k.get("two_man_pending_count", 0)))
    tbl.add_row("avg_ttl_left", f"{k.get('avg_ttl_left',0.0):.1f}s")
    return Panel(tbl, title="KPIs (5m)", border_style="green")


def _ibkr_panel() -> Panel:
    def _gs(key: str, default: str = "") -> str:
        try:
            return str(get_state(key, default) or default)
        except Exception:
            return default
    enabled = _gs("ibkr.enabled", "0")
    connected = _gs("ibkr.connected", "0")
    host = _gs("ibkr.host", "127.0.0.1")
    port = _gs("ibkr.port", "4002")
    client_id = _gs("ibkr.client_id", "")
    mdt = _gs("ibkr.market_data_type", "")
    last_ok = _gs("ibkr.last_ok_ts", "")
    last_err = _gs("ibkr.last_err", "")
    age = "--:--"
    try:
        if last_ok:
            from datetime import datetime, timezone
            now_dt = datetime.now(timezone.utc)
            age = fmt_mm_ss(now_dt - parse_iso(last_ok))
    except Exception:
        pass
    tbl = Table.grid(expand=True)
    bad_conn = f"[green]Yes[/green]" if connected == "1" else f"[red]No[/red]"
    bad_en = "Yes" if enabled == "1" else "No"
    tbl.add_row(f"enabled: {bad_en}", f"connected: {bad_conn}")
    tbl.add_row(f"host:port: {host}:{port}")
    tbl.add_row(f"client_id: {client_id}")
    if mdt:
        tbl.add_row(f"mkt_data_type: {mdt}")
    tbl.add_row(f"last_ok_age: {age}")
    if last_err:
        short = (last_err[:40] + "…") if len(last_err) > 40 else last_err
        tbl.add_row(f"last_err: {short}")
    return Panel(tbl, title="IBKR", border_style="yellow")


def _tg_panel() -> Panel:
    def _gs(key: str, default: str = "") -> str:
        try:
            return str(get_state(key, default) or default)
        except Exception:
            return default
    enabled = _gs("tg.enabled", "0")
    mock = _gs("tg.mock", "0")
    bot = _gs("tg.bot_username", "")
    chat = _gs("tg.chat_control", "")
    allow = _gs("tg.allowlist_count", "0")
    last_ok = _gs("tg.last_ok_ts", "")
    last_err = _gs("tg.last_err", "")
    age = "--:--"
    try:
        if last_ok:
            from datetime import datetime, timezone
            age = fmt_mm_ss(datetime.now(timezone.utc) - parse_iso(last_ok))
    except Exception:
        pass
    tbl = Table.grid(expand=True)
    bad_en = "Yes" if enabled == "1" else "No"
    bad_mock = f"[yellow]Yes[/yellow]" if mock == "1" else "No"
    tbl.add_row(f"enabled: {bad_en}", f"mock: {bad_mock}")
    tbl.add_row(f"bot: {bot or '-'}", f"chat: {chat or '-'}")
    tbl.add_row(f"allowlist: {allow}")
    tbl.add_row(f"last_ok_age: {age}")
    if last_err:
        short = (last_err[:40] + "…") if len(last_err) > 40 else last_err
        tbl.add_row(f"last_err: {short}")
    return Panel(tbl, title="Telegram", border_style="yellow")


def _current_filter() -> str:
    # Allow changing filter by editing runtime/dashboard.filter (simple UX)
    try:
        p = os.path.join("runtime", "dashboard.filter")
        if os.path.exists(p):
            return (open(p, "r", encoding="utf-8").read() or "").strip()
    except Exception:
        pass
    return os.getenv("DASH_FILTER", "")


# --- Adaptive rendering helpers ---

def render_layout() -> Layout:
    root = Layout(name="root")
    root.split_column(
        Layout(_header(), name="hdr", size=3),
        Layout(name="body")
    )
    body = root["body"]
    body.split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=2),
    )
    filt = _current_filter()
    body["left"].update(_orders_panel(filt))
    body["right"].split_column(
        Layout(_kpi_panel(), name="kpi", size=8),
        Layout(name="conn", size=9),
        Layout(_events_panel(filt), name="events"),
    )
    # connections block contains IBKR and Telegram side-by-side
    conn_grid = Table.grid(expand=True)
    conn_grid.add_column(); conn_grid.add_column()
    conn_grid.add_row(_ibkr_panel(), _tg_panel())
    body["right"]["conn"].update(Panel(conn_grid, title="Conn", border_style="cyan"))
    return root


def _peek_last_event_ts(db_path: str) -> int:
    try:
        ev = tail_events(1)
        return int(ev[0].ts) if ev else 0
    except Exception:
        return 0


def main_adaptive():  # pragma: no cover
    console = Console(force_terminal=True, color_system="truecolor")
    s = load_env(mirror=True)
    os.environ["IPC_DB"] = s.ipc_db
    layout = render_layout()
    now = time.time()
    next_events_ts = now
    next_orders_ts = now
    next_kpis_ts = now
    next_conn_ts = now
    last_event_ts = _peek_last_event_ts(s.ipc_db)
    # refresh cadence via environment (defaults: events=5s, kpis=15s)
    try:
        ev_every = max(1, int(get_settings().events_refresh_sec))
    except Exception:
        ev_every = 5
    try:
        kpi_every = max(1, int(get_settings().kpis_refresh_sec))
    except Exception:
        kpi_every = 15

    with Live(layout, refresh_per_second=10, screen=False, auto_refresh=False, transient=False, console=console) as live:
        while True:
            now = time.time()
            cur_last_ts = _peek_last_event_ts(s.ipc_db)
            if cur_last_ts > last_event_ts:
                last_event_ts = cur_last_ts
                next_events_ts = now
                # if latest event is relevant to orders/state, refresh orders immediately
                try:
                    evs = tail_events(1)
                    if evs:
                        m0 = str(evs[0].message)
                        if m0.startswith("orders.") or m0.startswith("state."):
                            next_orders_ts = now
                except Exception:
                    pass

            filt = _current_filter()
            updated = False

            layout["hdr"].update(_header())
            updated = True

            if now >= next_events_ts:
                layout["body"]["right"]["events"].update(_events_panel(filt))
                next_events_ts = now + ev_every
                updated = True

            if now >= next_orders_ts:
                layout["body"]["left"].update(_orders_panel(filt))
                next_orders_ts = now + ev_every
                updated = True

            if now >= next_kpis_ts:
                layout["body"]["right"]["kpi"].update(_kpi_panel())
                next_kpis_ts = now + kpi_every
                updated = True

            # refresh connection panels every 5s
            if now >= next_conn_ts:
                conn_grid = Table.grid(expand=True)
                conn_grid.add_column(); conn_grid.add_column()
                conn_grid.add_row(_ibkr_panel(), _tg_panel())
                layout["body"]["right"]["conn"].update(Panel(conn_grid, title="Conn", border_style="cyan"))
                next_conn_ts = now + 5
                updated = True

            if updated:
                live.update(layout, refresh=True)

            time.sleep(0.2)


# Small pure helper for tests: decide what to refresh next tick
def _plan_tick(now: float, next_events_ts: float, next_orders_ts: float, next_kpis_ts: float,
               events_changed: bool, ev_every: int, kpi_every: int) -> tuple[dict, tuple[float, float, float]]:
    upd_events = events_changed or now >= next_events_ts
    upd_orders = now >= next_orders_ts
    upd_kpis = now >= next_kpis_ts
    if upd_events:
        next_events_ts = now + max(1, int(ev_every))
    if upd_orders:
        next_orders_ts = now + max(1, int(ev_every))
    if upd_kpis:
        next_kpis_ts = now + max(1, int(kpi_every))
    return ({"events": upd_events, "orders": upd_orders, "kpis": upd_kpis}, (next_events_ts, next_orders_ts, next_kpis_ts))


def render():
    # robustes Layout mit klaren Größen
    root = Layout(name="root")
    root.split_column(
        Layout(_header(), name="hdr", size=3),
        Layout(name="body")
    )
    # body: left orders; right: top kpi, bottom events
    body = root["body"]
    body.split_row(
        Layout(name="left", ratio=2),
        Layout(name="right", ratio=2),
    )
    filt = _current_filter()
    body["left"].update(_orders_panel(filt))
    body["right"].split_column(
        Layout(_kpi_panel(), name="kpi", size=8),
        Layout(_events_panel(filt), name="events"),
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
        main_adaptive()
    except KeyboardInterrupt:
        pass
