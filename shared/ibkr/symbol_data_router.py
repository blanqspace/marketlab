from typing import Literal, Dict, Any
from shared.symbols.symbol_status_cache import load_cached_symbols

Method = Literal["live", "historical", "none"]


def get_data_method(symbol: str) -> Method:
    """
    Rückgabe: 'live' | 'historical' | 'none'
    Logik: Cache prüfen → live? → historical/delayed? → none
    """
    cached = load_cached_symbols()
    if not cached:
        return "none"

    data = cached.get("symbols")
    if isinstance(data, dict):
        info: Dict[str, Any] = data.get(symbol, {})
        if isinstance(info, dict):
            if info.get("live"):
                return "live"
            if info.get("historical") or info.get("delayed"):
                return "historical"
    return "none"
