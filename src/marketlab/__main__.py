from __future__ import annotations

from marketlab.cli import app
from marketlab.services.telegram_service import telegram_service


def main() -> None:
    telegram_service.notify_start("CLI")
    try:
        app()
    except Exception as exc:
        telegram_service.notify_error(str(exc))
        raise
    finally:
        telegram_service.notify_end("CLI")


if __name__ == "__main__":
    main()
