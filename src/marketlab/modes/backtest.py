import logging
import time
from marketlab.data.adapters import CSVAdapter
from marketlab.settings import RuntimeConfig
from marketlab.core.state_manager import STATE, Command, RunState

log = logging.getLogger(__name__)

def _pump_commands() -> None:
    cmd = STATE.get_nowait()
    if cmd == Command.PAUSE:
        STATE.set_state(RunState.PAUSE)
    elif cmd == Command.RESUME:
        STATE.set_state(RunState.RUN)
    elif cmd == Command.STOP:
        STATE.set_state(RunState.EXIT)

def run(profile: str, symbols: list[str], timeframe: str, start: str | None, end: str | None) -> None:
    cfg = RuntimeConfig(profile=profile, symbols=symbols, timeframe=timeframe)
    log.info({"event": "backtest.start", "cfg": cfg.model_dump()})

    adapter = CSVAdapter()
    total = 0
    for sym in symbols:
        bars = list(adapter.fetch_bars(sym, timeframe, start, end))
        total += len(bars)
        log.info({"event": "backtest.loaded", "symbol": sym, "bars": len(bars)})

    # simulate processing loop so PAUSE/RESUME/STOP can be tested
    processed = 0
    while processed < max(1, total) and not STATE.should_stop():
        _pump_commands()
        if STATE.state == RunState.PAUSE:
            time.sleep(0.2)
            continue
        # do one unit of work
        time.sleep(0.1)
        processed += 1

    log.info({"event": "backtest.done"})