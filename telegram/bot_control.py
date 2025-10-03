# telegram/bot_control.py
from __future__ import annotations
import os, time, json, requests, sys
from pathlib import Path
from typing import Dict, Any, Tuple

# Projektroot für Imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from shared.core.config_loader import load_env
load_env()

from control.control_center import control  # nutzt deine Queue

API = "https://api.telegram.org"

def env(name: str, default: str = "") -> str:
    v = os.getenv(name, default)
    return v.strip() if isinstance(v, str) else default

TOKEN = env("TELEGRAM_BOT_TOKEN")
CHAT_CONTROL = env("TG_CHAT_CONTROL")
ALLOW = {s.strip() for s in env("TG_ALLOWLIST", "").split(",") if s.strip()}

if not TOKEN or not CHAT_CONTROL:
    print("❌ TELEGRAM_BOT_TOKEN oder TG_CHAT_CONTROL fehlt (.env).")
    sys.exit(1)

def tg_get_updates(offset: int | None, timeout: int = 30) -> Dict[str, Any]:
    params = {"timeout": timeout, "limit": 20}
    if offset is not None: params["offset"] = offset
    r = requests.get(f"{API}/bot{TOKEN}/getUpdates", params=params, timeout=(10, timeout+5))
    return r.json()

def tg_send(chat_id: str, text: str) -> None:
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        requests.post(f"{API}/bot{TOKEN}/sendMessage", json=payload, timeout=(10,10))
    except Exception:
        pass

def auth_ok(msg: Dict[str, Any]) -> bool:
    # Nur vom konfigurierten Steuer-Chat und erlaubten Usern
    chat = str(msg.get("chat", {}).get("id", ""))
    user = str(msg.get("from", {}).get("id", ""))
    if chat != CHAT_CONTROL: return False
    if ALLOW and user not in ALLOW: return False
    return True

def parse_cmd(text: str) -> Tuple[str, Dict[str, Any]]:
    t = (text or "").strip()
    if not t.startswith("/"): return "", {}
    parts = t.split()
    cmd = parts[0].lower()
    args: Dict[str, Any] = {}
    if cmd in ("/run_once", "/status", "/loop_on", "/loop_off", "/safe_on", "/safe_off"):
        return cmd, args
    # einfache Orderkommandos: /buy AAPL 5  → PLACE-Event über Control center (optional)
    if cmd in ("/buy", "/sell") and len(parts) >= 3:
        sym = parts[1].upper()
        qty = float(parts[2])
        side = "BUY" if cmd == "/buy" else "SELL"
        return "/place", {"side": side, "sym": sym, "qty": qty}
    return "", {}

def dispatch(cmd: str, args: Dict[str, Any]) -> str:
    # Map Telegram → Control-Center Events
    if cmd == "/run_once":
        control.submit("RUN_ONCE", src="telegram")
        return "RUN_ONCE gesendet."
    if cmd == "/loop_on":
        control.submit("LOOP_ON", src="telegram")
        return "LOOP_ON gesendet."
    if cmd == "/loop_off":
        control.submit("LOOP_OFF", src="telegram")
        return "LOOP_OFF gesendet."
    if cmd == "/status":
        control.submit("STATUS", src="telegram")
        return "STATUS angefordert."
    if cmd == "/safe_on":
        control.submit("SAFE_ON", src="telegram")
        return "SAFE_ON gesetzt."
    if cmd == "/safe_off":
        control.submit("SAFE_OFF", src="telegram")
        return "SAFE_OFF gesetzt."
    if cmd == "/place":
        # optionales einfaches Place-Demo-Event
        control.submit("PLACE", {"sym": args["sym"], "qty": args["qty"], "side": args["side"]}, src="telegram")
        return f"PLACE {args['side']} {args['sym']} x {args['qty']} gesendet."
    return "Unbekanntes Kommando."

def main():
    tg_send(CHAT_CONTROL, "🤖 robust_lab: Steuerbot online. Befehle: /run_once /loop_on /loop_off /status /safe_on /safe_off [/buy SYM QTY | /sell SYM QTY]")
    offset = None
    while True:
        try:
            up = tg_get_updates(offset, timeout=30)
        except Exception:
            time.sleep(2); continue
        if not up or not up.get("ok"):
            continue
        for it in up.get("result", []):
            offset = max(offset or 0, it["update_id"] + 1)
            msg = it.get("message") or {}
            if not msg:  # ignoriert CallbackQuery in dieser Minimalversion
                continue
            if not auth_ok(msg):
                continue
            text = msg.get("text", "")
            cmd, args = parse_cmd(text)
            if not cmd:
                tg_send(CHAT_CONTROL, "Unbekannt. Nutze: /run_once /loop_on /loop_off /status /safe_on /safe_off [/buy SYM QTY | /sell SYM QTY]")
                continue
            resp = dispatch(cmd, args)
            tg_send(CHAT_CONTROL, f"OK: {resp}")
        # kleiner Herzschlag in Chat optional: auslassen für Ruhe

if __name__ == "__main__":
    main()
