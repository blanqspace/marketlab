import typer
import json, sys
from .utils.logging import setup_logging
from .settings import get_settings
from .utils.signal_handlers import register_signal_handlers
from .services.telegram_service import telegram_service
from .orders.schema import OrderTicket
from .orders.store import put_ticket, list_tickets, set_state, get_ticket
from .core.status import snapshot
from .modules.scanner_5m import scan_symbols, save_signals
from datetime import datetime, timezone

app = typer.Typer(no_args_is_help=True, add_completion=False)

@app.callback()
def _init(ctx: typer.Context):
    setup_logging()
    settings = get_settings()
    ctx.obj = {"settings": settings}
    register_signal_handlers()
    if settings.telegram.enabled:
        telegram_service.start_poller(settings)

def _shutdown(ctx: typer.Context):
    settings = ctx.obj.get("settings")
    if settings and settings.telegram.enabled:
        telegram_service.stop_poller()

# Beispiel: control
@app.command()
def control(ctx: typer.Context):
    from .modes import control as ctl
    try:
        ctl.run(ctx.obj["settings"])
    except Exception as e:
        telegram_service.notify_error(f"control failed: {e}")
        raise
    finally:
        _shutdown(ctx)

# backtest
@app.command()
def backtest(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile"),
    symbols: str = typer.Option(..., "--symbols"),
    timeframe: str = typer.Option("15m", "--timeframe"),
    start: str | None = typer.Option(None, "--start"),
    end: str | None = typer.Option(None, "--end"),
    work_units: int = typer.Option(0, "--work-units"),
):
    from .modes import backtest as bt
    try:
        result = bt.run(ctx.obj["settings"], profile, symbols, timeframe, start, end, work_units)
        typer.echo(result)
    except Exception as e:
        telegram_service.notify_error(f"backtest failed: {e}")
        raise
    finally:
        _shutdown(ctx)

@app.command("scan")
def scan(
    ctx: typer.Context,
    symbols: str = typer.Option(..., "--symbols", help="Comma separated symbols"),
    timeframe: str = typer.Option("5m", "--timeframe", help="5m or 2m"),
    out: str = typer.Option("reports/signals_5m.csv", "--out", help="Output CSV path"),
    json_out: bool = typer.Option(False, "--json", help="JSON output instead of file"),
):
    try:
        syms = [s.strip() for s in symbols.split(",") if s.strip()]
        df = scan_symbols(syms, timeframe)
        if json_out:
            recs = df.tail(100).to_dict(orient="records")
            typer.echo(json.dumps(recs, ensure_ascii=False, indent=2))
        else:
            save_signals(df, out)
            buy = int((df["signal"] == "BUY").sum()) if not df.empty else 0
            sell = int((df["signal"] == "SELL").sum()) if not df.empty else 0
            none = int((df["signal"] == "None").sum()) if not df.empty else 0
            typer.echo({"rows": len(df), "BUY": buy, "SELL": sell, "None": none, "dst": out})
    finally:
        _shutdown(ctx)

@app.command()
def status(ctx: typer.Context, json_out: bool = typer.Option(False, "--json", help="JSON-Output")):
    try:
        s = snapshot()
        if json_out:
            typer.echo(json.dumps(s, ensure_ascii=False, indent=2))
        else:
            typer.echo(f"[{s['ts']}] mode={s['mode']} state={s['run_state']} processed={s['processed']} stop={s['should_stop']}")
            typer.echo(f"telegram: enabled={s['telegram']['enabled']} mock={s['telegram']['mock']}")
            typer.echo(f"orders: {s['orders']['counts']}")
    finally:
        _shutdown(ctx)

@app.command("health")
def health(ctx: typer.Context):
    try:
        s = snapshot()
        ok = s["telegram"]["enabled"] and not s["should_stop"]
        # simple checks: keine zwingende Regelverletzung
        if ok:
            typer.echo("OK"); raise typer.Exit(code=0)
        else:
            typer.echo("DEGRADED"); raise typer.Exit(code=1)
    finally:
        _shutdown(ctx)

@app.command("orders-confirm")
def orders_confirm(ctx: typer.Context,
                   all_pending: bool = typer.Option(False, "--all-pending", help="Alle wartenden bestätigen"),
                   include_telegram_confirmed: bool = typer.Option(True, "--include-tg", help="CONFIRMED_TG einschließen")):
    try:
        targets = []
        if all_pending:
            targets += [t["id"] for t in list_tickets("PENDING")]
            if include_telegram_confirmed:
                targets += [t["id"] for t in list_tickets("CONFIRMED_TG")]
        if not targets:
            typer.echo("Nichts zu bestätigen."); return
        for oid in targets:
            set_state(oid, "CONFIRMED")
        typer.echo({"confirmed": len(targets)})
    finally:
        _shutdown(ctx)

# replay
@app.command()
def replay(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile"),
    symbols: str = typer.Option(..., "--symbols"),
    timeframe: str = typer.Option("15m", "--timeframe"),
):
    from .modes import replay as rp
    try:
        # Bestehende Signatur verwenden (keine Settings nötig)
        rp.run(profile, [s.strip() for s in symbols.split(",") if s.strip()], timeframe)
    except Exception as e:
        telegram_service.notify_error(f"replay failed: {e}")
        raise
    finally:
        _shutdown(ctx)

# paper
@app.command()
def paper(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile"),
    symbols: str = typer.Option(..., "--symbols"),
    timeframe: str = typer.Option("15m", "--timeframe"),
    host: str | None = typer.Option(None, "--host", help="IBKR API host (overrides TWS_HOST)"),
    port: int | None = typer.Option(None, "--port", help="IBKR API port (overrides TWS_PORT)"),
):
    from .modes import paper as pm
    try:
        pm.run(
            profile,
            [s.strip() for s in symbols.split(",") if s.strip()],
            timeframe,
            host=host,
            port=port,
        )
    except Exception as e:
        telegram_service.notify_error(f"paper failed: {e}")
        raise
    finally:
        _shutdown(ctx)

# live
@app.command()
def live(
    ctx: typer.Context,
    profile: str = typer.Option("default", "--profile"),
    symbols: str = typer.Option(..., "--symbols"),
    timeframe: str = typer.Option("15m", "--timeframe"),
):
    from .modes import live as lv
    try:
        lv.run(profile, [s.strip() for s in symbols.split(",") if s.strip()], timeframe)
    except Exception as e:
        telegram_service.notify_error(f"live failed: {e}")
        raise
    finally:
        _shutdown(ctx)

# orders
@app.command("orders")
def orders(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="new|list|confirm|reject"),
    symbol: str = typer.Option(None, "--symbol"),
    side: str = typer.Option(None, "--side"),
    qty: float = typer.Option(0, "--qty"),
    type_: str = typer.Option("MARKET", "--type"),
    limit: float | None = typer.Option(None, "--limit"),
    sl: float | None = typer.Option(None, "--sl"),
    tp: float | None = typer.Option(None, "--tp"),
    id_: str = typer.Option(None, "--id"),
    ttl: int = typer.Option(120, "--ttl"),
):
    try:
        if action == "new":
            assert symbol and side and qty > 0
            t = OrderTicket.new(symbol, side, qty, type_, limit, sl, tp, ttl)
            put_ticket(t)
            telegram_service.send_order_ticket(t.to_dict())
            typer.echo({"created": t.id})
        elif action == "list":
            typer.echo(list_tickets())
        elif action == "confirm":
            assert id_
            t = get_ticket(id_)
            if not t: raise ValueError("Unknown order id")
            # Ablaufdatum prüfen
            if datetime.fromisoformat(t["expires_at"]) < datetime.now(timezone.utc):
                set_state(id_, "CANCELED"); typer.echo({"state":"CANCELED"}); return
            set_state(id_, "CONFIRMED"); typer.echo({"state":"CONFIRMED"})
        elif action == "reject":
            assert id_
            set_state(id_, "REJECTED"); typer.echo({"state":"REJECTED"})
        else:
            raise ValueError("action must be one of: new|list|confirm|reject")
    except Exception as e:
        telegram_service.notify_error(f"orders {action} failed: {e}")
        raise
    finally:
        _shutdown(ctx)
