
from typing import Optional
import typer
from marketlab.settings import settings
from marketlab.modes import backtest, replay, paper, live
from marketlab.utils.logging import setup_logging

app = typer.Typer(add_completion=False, help="MarketLab CLI")

CommonSymbols = typer.Option(..., "--symbols", help="Kommagetrennt, z.B. AAPL,MSFT")
CommonTF = typer.Option(..., "--timeframe", help="z.B. 1m,5m,15m,1h,1d")

@app.callback()
def _init(verbose: bool = typer.Option(False, "--verbose", help="Mehr Logs")) -> None:
    setup_logging(verbose=verbose)
    _ = settings

@app.command("backtest")
def backtest_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
    start: Optional[str] = typer.Option(None, help="ISO-Startzeit oder Zeitraum-Preset"),
    end: Optional[str] = typer.Option(None, help="ISO-Endzeit"),
) -> None:
    backtest.run(profile, symbols.split(","), timeframe, start, end)

@app.command("replay")
def replay_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
) -> None:
    replay.run(profile, symbols.split(","), timeframe)

@app.command("paper")
def paper_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
) -> None:
    paper.run(profile, symbols.split(","), timeframe)

@app.command("live")
def live_cmd(
    profile: str = typer.Option("default", "--profile"),
    symbols: str = CommonSymbols,
    timeframe: str = CommonTF,
) -> None:
    live.run(profile, symbols.split(","), timeframe)
