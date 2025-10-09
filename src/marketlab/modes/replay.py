import logging, time
from ..data.adapters import CSVAdapter
from ..orders.store import list_tickets, set_state

log = logging.getLogger("marketlab.modes.replay")

def run(profile, symbols, timeframe):
    log.info({"event": "replay.start", "cfg": {"profile": profile, "symbols": symbols, "timeframe": timeframe}})
    a = CSVAdapter()
    for sym in symbols:
        df = a.load_bars(sym, timeframe)
        if df is None or len(df) == 0:
            log.warning({"event": "replay.nodata", "symbol": sym})
            continue
        log.info({"event": "replay.preload", "symbol": sym, "bars": int(len(df))})
        for _, row in df.iterrows():
            price = float(row["close"])
            # bestätigte Tickets sofort füllen
            for t in list_tickets():
                if t["symbol"] != sym:
                    continue
                if t["state"] == "CONFIRMED":
                    set_state(t["id"], "EXECUTED")
                    log.info({"event": "replay.order.exec", "ticket": t["id"], "fill_price": price})
            time.sleep(0.02)
    log.info({"event": "replay.run"})


