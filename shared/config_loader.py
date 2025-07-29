import os
import json
from pathlib import Path
from typing import Any, Dict, Optional
from dotenv import load_dotenv

from shared.logger import get_logger

logger = get_logger("config_loader")


def load_env(env_path: Optional[str] = ".env") -> None:
    """
    Lädt Umgebungsvariablen aus .env-Datei.
    """
    env_file = Path(env_path)
    if not env_file.exists():
        logger.warning(f".env-Datei nicht gefunden: {env_path}")
        return

    load_dotenv(dotenv_path=env_file)
    logger.info(f".env geladen: {env_path}")


def get_env_var(key: str, required: bool = True) -> Optional[str]:
    """
    Gibt Umgebungsvariable zurück. Loggt Warnung, wenn nicht vorhanden.
    """
    value = os.getenv(key)
    if required and not value:
        logger.warning(f"Umgebungsvariable '{key}' fehlt!")
    return value


def load_json_config(path: str, fallback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Lädt eine JSON-Konfigurationsdatei. Gibt Fallback zurück bei Fehlern.
    """
    config_path = Path(path)
    if not config_path.exists():
        logger.error(f"Konfigurationsdatei nicht gefunden: {path}")
        return fallback or {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            logger.info(f"Konfiguration geladen: {path}")
            return data
    except json.JSONDecodeError as e:
        logger.error(f"Ungültige JSON-Struktur in {path}: {e}")
        return fallback or {}
