# shared/symbol_data_router.py

def get_data_method(symbol: str) -> str:
    """
    Gibt zurück: 'live', 'historical' oder 'none'
    """
    info = load_availability_for(symbol)
    if info.get("live"):
        return "live"
    elif info.get("historical"):
        return "historical"
    return "none"
