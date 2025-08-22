import logging
import os
import json
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from typing import Optional

LOG_DIR = Path("logs")


def get_logger(
    modulname: str,
    log_to_console: bool = False,
    log_as_json: bool = False,
    log_level: Optional[str] = None
) -> logging.Logger:
    """
    Erstellt einen Logger mit täglicher Rotation.
    Unterstützt:
    - Log-Level aus Parameter oder ENV (LOG_LEVEL)
    - optional JSON-Formatierung
    - getrennte Log-Dateien pro Modul
    """
    logger = logging.getLogger(modulname)
    if logger.handlers:
        return logger  # Logger bereits initialisiert

    # Log-Level bestimmen
    level_str = log_level or os.getenv("LOG_LEVEL", "DEBUG").upper()
    level = getattr(logging, level_str, logging.DEBUG)
    logger.setLevel(level)

    # Log-Datei
    log_subdir = LOG_DIR / modulname
    log_subdir.mkdir(parents=True, exist_ok=True)
    logfile_path = log_subdir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    # FileHandler
    file_handler = TimedRotatingFileHandler(
        filename=logfile_path,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        delay=False
    )

    if log_as_json:
        formatter = logging.Formatter(
            fmt=json.dumps({
                "time": "%(asctime)s",
                "level": "%(levelname)s",
                "message": "%(message)s"
            }),
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:
        formatter = logging.Formatter(
            fmt=f"[{modulname}] %(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
