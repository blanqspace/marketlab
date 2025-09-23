from typing import List
from shared.utils.logger import get_logger
from shared.ibkr.ibkr_symbol_checker import fetch_symbols_via_ibkr_fallback
from shared.symbols.symbol_loader import load_symbols_from_json, load_cached_symbols

logger = get_logger("symbol_source")


def get_active_symbols() -> List[str]:
    """
    Quelle: JSON → Cache → IBKR-Fallback → []
    """
    sources = [
        load_symbols_from_json,
        load_cached_symbols,
        fetch_symbols_via_ibkr_fallback
    ]

    for source in sources:
        try:
            symbols = source()
            if symbols:
                return symbols
        except Exception as e:
            logger.warning(f"⚠️ Fehler bei Symbolquelle {source.__name__}: {e}")

    logger.warning("⚠️ Keine aktiven Symbole gefunden.")
    return []

