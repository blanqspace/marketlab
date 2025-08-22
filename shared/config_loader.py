import os
import json
from pathlib import Path
from typing import Any, Dict, Optional, Type, Union
from dotenv import load_dotenv
from shared.logger import get_logger

logger = get_logger("config_loader")


def _resolve_env_path(base_path: Optional[str] = ".env") -> Path:
    """
    Ermittelt den Pfad zur .env-Datei anhand von ENV_MODE (z. B. .env.dev)
    """
    env_mode = os.getenv("ENV_MODE", "").strip().lower()

    if env_mode:
        candidate = f"{base_path}.{env_mode}"
        candidate_path = Path(candidate)
        if candidate_path.exists():
            logger.info(f".env-Umgebung erkannt: {env_mode} → {candidate}")
            return candidate_path

    return Path(base_path)


def load_env(env_path: Optional[str] = ".env") -> None:
    """
    Lädt Umgebungsvariablen aus .env-Datei, unterstützt ENV_MODE
    """
    path = _resolve_env_path(env_path)

    if not path.exists():
        logger.warning(f".env-Datei nicht gefunden: {path}")
        return

    load_dotenv(dotenv_path=path)
    logger.info(f".env geladen: {path}")


def get_env_var(key: str, required: bool = True) -> Optional[str]:
    """
    Gibt Umgebungsvariable zurück. Loggt Warnung, wenn nicht vorhanden.
    """
    value = os.getenv(key)
    if required and not value:
        logger.warning(f"Umgebungsvariable '{key}' fehlt!")
    return value


def load_json_config(
    path: str,
    fallback: Optional[Any] = None,
    expected_type: Optional[Type] = dict
) -> Any:
    """
    Lädt eine JSON-Konfigurationsdatei. Prüft optional den Typ.
    """
    config_path = Path(path)
    if not config_path.exists():
        logger.error(f"⚠️ Konfigurationsdatei nicht gefunden: {path}")
        return fallback or ({} if expected_type == dict else [])

    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

            if expected_type and not isinstance(data, expected_type):
                logger.error(f"❌ Typfehler in {path}: erwartet {expected_type.__name__}, erhalten {type(data).__name__}")
                return fallback or expected_type()  # dict() oder list() usw.

            logger.info(f"Konfiguration geladen: {path}")
            return data

    except json.JSONDecodeError as e:
        logger.error(f"❌ Ungültige JSON-Struktur in {path}: {e}")
        return fallback or ({} if expected_type == dict else [])

