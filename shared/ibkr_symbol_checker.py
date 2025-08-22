from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from ib_insync import Stock
from shared.logger import get_logger
from shared.ibkr_client import IBKRClient
from shared.client_registry import registry
from shared.symbol_loader import cache_symbols

logger = get_logger("ibkr_symbol_checker")


def fetch_symbols_via_ibkr_fallback(candidates: Optional[List[str]] = None) -> List[str]:
    """
    Fragt bekannte Symbole bei IBKR ab – gibt nur gültige zurück.
    """
    logger.info("🌐 Hole Fallback-Symbole über IBKR...")

    if candidates is None:
        candidates = ["AAPL", "MSFT", "SPY", "GOOG", "TSLA", "ES", "NVDA", "QQQ", "AMZN", "META"]

    client_id = registry.get_client_id("symbol_probe") or 199
    ibkr = IBKRClient(client_id=client_id, module="symbol_probe")

    try:
        ib = ibkr.connect()
        valid_symbols = []

        def check_symbol(sym: str) -> Optional[str]:
            try:
                contract = Stock(sym, "SMART", "USD")
                details = ib.reqContractDetails(contract)
                if details:
                    logger.info(f"✅ Symbol gültig: {sym}")
                    return sym
                else:
                    logger.warning(f"❌ Symbol ungültig: {sym}")
            except Exception as e:
                logger.warning(f"⚠️ Fehler bei {sym}: {e}")
            return None

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {executor.submit(check_symbol, sym): sym for sym in candidates}
            for future in as_completed(futures):
                result = future.result()
                if result:
                    valid_symbols.append(result)

        cache_symbols(valid_symbols)
        return valid_symbols

    except Exception as e:
        logger.error(f"❌ Fehler bei IBKR-Symbolprüfung: {e}")
        return []

    finally:
        ibkr.disconnect()
