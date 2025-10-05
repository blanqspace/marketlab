import logging
from marketlab.data.adapters import CSVAdapter
from marketlab.settings import RuntimeConfig

log = logging.getLogger(__name__)


def run(profile: str, symbols: list[str], timeframe: str, start: str | None, end: str | None) -> None:
    cfg = RuntimeConfig(profile=profile, symbols=symbols, timeframe=timeframe)
    log.info({"event": "backtest.start", "cfg": cfg.model_dump()})

    adapter = CSVAdapter()
    for sym in symbols:
        bars = list(adapter.fetch_bars(sym, timeframe, start, end))
        log.info({"event": "backtest.loaded", "symbol": sym, "bars": len(bars)})

    log.info({"event": "backtest.done"})


