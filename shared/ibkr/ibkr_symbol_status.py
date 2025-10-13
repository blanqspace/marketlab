import logging
import time

from ib_insync import IB, Forex, Stock

from shared.ibkr.ibkr_client import IBKRClient

LOG = logging.getLogger(__name__)

DEFAULT_SYMBOLS = [
    ("AAPL", "stock"),
    ("SPY", "stock"),
    ("MSFT", "stock"),
    ("GOOG", "stock"),
    ("EURUSD", "forex"),
    ("USDJPY", "forex"),
    ("ES", "future")
]

def get_contract(symbol: str, typ: str):
    if typ == "stock":
        return Stock(symbol, "SMART", "USD")
    elif typ == "forex":
        return Forex(symbol)
    else:
        return None

def check_symbol_availability(ib: IB, symbol: str, typ: str) -> str:
    contract = get_contract(symbol, typ)
    if not contract:
        return "❓ Unbekannter Typ"

    def _try_market_data(market_data_type: int, label: str) -> str | None:
        ticker = None
        try:
            ib.reqMarketDataType(market_data_type)
            ticker = ib.reqMktData(contract, "", False, False)
            time.sleep(0.8)
            if ticker.bid or ticker.ask:
                return label
        except Exception as exc:
            LOG.warning(
                "Failed to fetch %s market data for %s (%s): %s",
                label.lower(),
                symbol,
                typ,
                exc,
            )
        finally:
            if ticker is not None:
                try:
                    ib.cancelMktData(ticker)
                except Exception as cancel_exc:
                    LOG.debug("Error cancelling market data for %s: %s", symbol, cancel_exc)
        return None

    live = _try_market_data(1, "✅ Live")
    if live:
        return live

    delayed = _try_market_data(3, "🟡 Delayed")
    if delayed:
        return delayed

    return "❌ Kein Zugriff"

def interactive_symbol_selection(default_list=None):
    if default_list is None:
        default_list = DEFAULT_SYMBOLS

    ibkr = IBKRClient(module="availability", task="check")
    ib = ibkr.connect()

    results = []
    try:
        for sym, typ in default_list:
            status = check_symbol_availability(ib, sym, typ)
            results.append((sym, typ, status))
    finally:
        ibkr.disconnect()

    print("\n📊 Verfügbare Symbole:")
    for i, (s, t, r) in enumerate(results):
        print(f"{i+1}. {s.ljust(8)} | {t.ljust(6)} | {r}")

    live_or_delayed = [(i, s, t) for i, (s, t, r) in enumerate(results) if r in ["✅ Live", "🟡 Delayed"]]
    if not live_or_delayed:
        print("❌ Kein Symbol verfügbar.")
        return None

    print("\n🔎 Wähle ein Symbol per Nummer:")
    for i, s, t in live_or_delayed:
        print(f"[{i+1}] {s} ({t})")

    try:
        choice = int(input("➡️ Auswahl: ")) - 1
        symbol, typ = results[choice][0], results[choice][1]
        return symbol, typ
    except Exception:
        print("❌ Ungültige Auswahl.")
        return None
