from __future__ import annotations
import requests
import time
from threading import Thread, Event
from marketlab.settings import settings
from marketlab.core.state_manager import STATE, Command

def _to_ints(csv: str | None) -> set[int]:
    if not csv:
        return set()
    return {int(x.strip()) for x in str(csv).split(",") if x.strip()}

class _RateLimiter:
    def __init__(self, per_sec: float = 1.0) -> None:
        self.per = max(0.1, per_sec)
        self._last = 0.0
    def allow(self) -> bool:
        now = time.time()
        if now - self._last >= 1.0 / self.per:
            self._last = now
            return True
        return False

class TelegramService:
    def __init__(self) -> None:
        self.enabled: bool = settings.telegram.enabled
        self.token = settings.telegram.bot_token.get_secret_value() if settings.telegram.bot_token else None
        self.chat_id = settings.telegram.chat_control
        self.allow = _to_ints(settings.telegram.allowlist_csv)
        self.brand: str = settings.app_brand
        self._stop = Event()
        self._thread: Thread | None = None
        self._rl = _RateLimiter(per_sec=1.0)
        self._notified_start: set[str] = set()

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send_text(self, text: str) -> None:
        if not (self.enabled and self.token and self.chat_id):
            return
        if not self._rl.allow():
            return
        try:
            requests.post(self._url("sendMessage"), json={"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}, timeout=6)
        except Exception:
            pass

    # Notifications (single-flight per mode run)
    def notify_start(self, mode: str) -> None:
        key = f"start:{mode}"
        if key in self._notified_start:
            return
        self._notified_start.add(key)
        self.send_text(f"▶️ {self.brand} started: <b>{mode}</b>")

    def notify_end(self, mode: str) -> None:
        self.send_text(f"⏹ {self.brand} finished: <b>{mode}</b>")
        self._notified_start.discard(f"start:{mode}")

    def notify_error(self, msg: str) -> None:
        self.send_text(f"⚠️ {self.brand} error: <b>{msg[:300]}</b>")

    # Poller
    def start_poller(self) -> None:
        if not (self.enabled and self.token):
            return
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._poll_loop, name="tg_poller", daemon=True)
        self._thread.start()

    def stop_poller(self) -> None:
        self._stop.set()

    def _poll_loop(self) -> None:
        offset = 0
        while not self._stop.is_set():
            try:
                r = requests.get(self._url("getUpdates"), params={"timeout": 15, "offset": offset}, timeout=20)
                data = r.json()
                if not data.get("ok"):
                    time.sleep(2); continue
                for upd in data.get("result", []):
                    offset = max(offset, upd["update_id"] + 1)
                    msg = upd.get("message") or upd.get("edited_message")
                    if not msg: 
                        continue
                    user_id = msg.get("from", {}).get("id")
                    text = (msg.get("text") or "").strip()
                    chat_id = msg.get("chat", {}).get("id")
                    if not text or not user_id or not chat_id:
                        continue
                    if self.chat_id and int(chat_id) != int(self.chat_id):
                        continue
                    if self.allow and int(user_id) not in self.allow:
                        continue
                    self._handle_text(text)
            except Exception:
                time.sleep(2)

    def _handle_text(self, text: str) -> None:
        t = text.lower()
        if t.startswith("/help"):
            self.send_text("Commands: /status, /pause, /resume, /stop, /ping")
        elif t.startswith("/ping"):
            self.send_text("pong")
        elif t.startswith("/status"):
            snap = STATE.snapshot()
            self.send_text(f"ℹ️ status: mode={snap['mode']}, state={snap['state']}, uptime={snap['uptime']}s, progress={snap['processed']}/{snap['target']}")
        elif t.startswith("/pause"):
            STATE.post(Command.PAUSE); self.send_text("⏸ paused")
        elif t.startswith("/resume"):
            STATE.post(Command.RESUME); self.send_text("▶️ resumed")
        elif t.startswith("/stop"):
            STATE.post(Command.STOP); self.send_text("🛑 stopping")
        else:
            self.send_text("Unknown. Use /help")

telegram_service = TelegramService()
