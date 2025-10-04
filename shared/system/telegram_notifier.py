from __future__ import annotations
import os, time, json, requests
from pathlib import Path
from typing import Dict, Any, Optional, Iterable

from shared.core.config_loader import load_env, get_env_var
from shared.utils.logger import get_logger

# ─────────────────── Setup ───────────────────
try:
    from shared.core.config_loader import load_env
    load_env()
except Exception:
    pass

log = get_logger("telegram_notifier")

TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", required=False)
CHAT_CTRL   = os.getenv("TG_CHAT_CONTROL", "").strip()
CHAT_LOGS   = os.getenv("TG_CHAT_LOGS", "").strip()
CHAT_ORDERS = os.getenv("TG_CHAT_ORDERS", "").strip()
CHAT_ALERTS = os.getenv("TG_CHAT_ALERTS", "").strip()

API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else None
DEFAULT_TIMEOUT = (10, 30)  # (connect, read)

# ───────────── Mock-Schalter ─────────────
MOCK = os.getenv("TELEGRAM_MOCK", "0") == "1"
MOCK_DIR = Path("runtime/telegram_mock")
if MOCK:
    MOCK_DIR.mkdir(parents=True, exist_ok=True)

# ───────────────── Helpers ─────────────────
def _enabled() -> bool:
    if MOCK:
        return True
    if not TOKEN or not API:
        log.warning("Telegram: TOKEN fehlt.")
        return False
    return True

def _chat_control() -> str|int:
    return os.getenv("TG_CHAT_CONTROL") or os.getenv("TELEGRAM_CHAT_ID")

def _chat_for_channel(channel: str|None) -> str:
    ch = (channel or "control").lower()
    if ch == "orders":  return CHAT_ORDERS or _chat_control()
    if ch == "logs":    return CHAT_LOGS   or _chat_control()
    if ch == "alerts":  return CHAT_ALERTS or _chat_control()
    return CHAT_CTRL or _chat_control()

# ───────────────── HTTP Core ─────────────────
def _post(method: str, payload: Dict[str, Any], retries: int = 2, delay: float = 1.0) -> bool:
    if not _enabled():
        return False

    if MOCK:
        fn = MOCK_DIR / f"{int(time.time())}_{method}.jsonl"
        fn.write_text(json.dumps({"method": method, "payload": payload}, ensure_ascii=False) + "\n", encoding="utf-8")
        return True

    url = f"{API}/{method}"
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
            if r.status_code == 200 and (r.json().get("ok", True)):
                log.info("Telegram: Nachricht gesendet.")
                return True
            log.error(f"Telegram: Status {r.status_code} → {r.text}")
        except Exception as e:
            log.warning(f"Telegram: Sendefehler (Try {attempt+1}): {e}")
        if attempt < retries:
            time.sleep(delay)
    return False

def _send_text(chat_id: str, text: str, parse_mode: Optional[str] = None,
               reply_markup: Optional[Dict[str, Any]] = None) -> bool:
    if not chat_id:
        log.debug("Telegram: chat_id leer → skip.")
        return False

    if MOCK:
        body = {
            "method": "sendMessage",
            "result": {"chat": {"id": chat_id}, "text": text, "reply_markup": reply_markup}
        }
        (MOCK_DIR / f"{int(time.time())}_sendMessage.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode: payload["parse_mode"] = parse_mode
    if reply_markup: payload["reply_markup"] = reply_markup
    return _post("sendMessage", payload)

def _edit_text(chat_id: str, message_id: int, text: str,
               parse_mode: Optional[str] = None,
               reply_markup: Optional[Dict[str, Any]] = None) -> bool:
    if MOCK:
        body = {
            "method": "editMessageText",
            "result": {"chat": {"id": chat_id}, "message_id": message_id, "text": text, "reply_markup": reply_markup}
        }
        (MOCK_DIR / f"{int(time.time())}_editMessageText.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True

    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    if parse_mode: payload["parse_mode"] = parse_mode
    if reply_markup: payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload)

# ─────────────── Channel-Router ───────────────
def to_control(text: str, parse_mode: Optional[str] = None) -> bool:
    print(f"[CTRL] {text}")
    return _send_text(_chat_for_channel("control"), f"{text}", parse_mode=parse_mode)

def to_logs(text: str, parse_mode: Optional[str] = None) -> bool:
    print(f"[LOG]  {text}")
    return _send_text(_chat_for_channel("logs"), f"{text}", parse_mode=parse_mode)

def to_orders(text: str, parse_mode: Optional[str] = None) -> bool:
    print(f"[ORD]  {text}")
    return _send_text(_chat_for_channel("orders"), f"{text}", parse_mode=parse_mode)

def to_alerts(text: str, parse_mode: Optional[str] = None) -> bool:
    try:
        import sys
        print(f"[ALR]  {text}", file=sys.stderr)
    except Exception:
        pass
    return _send_text(_chat_for_channel("alerts"), f"{text}", parse_mode=parse_mode)

# ───────────── Inline-Keyboard Helpers ─────────────
def kb_inline(rows: Iterable[Iterable[Dict[str, str]]]) -> Dict[str, Any]:
    return {"inline_keyboard": [list(row) for row in rows]}

def send_inline_keyboard(text: str, keyboard: list[list[dict]], *, channel: str = "control"):
    if not _enabled():
        return (False, {})

    if MOCK:
        chat_id = _chat_for_channel(channel)
        body = {"ok": True, "result": {"chat": {"id": chat_id}, "message_id": 9999,
                "text": text, "reply_markup": {"inline_keyboard": keyboard}}}
        (MOCK_DIR / f"{int(time.time())}_sendInlineKeyboard.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return (True, {"chat": {"id": chat_id}, "message_id": 9999})

    chat_id = _chat_for_channel(channel)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": keyboard},
        "disable_web_page_preview": True
    }
    r = requests.post(f"{API}/sendMessage", json=payload, timeout=DEFAULT_TIMEOUT)
    ok = r.status_code == 200
    try:
        body = r.json() if r.content else {}
    except Exception:
        body = {}
    if ok and body.get("ok"):
        res = body.get("result", {})
        return (True, {"chat": {"id": res.get("chat", {}).get("id", chat_id)},
                       "message_id": res.get("message_id")})
    log.error(f"Telegram send_inline_keyboard: {r.status_code} -> {r.text}")
    return (False, body)

def answer_callback(callback_query_id: str, text: str = "") -> bool:
    if MOCK:
        (MOCK_DIR / f"{int(time.time())}_answerCallback.json").write_text(
            json.dumps({"ok": True, "id": callback_query_id, "text": text}, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        return True
    return _post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

def edit_message_text(chat_id: str|int, message_id: int, text: str,
                      parse_mode: Optional[str] = None) -> bool:
    return _edit_text(str(chat_id), int(message_id), text, parse_mode=parse_mode)

def edit_message_reply_markup(chat_id: str|int, message_id: int,
                              reply_markup: Optional[Dict[str, Any]]) -> bool:
    if MOCK:
        body = {"ok": True, "chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        (MOCK_DIR / f"{int(time.time())}_editReplyMarkup.json").write_text(
            json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return True
    payload = {"chat_id": str(chat_id), "message_id": int(message_id),
               "reply_markup": reply_markup or {"inline_keyboard": []}}
    return _post("editMessageReplyMarkup", payload)

def get_updates(offset: int = 0, timeout: int = 20, limit: int = 20) -> Dict[str, Any]:
    if not _enabled():
        return {"ok": False, "result": []}

    if MOCK:
        p = MOCK_DIR / "updates.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {"ok": True, "result": []}
        return {"ok": True, "result": []}

    payload = {"offset": offset, "timeout": timeout, "limit": limit, "allowed_updates": ["callback_query"]}
    url = f"{API}/getUpdates"
    try:
        r = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        log.error(f"Telegram getUpdates: {r.status_code} -> {r.text}")
    except Exception as e:
        log.warning(f"Telegram getUpdates Fehler: {e}")
    return {"ok": False, "result": []}

# ───────────── Legacy-Kompatibilität ─────────────
def send_alert(message: str, level: str = "info") -> bool:
    lvl = (level or "info").lower()
    if lvl == "control":
        return to_control(f"ℹ️ INFO:\n{message}")
    if lvl == "orders":
        return to_orders(f"ℹ️ INFO:\n{message}")
    if lvl in ("warning", "warn"):
        return to_alerts(f"⚠️ WARNUNG:\n{message}")
    if lvl in ("alert", "error", "critical"):
        return to_alerts(f"❌ ALERT:\n{message}")
    return to_logs(f"ℹ️ INFO:\n{message}")

# ───────────── Mini Self-Test ─────────────
def _selftest() -> None:
    print("MOCK :", MOCK)
    print("TOKEN:", bool(TOKEN))
    print("CTRL :", CHAT_CTRL)
    print("LOGS :", CHAT_LOGS)
    print("ORDERS:", CHAT_ORDERS)
    print("ALERTS:", CHAT_ALERTS)
    if MOCK:
        to_control("Mock: CONTROL")
        to_logs("Mock: LOGS")
        to_orders("Mock: ORDERS")
        to_alerts("Mock: ALERTS")
        send_inline_keyboard("Mock Keyboard", [[{"text": "OK", "callback_data": "noop"}]], channel="orders")
        return
    if not _enabled(): 
        return
    send_inline_keyboard("Bot online • /menu", [[{"text": "Run once", "callback_data": "v1|cmd|RUN_ONCE"}]], channel="control")
    to_logs("Test LOG")
    to_orders("Test ORDERS")
    to_alerts("Test ALERT")
    to_control("Test CONTROL")
