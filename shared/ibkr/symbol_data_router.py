from typing import Literal, Dict, Any
from shared.symbols.symbol_status_cache import load_cached_symbols

Method = Literal["live","delayed","historical","none"]


def get_data_method(symbol: str) -> Method:
    """
    Rückgabe: 'live' | 'delayed' | 'historical' | 'none'
    Logik: Cache prüfen → live? → delayed? → historical? → none
    """
    cached = load_cached_symbols()
    if not cached or "symbols" not in cached:
        return "none"
    data = cached["symbols"]
    if not isinstance(data, dict):
        return "none"
    info = data.get(symbol, {}) or {}
    if info.get("live"): return "live"
    if info.get("delayed"): return "delayed"
    if info.get("historical"): return "historical"
    return "none"
