# telegram/bot_control.py
from __future__ import annotations

import os, time, json, threading
import requests
from typing import Set

# ── Env ────────────────────────────────────────────────────────────────
TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
API   = f"https://api.telegram.org/bot{TOKEN}"
CHAT_CTRL = (os.getenv("TG_CHAT_CONTROL") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()

# Allowlist: TG_ALLOWLIST oder TG_ALLOW_USER_IDS oder TG_ADMIN
def _parse_ids(s: str | None) -> Set[int]:
    if not s: return set()
    out = set()
    for part in s.replace(",", " ").split():
        try: out.add(int(part))
        except: pass
    return out

ALLOWED: Set[int] = (
    _parse_ids(os.getenv("TG_ALLOWLIST")) or
    _parse_ids(os.getenv("TG_ALLOW_USER_IDS")) or
    _parse_ids(os.getenv("TG_ADMIN"))
)
if not ALLOWED and CHAT_CTRL.isdigit():
    ALLOWED = {int(CHAT_CTRL)}

def _ok_token() -> bool:
    try:
        r = requests.get(f"{API}/getMe", timeout=15)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False

def _send(chat_id: str | int, text: str):
    try:
        payload = {"chat_id": str(chat_id), "text": text, "disable_web_page_preview": True}
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
        return r.status_code == 200, (r.json() if r.content else {})
    except Exception as e:
        return False, {"error": str(e)}

def _is_allowed(uid: int) -> bool:
    return uid in ALLOWED if ALLOWED else True

# ── Steuer-Callbacks in dein Control-Center ────────────────────────────
from control.control_center import control

CMDS = {
    "/run_once":  "RUN_ONCE",
    "/loop_on":   "LOOP_ON",
    "/loop_off":  "LOOP_OFF",
    "/safe_on":   "SAFE_ON",
    "/safe_off":  "SAFE_OFF",
    "/status":    "STATUS",
}

def _handle_text(msg: dict):
    chat = msg.get("chat", {})
    uid  = int(str(chat.get("id", "0")).replace("-", "")) if chat.get("type")=="private" else int(str(msg.get("from", {}).get("id", "0")))
    txt  = (msg.get("text") or "").strip()
    if txt in CMDS:
        if not _is_allowed(uid):
            _send(CHAT_CTRL or uid, f"⛔ Nicht erlaubt: {uid}")
            return
        control.submit(CMDS[txt], src="telegram")
        _send(CHAT_CTRL or uid, f"✅ {txt} gesendet.")
    elif txt in ("/help", "/start"):
        _send(chat.get("id"), "Befehle: " + " ".join(CMDS.keys()))
    else:
        _send(chat.get("id"), "Unbekannt. /help")

def _poll_loop(stop_flag):
    if not _ok_token():
        _send(CHAT_CTRL or "", "⚠️ Telegram-Token ungültig (getMe fehlgeschlagen).")
        return
    offset = 0
    _send(CHAT_CTRL or "", "Bot-Control aktiv. Befehle: " + " ".join(CMDS.keys()))
    while not stop_flag.is_set():
        try:
            r = requests.post(f"{API}/getUpdates",
                              json={"timeout": 25, "limit": 20, "offset": offset, "allowed_updates": ["message"]},
                              timeout=(10, 30))
            if r.status_code != 200: time.sleep(2); continue
            body = r.json()
            for upd in body.get("result", []):
                offset = max(offset, int(upd["update_id"]) + 1)
                msg = upd.get("message")
                if not msg: continue
                if "text" in msg: _handle_text(msg)
        except Exception:
            time.sleep(2)

_STOP = threading.Event()
_THR  = None

def start():
    global _THR, _STOP
    if _THR and _THR.is_alive(): return
    _STOP = threading.Event()
    _THR = threading.Thread(target=_poll_loop, args=(_STOP,), name="tg-cmd-bot", daemon=True)
    _THR.start()

def stop():
    if _THR and _THR.is_alive():
        _STOP.set()
