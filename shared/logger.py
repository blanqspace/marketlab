import logging
import os
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime

LOG_DIR = Path("logs")


def get_logger(modulname: str, log_to_console: bool = False) -> logging.Logger:
    """
    Erstellt einen Logger mit täglicher Rotation.
    Log-Dateien werden gespeichert unter: logs/<modulname>/YYYY-MM-DD.log
    """

    # Logger einmalig erzeugen
    logger = logging.getLogger(modulname)
    if logger.handlers:
        return logger  # Logger bereits initialisiert

    logger.setLevel(logging.DEBUG)

    # Logverzeichnis erstellen, z. B. logs/data_fetcher/
    log_subdir = LOG_DIR / modulname
    log_subdir.mkdir(parents=True, exist_ok=True)

    # Dateiname nach heutigem Datum
    logfile_path = log_subdir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    # FileHandler mit täglicher Rotation (behält 7 Tage)
    file_handler = TimedRotatingFileHandler(
        filename=logfile_path,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
        delay=False
    )

    # Formatierung: Zeit, Level, Nachricht
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Optional: Konsolen-Ausgabe
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger
