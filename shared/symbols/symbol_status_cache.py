import json
import os
from datetime import datetime

CACHE_PATH = "data/available_symbols.json"

def save_available_symbols(data: dict):
    """
    Speichert Symbolverfügbarkeit als JSON.
    """
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "symbols": data
        }, f, indent=2)

def load_cached_symbols():
    """
    Lädt gespeicherte Symbolverfügbarkeit (falls vorhanden).
    """
    if not os.path.exists(CACHE_PATH):
        return None

    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

