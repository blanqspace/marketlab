from __future__ import annotations

import requests
from marketlab.settings import settings


class TelegramService:
    def __init__(self) -> None:
        telegram = settings.telegram
        self.enabled = telegram.enabled
        self.token = telegram.bot_token.get_secret_value() if telegram.bot_token else None
        self.chat_id = telegram.chat_control

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send_text(self, text: str) -> None:
        if not self.enabled or not self.token or not self.chat_id:
            return
        try:
            payload = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            requests.post(self._url("sendMessage"), json=payload, timeout=5)
        except Exception as exc:
            print(f"[WARN] Telegram send failed: {exc}")

    def notify_start(self, mode: str) -> None:
        self.send_text(f"\u25b6\ufe0f MarketLab started in <b>{mode}</b> mode.")

    def notify_end(self, mode: str) -> None:
        self.send_text(f"\u23f9\ufe0f MarketLab finished mode <b>{mode}</b>.")

    def notify_error(self, msg: str) -> None:
        self.send_text(f"\u26a0\ufe0f MarketLab error: <b>{msg}</b>")


telegram_service = TelegramService()
