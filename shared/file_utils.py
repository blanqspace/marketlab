import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from shared.logger import get_logger

logger = get_logger("file_utils")


def ensure_directory(path: Union[str, Path]) -> None:
    """
    Erstellt den Ordner, falls er nicht existiert.
    """
    Path(path).mkdir(parents=True, exist_ok=True)
    logger.debug(f"Verzeichnis sichergestellt: {path}")


def safe_write_text(path: Union[str, Path], content: str) -> None:
    """
    Schreibt Textinhalt sicher in eine Datei.
    """
    try:
        Path(path).write_text(content, encoding="utf-8")
        logger.debug(f"Text geschrieben nach: {path}")
    except Exception as e:
        logger.error(f"Fehler beim Schreiben nach {path}: {e}")


def safe_read_text(path: Union[str, Path]) -> Optional[str]:
    """
    Liest Textinhalt aus einer Datei, wenn vorhanden.
    """
    try:
        return Path(path).read_text(encoding="utf-8")
    except Exception as e:
        logger.warning(f"Lesefehler bei {path}: {e}")
        return None


def load_json_file(path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    Lädt eine JSON-Datei als Dict.
    """
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Fehler beim Laden von JSON {path}: {e}")
        return None


def write_json_file(path: Union[str, Path], data: Dict[str, Any]) -> None:
    """
    Speichert ein Dict als JSON-Datei.
    """
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        Path(path).write_text(content, encoding="utf-8")
        logger.debug(f"JSON gespeichert nach: {path}")
    except Exception as e:
        logger.error(f"Fehler beim Speichern von JSON {path}: {e}")


def file_exists(path: Union[str, Path]) -> bool:
    return Path(path).exists()
