# shared/utils/logger.py
from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

def get_logger(name: str, log_dir: str = "logs", level: int = logging.INFO) -> logging.Logger:
    """
    Einheitliche Logger-Factory.
    - Console + RotatingFile (2 MB, 5 Backups)
    - UTF-8, kein doppeltes Handler-Anfügen
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    fh = RotatingFileHandler(Path(log_dir) / f"{name}.log", maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger

