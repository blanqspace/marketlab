# telegram/bot_inline.py
from __future__ import annotations
import os, time, json, threading, requests, sys
from pathlib import Path
from typing import Dict, Any, Optional

# Projekt-Root für Imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from shared.core.config_loader import load_env
load_env()

from control.control_center import control  # gleiche Instanz im selben Prozess

API = "https://api.telegram.org"
RUNTIME = Path("runtime")
OFFSET_FILE = RUNTIME / "tg_inline_offset.json"

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_CONTROL = os.getenv("TG_CHAT_CONTROL", "").strip()
ALLOW = {s.strip() for s in os.getenv("TG_ALLOWLIST", "").split(",") if s.strip()}

_running = False
_thread: Optional[threading.Thread] = None

def _load_offset() -> int:
    try: return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0))
    except Exception: return 0

def _save_offset(ofs: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    OFFSET_FILE.write_text(json.dumps({"offset": ofs}), encoding="utf-8")

def _send(chat_id: str, text: str, kb: dict | None = None) -> None:
    if not TOKEN: return
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if kb is not None:
        payload["reply_markup"] = kb
    try:
        requests.post(f"{API}/bot{TOKEN}/sendMessage", json=payload, timeout=(10,10))
    except Exception:
        pass

def _edit(chat_id: str, message_id: int, text: str, kb: dict | None = None) -> None:
    if not TOKEN: return
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "disable_web_page_preview": True}
    if kb is not None:
        payload["reply_markup"] = kb
    try:
        requests.post(f"{API}/bot{TOKEN}/editMessageText", json=payload, timeout=(10,10))
    except Exception:
        pass

def _get_updates(offset: int | None, timeout: int = 30) -> Dict[str, Any]:
    if not TOKEN: return {"ok": False}
    params = {"timeout": timeout, "limit": 20}
    if offset is not None: params["offset"] = offset
    r = requests.get(f"{API}/bot{TOKEN}/getUpdates", params=params, timeout=(10, timeout+5))
    try: return r.json()
    except Exception: return {"ok": False}

def _answer_cb(cb_id: str, text: str = "") -> None:
    if not TOKEN: return
    try:
        requests.post(f"{API}/bot{TOKEN}/answerCallbackQuery",
                      json={"callback_query_id": cb_id, "text": text}, timeout=(10,10))
    except Exception:
        pass

def _auth_ok(obj: Dict[str, Any]) -> bool:
    # erlaube nur Steuer-Chat + Allowlist-User
    if "message" in obj:
        chat = str(obj["message"].get("chat", {}).get("id", ""))
        user = str(obj["message"].get("from", {}).get("id", ""))
    else:
        cq = obj.get("callback_query", {})
        chat = str(cq.get("message", {}).get("chat", {}).get("id", ""))
        user = str(cq.get("from", {}).get("id", ""))
    if CHAT_CONTROL and chat != CHAT_CONTROL: return False
    if ALLOW and user not in ALLOW: return False
    return True

def _main_menu_kb() -> dict:
    return {
        "inline_keyboard": [
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
        ]
    }

def _handle_cmd(cmd: str) -> str:
    control.submit(cmd, src="telegram")  # gleiche Queue/Instanz
    return f"{cmd} gesendet."

def _handle_update(it: Dict[str, Any]) -> None:
    if not _auth_ok(it):
        return
    if "message" in it:
        msg = it["message"]; chat = str(msg["chat"]["id"])
        text = (msg.get("text") or "").strip().lower()
        if text in ("/start", "/menu"):
            _send(chat, "marketlab • Steuerung", _main_menu_kb()); return
        # Fallback: immer das Menü zeigen
        _send(chat, "Menü:", _main_menu_kb()); return

    cq = it.get("callback_query")
    if not cq: return
    cbid = cq.get("id"); m = cq.get("message", {}); chat = str(m.get("chat", {}).get("id", "")); mid = m.get("message_id")
    data = cq.get("data", "")
    parts = data.split("|")
    if len(parts) >= 3 and parts[0] == "v1" and parts[1] == "cmd":
        cmd = parts[2].upper()
        _answer_cb(cbid, f"{cmd}")
        note = _handle_cmd(cmd)
        try:
            _edit(chat, mid, f"{note}", _main_menu_kb())
        except Exception:
            pass
        return

def _loop():
    offset = _load_offset()
    # Initiales Menü (optional)
    if CHAT_CONTROL:
        _send(CHAT_CONTROL, "marketlab • Steuerbot aktiv.\nTippe /menu", None)
    while _running:
        try:
            up = _get_updates(offset, timeout=30)
        except Exception:
            time.sleep(2); continue
        if not up or not up.get("ok"): continue
        for it in up.get("result", []):
            offset = max(offset, it["update_id"] + 1)
            try:
                _handle_update(it)
            except Exception:
                pass
        _save_offset(offset)

def start_inline_bot():
    global _running, _thread
    if not TOKEN or not CHAT_CONTROL:
        print("Telegram-Bot nicht konfiguriert (.env: TELEGRAM_BOT_TOKEN, TG_CHAT_CONTROL).")
        return
    if _running: return
    _running = True
    _thread = threading.Thread(target=_loop, daemon=True, name="tg-inline")
    _thread.start()
    print("Telegram Inline-Bot gestartet.")

def stop_inline_bot():
    global _running
    _running = False
    print("Telegram Inline-Bot gestoppt.")

