from shared.ibkr_client.ibkr_client import IBKRClient
from shared.thread_tools.thread_tools import start_named_thread
from shared.logger.logger import get_logger
from shared.client_registry.client_registry import registry
from shared.config_loader.config_loader import load_json_config
import time

logger = get_logger("symbol_fetcher", log_to_console=True)

def fetch_task(symbol: str):
    try:
        client = IBKRClient(module="symbol_fetcher_pool", task=f"fetch_{symbol}")
        ib = client.connect()

        contract = ib.qualifyContracts(ib.stock(symbol))[0]

        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr="1 D",
            barSizeSetting="5 mins",
            whatToShow="TRADES",
            useRTH=True,
            formatDate=1
        )

        logger.info(f"{symbol}: {len(bars)} Balken empfangen")
        client.disconnect()

    except Exception as e:
        logger.error(f"❌ Fehler bei {symbol}: {e}")

def run():
    logger.info("🚀 Symbol-Fetcher mit dynamischer Symbolquelle")
    symbol_tasks = load_json_config("config/symbol_tasks.json", fallback=[])

    active_symbols = [task["symbol"] for task in symbol_tasks if task.get("active", False)]

    if not active_symbols:
        logger.warning("⚠️ Keine aktiven Symbole gefunden.")
        return

    for symbol in active_symbols:
        start_named_thread(
            name=f"fetch_{symbol}",
            target=fetch_task,
            args=(symbol,),
            daemon=True
        )

    time.sleep(15)
    print("\n📊 IBKR-Statusübersicht:")
    print(registry.get_status_report())

if __name__ == "__main__":
    run()
