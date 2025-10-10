import os, logging
from ..data.adapters import IBKRAdapter
from ..orders.store import list_tickets, set_state

log = logging.getLogger("marketlab.modes.paper")

def run(profile, symbols, timeframe, host: str | None = None, port: int | None = None):
    # Resolve connection parameters with CLI > ENV > defaults
    host = host or os.getenv("TWS_HOST", "127.0.0.1")
    port = port if port is not None else os.getenv("TWS_PORT", "7497")
    client = int(os.getenv("IBKR_CLIENT_ID", "7"))

    log.info({
        "event": "paper.start",
        "cfg": {
            "profile": profile,
            "symbols": symbols,
            "timeframe": timeframe,
            "host": host,
            "port": int(port),
        },
    })

    ib = IBKRAdapter()
    ib.connect(host, port, client)

    for sym in symbols:
        log.info({"event": "paper.stream.init", "symbol": sym})
        tick_iter = ib.stream_quotes(sym)
        # Begrenzte Ticks im Smoke, Endlosschleife in echter Session anpassen
        for _ in range(50):
            tick = next(tick_iter)
            # bestätigte Tickets dieses Symbols ausführen
            for t in list_tickets():
                if t["symbol"] != sym:
                    continue
                if t["state"] == "CONFIRMED":
                    res = ib.submit_order(sym, t["side"], t["qty"], t["type"], t.get("limit"))
                    set_state(t["id"], "EXECUTED")
                    log.info({"event": "paper.order.exec", "ticket": t["id"], "result": res})


