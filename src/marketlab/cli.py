from typing import Optional
import time
import typer
from marketlab.settings import settings
from marketlab.modes import backtest, replay, paper, live
from marketlab.utils.logging import setup_logging
from marketlab.services.telegram_service import telegram_service
from marketlab.core.state_manager import STATE

app = typer.Typer(add_completion=False, help="MarketLab CLI")

CommonSymbols = typer.Option(..., "--symbols", help="Kommagetrennt, z.B. AAPL,MSFT")
CommonTF = typer.Option(..., "--timeframe", help="z.B. 1m,5m,15m,1h,1d")

@app.callback()
def _init(verbose: bool = typer.Option(False, "--verbose", help="Mehr Logs")) -> None:
    setup_logging(verbose=verbose)
    _ = settings
    telegram_service.start_poller()

def _run_mode(fn, mode_name: str, *args, **kwargs) -> None:
    from marketlab.core.state_manager import RunState
    STATE.set_mode(mode_name)
    STATE.set_state(RunState.RUN)
    telegram_service.notify_start(mode_name)
    try:
        fn(*args, **kwargs)
    except Exception as e:
        telegram_service.notify_error(str(e))
        raise
    finally:
        telegram_service.notify_end(mode_name)

@app.command("backtest")
def backtest_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
    start: Optional[str] = typer.Option(None, help="ISO-Start"),
    end: Optional[str] = typer.Option(None, help="ISO-Ende"),
    work_units: int = typer.Option(120, "--work-units", help="Simulierte Arbeitsschritte"),
) -> None:
    _run_mode(backtest.run, "backtest", profile, symbols.split(","), timeframe, start, end, work_units)

@app.command("replay")
def replay_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
) -> None:
    _run_mode(replay.run, "replay", profile, symbols.split(","), timeframe)

@app.command("paper")
def paper_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
) -> None:
    _run_mode(paper.run, "paper", profile, symbols.split(","), timeframe)

@app.command("live")
def live_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
) -> None:
    _run_mode(live.run, "live", profile, symbols.split(","), timeframe)
