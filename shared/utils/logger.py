# shared/utils/logger.py
import logging, os, json
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from typing import Optional

LOG_DIR = Path("logs")

class _DeDupeFilter(logging.Filter):
    """
    Unterdrückt Wiederholungen derselben Log-Zeile (name, level, msg) für 300 s.
    """
    last_seen = {}
    cooldown_sec = 300
    def filter(self, record: logging.LogRecord) -> bool:
        key = (record.name, record.levelno, record.getMessage())
        now = int(datetime.now().timestamp())
        prev = self.last_seen.get(key, 0)
        if now - prev < self.cooldown_sec:
            return False
        self.last_seen[key] = now
        return True

def get_logger(
    modulname: str,
    log_to_console: bool = False,
    log_as_json: bool = False,
    log_level: Optional[str] = None
) -> logging.Logger:
    logger = logging.getLogger(modulname)
    if logger.handlers:
        return logger

    level_str = log_level or os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)
    logger.setLevel(level)

    log_subdir = LOG_DIR / modulname
    log_subdir.mkdir(parents=True, exist_ok=True)
    logfile_path = log_subdir / f"{datetime.now().strftime('%Y-%m-%d')}.log"

    fh = TimedRotatingFileHandler(
        filename=logfile_path, when="midnight",
        backupCount=7, encoding="utf-8", delay=False
    )

    if log_as_json:
        fmt = json.dumps({"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"})
        formatter = logging.Formatter(fmt=fmt, datefmt="%Y-%m-%d %H:%M:%S")
    else:
        formatter = logging.Formatter(
            fmt=f"[{modulname}] %(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    fh.setFormatter(formatter)
    fh.addFilter(_DeDupeFilter())
    logger.addHandler(fh)

    if log_to_console:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        ch.addFilter(_DeDupeFilter())
        logger.addHandler(ch)

    return logger
