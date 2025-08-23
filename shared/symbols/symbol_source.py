from typing import List
from shared.utils.logger import get_logger
from shared.ibkr.ibkr_symbol_checker import fetch_symbols_via_ibkr_fallback


logger = get_logger("symbol_source")


def get_active_symbols() -> List[str]:
    """
    Hauptzugangspunkt für Symbolquelle.
    Versucht JSON → Cache → IBKR → sonst Warnung
    """
    sources = [
        load_symbols_from_json,
        # load_symbols_from_db,  # ← später möglich
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
