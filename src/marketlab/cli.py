import typer
from .utils.logging import setup_logging
from .settings import get_settings
from .utils.signal_handlers import register_signal_handlers
from .services.telegram_service import telegram_service
from .orders.schema import OrderTicket
from .orders.store import put_ticket, list_tickets, set_state, get_ticket
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
):
    from .modes import paper as pm
    try:
        pm.run(profile, [s.strip() for s in symbols.split(",") if s.strip()], timeframe)
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
