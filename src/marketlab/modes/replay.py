import logging
from marketlab.data.adapters import CSVAdapter
from marketlab.settings import RuntimeConfig

log = logging.getLogger(__name__)


def run(profile: str, symbols: list[str], timeframe: str) -> None:
    cfg = RuntimeConfig(profile=profile, symbols=symbols, timeframe=timeframe)
    log.info({"event": "replay.start", "cfg": cfg.model_dump()})
    adapter = CSVAdapter()
    for sym in symbols:
        _ = list(adapter.fetch_bars(sym, timeframe))
        log.info({"event": "replay.preload", "symbol": sym})
    log.info({"event": "replay.run"})


