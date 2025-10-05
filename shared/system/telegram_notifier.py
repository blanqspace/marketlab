import json, time
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests

RUNTIME_DIR = Path("runtime"); (RUNTIME_DIR).mkdir(parents=True, exist_ok=True)
EVENTS_DIR = Path("reports") / "events"; EVENTS_DIR.mkdir(parents=True, exist_ok=True)

def _read_state() -> Dict[str, Any]:
    p = RUNTIME_DIR / "state.json"
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _write_state(st: Dict[str, Any]) -> None:
    (RUNTIME_DIR / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")

def _write_startup(res: Dict[str, Any]) -> None:
    (EVENTS_DIR / "startup.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

class TelegramNotifier:
    def __init__(self, token: str, enabled: bool, routes: Optional[Dict[str, Any]]=None, timeout: float=10.0):
        self.enabled = bool(enabled)
        self.token = (token or "").strip()
        self.routes = routes or {}
        self.timeout = timeout
        self.base = f"https://api.telegram.org/bot{self.token}"

        # Mock-Schalter und Mock-Ordner

        self.mock = str(os.getenv("TELEGRAM_MOCK", "0")) == "1"
        self._mock_dir = Path("runtime/telegram_mock")
        self._mock_dir.mkdir(parents=True, exist_ok=True)

    def _get(self, method: str, params: Dict[str, Any]=None) -> Dict[str, Any]:
        r = requests.get(f"{self.base}/{method}", params=params or {}, timeout=self.timeout) if self.enabled else None
        if not self.enabled: return {}
        r.raise_for_status(); return r.json()

    def _post(self, method: str, data: Dict[str, Any]) -> Dict[str, Any]:
        r = requests.post(f"{self.base}/{method}", json=data, timeout=self.timeout) if self.enabled else None
        if not self.enabled: return {}
        r.raise_for_status(); return r.json()

    def get_me(self) -> Optional[Dict[str, Any]]:
        if not self.enabled: return None
        return self._get("getMe").get("result")

    def send_text(self, chat_id: int, text: str) -> Optional[Dict[str, Any]]:
        if not self.enabled: return None
        return self._post("sendMessage", {"chat_id": chat_id, "text": text}).get("result")

    def send_inline_keyboard(self, chat_id: int, text: str, buttons: List[List[Dict[str, Any]]]) -> Optional[Dict[str, Any]]:
        if not self.enabled: return None
        payload = {"chat_id": chat_id, "text": text, "reply_markup": {"inline_keyboard": buttons}}
        return self._post("sendMessage", payload).get("result")

    def edit_message_reply_markup(self, chat_id: int, message_id: int, reply_markup: Optional[Dict[str, Any]]=None):
        if not self.enabled: return None
        payload = {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        return self._post("editMessageReplyMarkup", payload).get("result")

    def dismiss_inline_safely(self, chat_id: int, message_id: int) -> bool:
        if not self.enabled: return True
        try:
            self.edit_message_reply_markup(chat_id, message_id, {"inline_keyboard": []}); return True
        except Exception:
            try:
                self.edit_message_reply_markup(chat_id, message_id, {"inline_keyboard": []}); return True
            except Exception:
                return False

    def startup_probe(self) -> Dict[str, Any]:
        res = {"env_valid": True, "getMe": False, "control_ping": False, "inline_sent": False, "inline_dismiss": False, "degraded": False}
        if not self.enabled:
            res["degraded"] = True; _write_startup(res)
            st = _read_state(); st["telegram_enabled_effective"] = False; _write_state(st)
            return res
        try:
            me = self.get_me(); res["getMe"] = bool(me and me.get("id") is not None)
            ctrl = int(self.routes.get("CONTROL") or self.routes.get("DEFAULT") or 0)
            if not ctrl: res["degraded"] = True
            else:
                m1 = self.send_text(ctrl, f"startup_ok {int(time.time())}"); res["control_ping"] = bool(m1 and m1.get("message_id"))
                m2 = self.send_inline_keyboard(ctrl, "probe", [[{"text":"ok","callback_data":"ok"}]]); res["inline_sent"] = bool(m2 and m2.get("message_id"))
                if res["inline_sent"]: res["inline_dismiss"] = self.dismiss_inline_safely(m2["chat"]["id"], m2["message_id"])
        except Exception:
            res["degraded"] = True
        st = _read_state(); st["telegram_enabled_effective"] = (self.enabled and not res["degraded"]); _write_state(st); _write_startup(res); return res

    def _mock_write(self, name: str, payload: dict) -> dict:
        import json, time
        p = self._mock_dir / f"{name}.json"
        data = {"ok": True, "result": payload, "ts": int(time.time())}
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def _get(self, method: str, params: dict | None = None) -> dict:
        if not self.enabled:
            return {}
        if self.mock:
            # synthetische Antwort für getMe
            if method == "getMe":
                return {"ok": True, "result": {"id": 123456, "is_bot": True, "username": "mock_bot"}}
            return {"ok": True, "result": {}}
        import requests
        url = f"{self.base}/{method}"
        r = requests.get(url, params=params or {}, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, method: str, data: dict) -> dict:
        if not self.enabled:
            return {}
        if self.mock:
            # synthetische Antworten in Dateien ablegen
            if method == "sendMessage":
                res = {"message_id": 1, "chat": {"id": data.get("chat_id")}, "text": data.get("text")}
                return self._mock_write("sendMessage", res)
            if method == "editMessageReplyMarkup":
                res = {"message_id": data.get("message_id"), "chat": {"id": data.get("chat_id")}, "reply_markup": data.get("reply_markup")}
                return self._mock_write("editMessageReplyMarkup", res)
            return self._mock_write(method, {"echo": data})
        import requests
        url = f"{self.base}/{method}"
        r = requests.post(url, json=data, timeout=self.timeout)
        r.raise_for_status()
        return r.json()


# --- Legacy-Kompatibilität: alte Funktionsnamen ---
def _routes_from_env():
    return {
        "CONTROL": os.getenv("TG_CHAT_CONTROL"),
        "LOGS": os.getenv("TG_CHAT_LOGS") or os.getenv("TG_CHAT_CONTROL"),
        "ORDERS": os.getenv("TG_CHAT_ORDERS") or os.getenv("TG_CHAT_CONTROL"),
        "ALERTS": os.getenv("TG_CHAT_ALERTS") or os.getenv("TG_CHAT_CONTROL"),
    }

def _send_text(channel_key: str, text: str):
    r = _routes_from_env()
    chat = r.get(channel_key) or r.get("CONTROL")
    try:
        tn = TelegramNotifier(
            token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            enabled=str(os.getenv("TELEGRAM_ENABLED", "0")) == "1",
            routes=r,
        )
        if chat:
            tn.send_text(int(chat), text)
    except Exception as e:
        print(f"[telegram_notifier] send {channel_key} failed: {e}")

# --- Legacy-kompatible Aliase mit echtem Routing ---
def to_control(text: str): _send_text("CONTROL", text)
def to_logs(text: str):    _send_text("LOGS",    text)
def to_orders(text: str):  _send_text("ORDERS",  text)
def to_alerts(text: str):  _send_text("ALERTS",  text)