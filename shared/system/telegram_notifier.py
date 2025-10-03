from __future__ import annotations
import os, time, json, requests
from typing import Dict, Any, Iterable, Optional
from shared.core.config_loader import load_env, get_env_var
from shared.utils.logger import get_logger

# ─────────────────── Setup ───────────────────
load_env()
log = get_logger("telegram_notifier")

TOKEN = get_env_var("TELEGRAM_BOT_TOKEN", required=False)
CHAT_CTRL   = os.getenv("TG_CHAT_CONTROL", "").strip()
CHAT_LOGS   = os.getenv("TG_CHAT_LOGS", "").strip()
CHAT_ORDERS = os.getenv("TG_CHAT_ORDERS", "").strip()
CHAT_ALERTS = os.getenv("TG_CHAT_ALERTS", "").strip()

API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else None
DEFAULT_TIMEOUT = (10, 10)  # connect, read

def _enabled() -> bool:
    if not TOKEN or not API:
        log.warning("Telegram: TOKEN fehlt.")
        return False
    return True
# --- Public wrappers for ask_flow ---
def edit_message_text(chat_id: str|int, message_id: int, text: str,
                      parse_mode: Optional[str] = None) -> bool:
    return _edit_text(str(chat_id), int(message_id), text, parse_mode=parse_mode)

def edit_message_reply_markup(chat_id: str|int, message_id: int,
                              reply_markup: Optional[Dict[str, Any]]) -> bool:
    payload = {
        "chat_id": str(chat_id),
        "message_id": int(message_id),
        "reply_markup": reply_markup or {"inline_keyboard": []},
    }
    return _post("editMessageReplyMarkup", payload)

def get_updates(offset: int = 0, timeout: int = 20, limit: int = 20) -> Dict[str, Any]:
    if not _enabled():
        return {"ok": False, "result": []}
    payload = {
        "offset": offset,
        "timeout": timeout,
        "limit": limit,
        "allowed_updates": ["callback_query"],
    }
    url = f"{API}/getUpdates"
    try:
        r = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
        if r.status_code == 200:
            return r.json()
        log.error(f"Telegram getUpdates: {r.status_code} -> {r.text}")
    except Exception as e:
        log.warning(f"Telegram getUpdates Fehler: {e}")
    return {"ok": False, "result": []}

def _chat_for_channel(channel: str|None) -> str:
    ch = (channel or "control").lower()
    if ch == "orders":
        return CHAT_ORDERS or _chat_control()
    if ch == "logs":
        return CHAT_LOGS or _chat_control()
    if ch == "alerts":
        return CHAT_ALERTS or _chat_control()
    return CHAT_CTRL or _chat_control()

def send_inline_keyboard(text: str, keyboard: list[list[dict]], *, channel: str = "control"):
    if not _enabled():
        return (False, {})
    chat_id = _chat_for_channel(channel)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "reply_markup": {"inline_keyboard": keyboard},
        "disable_web_page_preview": True,
    }
    r = requests.post(f"{API}/sendMessage", json=payload, timeout=DEFAULT_TIMEOUT)
    ok = r.status_code == 200
    try:
        body = r.json() if r.content else {}
    except Exception:
        body = {}
    if ok and body.get("ok"):
        res = body.get("result", {})
        return (True, {
            "chat": {"id": res.get("chat", {}).get("id", chat_id)},
            "message_id": res.get("message_id"),
        })
    log.error(f"Telegram send_inline_keyboard: {r.status_code} -> {r.text}")
    return (False, body)

# ───────────────── HTTP Core ─────────────────
def _post(method: str, payload: Dict[str, Any], retries: int = 2, delay: float = 1.0) -> bool:
    if not _enabled():
        return False
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
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if parse_mode: payload["parse_mode"] = parse_mode
    if reply_markup: payload["reply_markup"] = reply_markup
    ok = _post("sendMessage", payload)
    return ok

def _edit_text(chat_id: str, message_id: int, text: str,
               parse_mode: Optional[str] = None,
               reply_markup: Optional[Dict[str, Any]] = None) -> bool:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    if parse_mode: payload["parse_mode"] = parse_mode
    if reply_markup: payload["reply_markup"] = reply_markup
    return _post("editMessageText", payload)

def answer_callback(callback_query_id: str, text: str = "") -> bool:
    return _post("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text})

# ─────────────── Channel-Router ───────────────
def to_control(text: str, parse_mode: Optional[str] = None) -> bool:
    print(f"[CTRL] {text}")
    return _send_text(CHAT_CTRL, f"{text}", parse_mode=parse_mode)

def to_logs(text: str, parse_mode: Optional[str] = None) -> bool:
    print(f"[LOG]  {text}")
    return _send_text(CHAT_LOGS, f"{text}", parse_mode=parse_mode)

def to_orders(text: str, parse_mode: Optional[str] = None) -> bool:
    print(f"[ORD]  {text}")
    return _send_text(CHAT_ORDERS, f"{text}", parse_mode=parse_mode)

def to_alerts(text: str, parse_mode: Optional[str] = None) -> bool:
    # auch auf STDERR spiegeln
    try:
        import sys
        print(f"[ALR]  {text}", file=sys.stderr)
    except Exception:
        pass
    return _send_text(CHAT_ALERTS, f"{text}", parse_mode=parse_mode)

# ───────────── Inline-Keyboard Helpers ─────────────
def kb_inline(rows: Iterable[Iterable[Dict[str, str]]]) -> Dict[str, Any]:
    """rows = [[{"text":"Run","callback_data":"v1|cmd|RUN_ONCE"}, ...], ...]"""
    return {"inline_keyboard": [list(row) for row in rows]}

def send_menu_control(title: str = "robust_lab • Steuerung") -> bool:
    kb = kb_inline([
        [
            {"text": "▶️ Run once", "callback_data": "v1|cmd|RUN_ONCE"},
            {"text": "🔁 Loop ON",  "callback_data": "v1|cmd|LOOP_ON"},
            {"text": "⏹ Loop OFF",  "callback_data": "v1|cmd|LOOP_OFF"},
        ],
        [
            {"text": "🛡 SAFE ON",  "callback_data": "v1|cmd|SAFE_ON"},
            {"text": "🟢 SAFE OFF", "callback_data": "v1|cmd|SAFE_OFF"},
            {"text": "ℹ️ Status",   "callback_data": "v1|cmd|STATUS"},
        ],
    ])
    return _send_text(CHAT_CTRL, title, reply_markup=kb)

def send_order_decision(sym: str, action: str, qty: float, tif: str = "DAY",
                        extra: str = "") -> bool:
    text = f"Order-Vorschlag: {sym} {action} {qty} TIF={tif}\n{extra}".strip()
    kb = kb_inline([
        [
            {"text": "✅ Ausführen", "callback_data": f"v1|ord|CONFIRM|{sym}|{action}|{qty}|{tif}"},
            {"text": "❌ Abbrechen", "callback_data": f"v1|ord|CANCEL|{sym}|{action}|{qty}|{tif}"},
        ]
    ])
    return _send_text(CHAT_CTRL, text, reply_markup=kb)

# ───────────── Legacy-Kompatibilität ─────────────
def send_alert(message: str, level: str = "info") -> bool:
    """
    Kompatibler Wrapper.
    Routing:
      - 'control' → CONTROL
      - 'orders'  → ORDERS
      - 'info'    → LOGS
      - 'warning'/'alert' → ALERTS
    """
    lvl = (level or "info").lower()
    if lvl == "control":
        return to_control(f"ℹ️ INFO:\n{message}")
    if lvl == "orders":
        return to_orders(f"ℹ️ INFO:\n{message}")
    if lvl in ("warning", "warn"):
        return to_alerts(f"⚠️ WARNUNG:\n{message}")
    if lvl in ("alert", "error", "critical"):
        return to_alerts(f"❌ ALERT:\n{message}")
    # default info → logs
    return to_logs(f"ℹ️ INFO:\n{message}")

# ───────────── Mini Self-Test ─────────────
def _selftest() -> None:
    ok = _enabled()
    print("TOKEN:", bool(TOKEN))
    print("CTRL :", CHAT_CTRL)
    print("LOGS :", CHAT_LOGS)
    print("ORDERS:", CHAT_ORDERS)
    print("ALERTS:", CHAT_ALERTS)
    if not ok: return
    send_menu_control("Bot online • /menu")
    to_logs("Test LOG")
    to_orders("Test ORDERS")
    to_alerts("Test ALERT")
    to_control("Test CONTROL")

def _chat_control() -> str|int:
    import os
    return os.getenv("TG_CHAT_CONTROL") or os.getenv("TELEGRAM_CHAT_ID")

if __name__ == "__main__":
    _selftest()
