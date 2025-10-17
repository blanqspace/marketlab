
import json
import logging
import sys


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        payload = {
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        # Include token if present; never include internal order_id in logs
        extras = getattr(record, "__dict__", {})
        tok = extras.get("token")
        if tok:
            payload["token"] = tok
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

_def_level = logging.INFO


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else _def_level
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(_JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
