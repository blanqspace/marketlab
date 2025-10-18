from pathlib import Path
from typing import List, Optional
import json
from datetime import datetime
from shared.utils.file_utils import load_json_file
from shared.utils.logger import get_logger

logger = get_logger("symbol_loader")

CONFIG_PATH = Path("config/active_symbols.json")
CACHE_PATH = Path("config/cached_symbols.json")


def cache_symbols(symbols: List[str], path: Path = CACHE_PATH):
    data = {
        "symbols": symbols,
        "fetched_at": datetime.utcnow().isoformat()
    }
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info(f"🧊 Symbol-Cache gespeichert ({len(symbols)} Symbole)")
    except Exception as e:
        logger.error(f"❌ Fehler beim Schreiben des Caches: {e}")


def load_cached_symbols(path: Path = CACHE_PATH) -> Optional[List[str]]:
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and "symbols" in data:
            logger.info(f"♻️ Verwende Symbol-Cache vom {data.get('fetched_at', '?')}")
            return data["symbols"]
    except Exception as e:
        logger.warning(f"⚠️ Fehler beim Laden des Symbol-Caches: {e}")
    return None


def load_symbols_from_json(path: Path = CONFIG_PATH) -> Optional[List[str]]:
    if not path.exists():
        return None
    data = load_json_file(path)
    if isinstance(data, dict) and "symbols" in data:
        symbols = data["symbols"]
        if isinstance(symbols, list) and all(isinstance(s, str) for s in symbols):
            logger.info(f"📥 Symbole geladen aus JSON: {symbols}")
            return symbols
        else:
            logger.warning("⚠️ Symbolformat in JSON ungültig")
    return None

