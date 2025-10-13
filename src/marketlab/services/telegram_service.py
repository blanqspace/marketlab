from __future__ import annotations
from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

from marketlab.net.http import SafeHttpClient
from src.marketlab.core.timefmt import iso_utc
from src.marketlab.ipc import bus

@dataclass
class _TGSettings:
    enabled: bool
    mock: bool
    bot_token: str | None = None
    chat_control: int | None = None

class TelegramService:
    def __init__(self):
        self._running = False
        self._mock = False
        self._base = Path("runtime/telegram_mock")
        self._bot_token: str | None = None
        self._chat_control: int | None = None
        self._http = SafeHttpClient({"api.telegram.org"}, timeout=10)
        self._log = logging.getLogger(__name__)

    def start_poller(self, settings: Any):
        if self._running:
            return
        tg = getattr(settings, "telegram", None)
        enabled = bool(getattr(tg, "enabled", False))
        self._mock = bool(getattr(tg, "mock", False))
        # Token/Chat merken
        tok = getattr(tg, "bot_token", None)
        try:
            self._bot_token = tok.get_secret_value() if tok is not None and hasattr(tok, "get_secret_value") else (str(tok) if tok is not None else None)
        except Exception:
            self._bot_token = str(tok) if tok is not None else None
        chat = getattr(tg, "chat_control", None)
        try:
            self._chat_control = int(chat) if chat is not None else None
        except Exception:
            self._chat_control = None
        # Persist TG state for dashboard
        try:
            bus.set_state("tg.enabled", "1" if enabled else "0")
            bus.set_state("tg.mock", "1" if self._mock else "0")
            bus.set_state("tg.bot_username", "")
            bus.set_state("tg.chat_control", str(self._chat_control or ""))
            allow = getattr(tg, "allowlist", []) if tg else []
            bus.set_state("tg.allowlist_count", str(len(allow or [])))
        except Exception as exc:
            self._log.warning("Failed to publish telegram state: %s", exc)
        if not enabled:
            return
        if self._mock:
            self._base.mkdir(parents=True, exist_ok=True)
        # Real-Poller wäre hier; aktuell Mock/No-Op
        self._running = True

    def stop_poller(self):
        if not self._running:
            return
        # Real-Stop wäre hier
        self._running = False

    def _is_enabled(self) -> bool:
        return self._running

    def _write_mock(self, name: str, payload: dict):
        if not self._mock:
            return
        self._base.mkdir(parents=True, exist_ok=True)
        (self._base / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _send_real(self, method: str, payload: dict):
        url = f"https://api.telegram.org/bot{self._bot_token}/{method}"
        response = self._http.post(url, json=payload, timeout=10)
        return response.json()

    def _api_post(self, method: str, payload: dict):
        if not getattr(self, "_bot_token", None):
            return None
        return self._send_real(method, payload)

    def notify_start(self, mode: str):
        if not self._is_enabled():
            return
        text = f"🟢 {mode}: gestartet"
        if self._mock:
            self._write_mock("sendMessage_start", {"text": text})
        else:
            self._send_real("sendMessage", {"chat_id": self._chat_control, "text": text})

    def notify_end(self, mode: str):
        if not self._is_enabled():
            return
        text = f"⚪ {mode}: beendet"
        if self._mock:
            self._write_mock("sendMessage_end", {"text": text})
        else:
            self._send_real("sendMessage", {"chat_id": self._chat_control, "text": text})

    def notify_error(self, msg: str):
        if not self._is_enabled():
            return
        if self._mock:
            self._write_mock("sendMessage_error", {"text": f"🔴 Fehler: {msg}"})
        else:
            self._send_real("sendMessage", {"chat_id": self._chat_control, "text": f"🔴 Fehler: {msg}"})

    # --- Orders ---
    def send_order_ticket(self, t: dict):
        if not self._is_enabled(): return
        payload = {
            "chat_id": self._chat_control,
            "text": f"🧾 Order {t['id']}\n{t['side']} {t['qty']} {t['symbol']} @ {t.get('limit') or 'MKT'}\nSL:{t.get('sl')} TP:{t.get('tp')}",
            "reply_markup": {
                "inline_keyboard": [[
                    {"text":"✅ Bestätigen", "callback_data": f"ORD:CONFIRM:{t['id']}"},
                    {"text":"❌ Ablehnen",   "callback_data": f"ORD:REJECT:{t['id']}"}
                ]]
            }
        }
        if self._mock:
            self._write_mock(f"sendMessage_order_{t['id']}", payload)
        else:
            self._send_real("sendMessage", payload)

    def handle_callback(self, data: str):
        # Nur Mock: schreibe Auswahl ins File. In Real-Mode hier API-Callback entpacken.
        if not data.startswith("ORD:"): return
        self._write_mock("callback_received", {"data": data})

telegram_service = TelegramService()
