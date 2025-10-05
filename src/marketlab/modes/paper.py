import logging
from marketlab.data.adapters import IBKRAdapter
from marketlab.settings import RuntimeConfig

log = logging.getLogger(__name__)


def run(profile: str, symbols: list[str], timeframe: str) -> None:
    cfg = RuntimeConfig(profile=profile, symbols=symbols, timeframe=timeframe)
    log.info({"event": "paper.start", "cfg": cfg.model_dump()})
    adapter = IBKRAdapter()
    for sym in symbols:
        _ = adapter.stream_quotes(sym)
        log.info({"event": "paper.stream.init", "symbol": sym})


