import json
from pathlib import Path
from typing import Any, Optional, Union, Type

from shared.utils.logger import get_logger

logger = get_logger("file_utils")


def ensure_directory(path: Union[str, Path]) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)
    logger.debug("📁 Verzeichnis sichergestellt: %s", path)


def safe_write_text(path: Union[str, Path], content: str, backup: bool = False) -> None:
    try:
        path = Path(path)
        if backup and path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            logger.info("📄 Backup erstellt: %s", backup_path)

        path.write_text(content, encoding="utf-8")
        logger.debug(f"📝 Text geschrieben nach: {path}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Schreiben nach {path}: {e}")


def safe_read_text(path: Union[str, Path]) -> Optional[str]:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, IOError) as e:
        logger.warning("⚠️ Lesefehler bei %s: %s", path, e)
        return None


def load_json_file(
    path: Union[str, Path],
    fallback: Optional[Any] = None,
    expected_type: Optional[Type] = dict
) -> Optional[Any]:
    try:
        text = safe_read_text(path)
        if text is None:
            return fallback or expected_type()

        data = json.loads(text)

        if expected_type and not isinstance(data, expected_type):
            logger.error(f"❌ Typfehler in {path}: erwartet {expected_type.__name__}, erhalten {type(data).__name__}")
            return fallback or expected_type()

        logger.debug(f"📥 JSON geladen: {path}")
        return data
    except Exception as e:
        logger.warning(f"⚠️ Fehler beim Laden von JSON {path}: {e}")
        return fallback or expected_type()


def write_json_file(
    path: Union[str, Path],
    data: Any,
    backup: bool = False
) -> None:
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False)
        safe_write_text(path, content, backup=backup)
        logger.debug(f"📤 JSON gespeichert nach: {path}")
    except Exception as e:
        logger.error(f"❌ Fehler beim Speichern von JSON {path}: {e}")


def file_exists(path: Union[str, Path]) -> bool:
    return Path(path).exists()
