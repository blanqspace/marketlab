from ib_insync import Stock
from shared.ibkr_client import IBKRClient
from shared.logger import get_logger
from shared.lock_tools import create_lock, remove_lock

import time

logger = get_logger("live_market_data", log_to_console=True)

def fetch_realtime_data(symbol: str = "AAPL", duration_sec: int = 20):
    lock_name = f"live_data_{symbol.lower()}"
    if not create_lock(lock_name, note=f"Live-Daten {symbol}"):
        return

    try:
        ibkr = IBKRClient(module="realtime", task=f"live_{symbol}")
        ib = ibkr.connect()

        contract = Stock(symbol, "SMART", "USD")
        ib.reqMarketDataType(1)  # ← Diese Zeile ersetzt MarketDataType.Live
        ticker = ib.reqMktData(contract, "", False, False)

        logger.info(f"📡 Abonniere Live-Daten für {symbol} ({duration_sec} Sekunden) ...")

        start_time = time.time()
        while time.time() - start_time < duration_sec:
            ib.sleep(1)
            if ticker.last:
                logger.info(f"{symbol} → Last: {ticker.last} | Bid: {ticker.bid} | Ask: {ticker.ask}")

        ib.cancelMktData(contract)
        ibkr.disconnect()
        logger.info(f"🛑 Live-Daten für {symbol} beendet.")

    except Exception as e:
        logger.error(f"❌ Fehler beim Abrufen von Live-Daten für {symbol}: {e}")

    finally:
        remove_lock(lock_name)
