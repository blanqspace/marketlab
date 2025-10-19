import json
import os
from pathlib import Path

import typer

from .core.status import snapshot
from .core.control_policy import approval_window, approvals_required, command_target, risk_of_command
from .ipc import bus
from .modules.scanner_5m import save_signals, scan_symbols
from .orders.schema import OrderTicket
from .orders.store import (
    get_pending,
    list_tickets,
    put_ticket,
    resolve_order,
    set_state,
)
from .services.telegram_service import telegram_service
from .settings import get_settings
from .utils.logging import setup_logging
from .utils.signal_handlers import register_signal_handlers

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _cli_actor_id() -> str:
    return os.getenv("MARKETLAB_ACTOR") or os.getenv("USER") or "cli"


def _resolve_ttl(cmd: str, ttl_override: int | None) -> int:
    if ttl_override is not None:
        return int(ttl_override)
    return max(bus.DEFAULT_TTL, approval_window(cmd) + 30)


def _queue_command(
    cmd: str,
    args: dict,
    *,
    source: str = "cli",
    ttl_sec: int | None = None,
    dedupe_key: str | None = None,
    actor_id: str | None = None,
    request_id: str | None = None,
    risk_level: str | None = None,
) -> str:
    actor = actor_id or _cli_actor_id()
    target = command_target(cmd, args)
    if request_id:
        rid = request_id
    else:
        if target == cmd:
            base = bus.stable_request_id(cmd, args)
        else:
            base = f"{cmd}:{target}"
        if approvals_required(cmd) > 1 and actor:
            base = f"{base}:{actor}"
        rid = base
    ttl_final = _resolve_ttl(cmd, ttl_sec)
    risk = risk_level or risk_of_command(cmd)
    return bus.enqueue(
        cmd,
        args,
        source=source,
        ttl_sec=ttl_final,
        dedupe_key=dedupe_key,
        actor_id=actor,
        request_id=rid,
        risk_level=risk,
    )


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


@app.command("verify-data")
def verify_data(
    ctx: typer.Context,
    symbols: str = typer.Option(..., "--symbols"),
    timeframe: str = typer.Option("15m", "--timeframe"),
    data_dir: str = typer.Option("data", "--data-dir"),
    out: str | None = typer.Option(None, "--out"),
):
    from .utils.data_validator import validate_dataset
    try:
        syms = [s.strip() for s in symbols.split(",") if s.strip()]
        results = []
        for sym in syms:
            stem = f"{sym}_{timeframe}".upper()
            # prefer parquet then csv
            p_parq = Path(data_dir) / f"{stem}.parquet"
            p_csv = Path(data_dir) / f"{stem}.csv"
            path = p_parq if p_parq.exists() else p_csv
            res = validate_dataset(path, sym, timeframe)
            results.append(res)
            typer.echo(res)
        if out:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            with open(out, "w", encoding="utf-8") as f:
                import json
                json.dump(results, f, ensure_ascii=False, indent=2)
        status_codes = {"ok": 0, "warn": 0, "fail": 2}
        worst = max((r["status"] for r in results), key=lambda s: ["ok", "warn", "fail"].index(s))
        raise typer.Exit(code=status_codes.get(worst, 0))
    finally:
        _shutdown(ctx)


@app.command("supervisor")
def supervisor():
    """Startet den Ein-Fenster-Supervisor (kein screen, keine Hotkeys)."""
    from .supervisor import run_supervisor
    run_supervisor()


@app.command("slack")
def slack(ctx: typer.Context):
    """Startet den Slack-Socket-Mode-Bot als Control-Kanal."""
    settings = ctx.obj["settings"]
    if not settings.SLACK_ENABLED:
        typer.echo("Slack ist nicht aktiviert (SLACK_ENABLED=0).")
        _shutdown(ctx)
        raise typer.Exit(code=2)
    missing: list[str] = []
    if not settings.SLACK_BOT_TOKEN:
        missing.append("SLACK_BOT_TOKEN")
    if not settings.SLACK_APP_TOKEN:
        missing.append("SLACK_APP_TOKEN")
    if missing:
        typer.echo(f"Fehlende Slack-Konfiguration: {', '.join(missing)}")
        _shutdown(ctx)
        raise typer.Exit(code=2)
    from .services.slack_bot import SlackBot

    bot = SlackBot()
    try:
        bot.start()
    except RuntimeError as exc:
        typer.echo(f"Slack-Bot konnte nicht starten: {exc}")
        raise typer.Exit(code=2)
    finally:
        _shutdown(ctx)


@app.command("slack:selftest")
def slack_selftest(
    token: str = typer.Option("TEST123", "--token"),
    symbol: str = typer.Option("AAPL", "--symbol"),
    qty: int = typer.Option(10, "--qty"),
    px: float = typer.Option(178.2, "--px"),
):
    """Post a fake pending order to Slack to verify blocks/buttons."""
    from .services.slack_bot import SlackBot

    bot = SlackBot()
    order = {"token": token, "symbol": symbol, "qty": qty, "px": px, "side": "BUY"}
    ref = bot.post_order_pending(order)
    typer.echo({"posted": {"channel": ref.channel, "ts": ref.ts, "thread_ts": ref.thread_ts}})


ctl = typer.Typer(help="Command bus operations")
app.add_typer(ctl, name="ctl")


@ctl.command("enqueue")
def ctl_enqueue(
    cmd: str = typer.Option(..., "--cmd"),
    args: str = typer.Option("{}", "--args"),
    source: str = typer.Option("cli", "--source"),
    ttl_sec: int = typer.Option(300, "--ttl"),
    dedupe_key: str | None = typer.Option(None, "--dedupe"),
):
    import json as _json
    try:
        payload = _json.loads(args or "{}")
    except Exception:
        typer.echo({"error": "args must be JSON"})
        raise typer.Exit(code=2)
    cmd_id = _queue_command(
        cmd,
        payload,
        source=source,
        ttl_sec=ttl_sec,
        dedupe_key=dedupe_key,
    )
    typer.echo({"cmd_id": cmd_id})


@ctl.command("tail")
def ctl_tail(limit: int = typer.Option(30, "--limit")):
    """Dump last N events from bus for debugging."""
    events = bus.tail_events(limit=limit)
    import json as _json

    payload = [
        {"ts": evt.ts, "level": evt.level, "message": evt.message, "fields": evt.fields}
        for evt in events
    ]
    typer.echo(_json.dumps(payload, indent=2, ensure_ascii=False))


@ctl.command("emit")
def ctl_emit(
    name: str = typer.Option(..., "--name"),
    payload: str = typer.Option("{}", "--payload"),
):
    """Emit a raw event into bus (JSON payload)."""
    import json as _json

    try:
        fields = _json.loads(payload or "{}")
    except Exception as exc:
        typer.echo({"error": f"payload must be JSON: {exc}"})
        raise typer.Exit(code=2)
    if not isinstance(fields, dict):
        typer.echo({"error": "payload must decode to an object"})
        raise typer.Exit(code=2)
    bus.emit("debug", name, **fields)


@ctl.command("drain")
def ctl_drain(
    limit: int = typer.Option(10, "--limit"),
    apply: bool = typer.Option(False, "--apply", help="Process commands using worker"),
):
    if apply:
        from .daemon.worker import Worker
        w = Worker()
        seen = w.process_available(max_items=limit)
        typer.echo({"processed": seen})
        return
    # legacy drain: mark as done without applying
    seen = 0
    while seen < limit:
        c = bus.next_new()
        if not c:
            break
        bus.mark_done(c.cmd_id)
        seen += 1
    typer.echo({"drained": seen})


@app.command("control-menu")
def control_menu():
    """Startet das nummernbasierte Control-Menü (stdin, keine Hotkeys)."""
    from .control_menu import run_menu
    run_menu()


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
            typer.echo(
                f"[{s['ts']}] mode={s['mode']} state={s['run_state']} processed={s['processed']} stop={s['should_stop']}"
            )
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
            typer.echo("OK")
            raise typer.Exit(code=0)
        else:
            typer.echo("DEGRADED")
            raise typer.Exit(code=1)
    finally:
        _shutdown(ctx)


@app.command("stop-now")
def stop_now(ctx: typer.Context):
    try:
        _queue_command("stop.now", {}, source="cli")
        typer.echo({"stop": "queued"})
    finally:
        _shutdown(ctx)


@app.command("orders-confirm")
def orders_confirm(
    ctx: typer.Context,
    all_pending: bool = typer.Option(False, "--all-pending", help="Alle wartenden bestätigen"),
    include_telegram_confirmed: bool = typer.Option(True, "--include-tg", help="CONFIRMED_TG einschließen"),
):
    try:
        targets = []
        if all_pending:
            targets += [t["id"] for t in list_tickets("PENDING")]
            if include_telegram_confirmed:
                targets += [t["id"] for t in list_tickets("CONFIRMED_TG")]
        if not targets:
            typer.echo("Nichts zu bestätigen.")
            return
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
    token: str | None = typer.Option(None, "--token", help="Order token (SOT)"),
    n: int | None = typer.Option(None, "--n", help="Index in pending list (1-based)"),
    last: bool = typer.Option(False, "--last", help="Select last pending entry"),
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
        elif action in ("confirm", "reject"):
            selector: str | int | None = None
            if last:
                pend = get_pending(limit=1)
                if not pend:
                    raise ValueError("No pending orders")
                selector = pend[0]["id"]
            elif n is not None:
                selector = int(n)
            elif token:
                selector = token
            elif id_:
                selector = id_
            else:
                raise ValueError("missing selector: --n | --token | --id | --last")
            rec = resolve_order(selector)
            cmd = f"orders.{action}"
            payload = {"id": rec["id"]}
            if rec.get("token"):
                payload["token"] = rec["token"]
            _queue_command(cmd, payload, source="cli")
            # Token-only output
            typer.echo(f"OK: {cmd} -> {rec.get('token')}")
        else:
            raise ValueError("action must be one of: new|list|confirm|reject")
    except Exception as e:
        telegram_service.notify_error(f"orders {action} failed: {e}")
        raise
    finally:
        _shutdown(ctx)


diag = typer.Typer(help="Diagnosewerkzeuge")
app.add_typer(diag, name="diag")


@diag.command("ibkr")
def diag_ibkr(ctx: typer.Context):
    from .data.adapters import IBKRAdapter
    s = ctx.obj["settings"]
    try:
        adapter = IBKRAdapter().connect(s.ibkr.host, s.ibkr.port, client_id=7)
        adapter.req_market_data_type_delayed()
        ok = adapter.ping()
        caps = adapter.capabilities()
        typer.echo({"ok": ok, "capabilities": caps})
        raise typer.Exit(code=0 if ok else 1)
    except Exception as e:
        typer.echo({"ok": False, "error": str(e)})
        raise typer.Exit(code=1)
