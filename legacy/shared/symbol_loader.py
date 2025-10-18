from typing import List, Optional
from pathlib import Path
from datetime import datetime
import json
from shared.utils.logger import get_logger
from shared.utils.file_utils import load_json_file, write_json_file

logger = get_logger("symbol_loader")


def load_symbols_from_json() -> List[str]:
    """
    Lädt aktive Symbole aus config/active_symbols.json
    """
    try:
        config_path = Path("config/active_symbols.json")
        data = load_json_file(config_path)
        symbols = data.get("symbols", [])
        if symbols:
            logger.info(f"📄 {len(symbols)} Symbole aus active_symbols.json geladen")
            return symbols
        else:
            logger.warning("📄 Keine Symbole in active_symbols.json gefunden")
            return []
    except Exception as e:
        logger.error(f"❌ Fehler beim Laden von active_symbols.json: {e}")
        return []


def load_cached_symbols() -> List[str]:
    """
    Lädt Symbole aus config/cached_symbols.json (Fallback)
    """
    try:
        config_path = Path("config/cached_symbols.json")
        data = load_json_file(config_path)
        symbols = data.get("symbols", [])
        if symbols:
            logger.info(f"💾 {len(symbols)} Symbole aus Cache geladen")
            return symbols
        else:
            logger.warning("💾 Keine Symbole im Cache gefunden")
            return []
    except Exception as e:
        logger.error(f"❌ Fehler beim Laden des Symbol-Cache: {e}")
        return []


def cache_symbols(symbols: List[str]) -> None:
    """
    Speichert Symbole in config/cached_symbols.json mit Zeitstempel
    """
    try:
        config_path = Path("config/cached_symbols.json")
        data = {
            "symbols": symbols,
            "fetched_at": datetime.now().isoformat()
        }
        write_json_file(config_path, data)
        logger.info(f"💾 {len(symbols)} Symbole im Cache gespeichert")
    except Exception as e:
        logger.error(f"❌ Fehler beim Speichern des Symbol-Cache: {e}")

