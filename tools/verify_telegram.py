"""
Verifies Telegram integration by sending a test message if enabled.
"""
from marketlab.services.telegram_service import telegram_service


if telegram_service.enabled:
    telegram_service.send_text("\u2705 MarketLab Telegram connection test OK.")
    print('{"ok": true, "telegram": true}')
else:
    print('{"ok": true, "telegram": false}')
