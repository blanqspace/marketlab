import os, time, json, urllib.request
from src.marketlab.services.telegram_service import telegram_service
from src.marketlab.services.telegram_usecases import build_main_menu, handle_callback
from src.marketlab.ipc import bus

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = os.environ.get("TG_CHAT_CONTROL")
URL_BASE = f"https://api.telegram.org/bot{TOKEN}"
URL_UPD = f"{URL_BASE}/getUpdates"
URL_SEND = f"{URL_BASE}/sendMessage"
URL_ANS = f"{URL_BASE}/answerCallbackQuery"
OFFSET = None

def get_updates():
    global OFFSET
    params = {"timeout": 20}
    if OFFSET is not None: params["offset"] = OFFSET
    req = urllib.request.Request(URL_UPD, data=json.dumps(params).encode("utf-8"),
                                 headers={"Content-Type":"application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("result", [])


def send_message(text: str, reply_markup: dict | None = None):
    if not CHAT:
        return
    payload = {"chat_id": int(CHAT), "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    req = urllib.request.Request(
        URL_SEND, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"
    )
    urllib.request.urlopen(req, timeout=10).read()


def answer_callback(cb_id: str, text: str):
    req = urllib.request.Request(
        URL_ANS,
        data=json.dumps({"callback_query_id": cb_id, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    urllib.request.urlopen(req, timeout=10).read()

if TOKEN and CHAT:
    try:
        send_message("MarketLab Control", reply_markup=build_main_menu())
    except Exception:
        pass

while True:
    try:
        for upd in get_updates():
            OFFSET = upd["update_id"] + 1
            # Callback buttons
            cb = upd.get("callback_query")
            if cb:
                data_raw = cb.get("data")
                if not data_raw:
                    continue
                # Try JSON format first
                parsed = None
                try:
                    parsed = json.loads(data_raw)
                except Exception:
                    # Legacy: ORD:CONFIRM:<ID> / ORD:REJECT:<ID>
                    if data_raw.startswith("ORD:CONFIRM:"):
                        oid = data_raw.split(":")[2]
                        parsed = {"action": "confirm", "id": oid}
                    elif data_raw.startswith("ORD:REJECT:"):
                        oid = data_raw.split(":")[2]
                        parsed = {"action": "reject", "id": oid}
                if not parsed:
                    continue
                try:
                    handle_callback(parsed)
                    answer_callback(cb.get("id"), f"OK: {parsed.get('action')}")
                    # update dynamic menu after each action
                    try:
                        send_message("MarketLab Control", reply_markup=build_main_menu())
                    except Exception:
                        pass
                except Exception as e:
                    answer_callback(cb.get("id"), f"Fehler: {e}")
                    # If missing id for confirm/reject, prompt user
                    try:
                        if str(e).startswith("Bitte ID"):
                            send_message("Bitte ID angeben: /confirm <ID> oder /reject <ID>")
                    except Exception:
                        pass
                continue

            # Text commands (e.g., /confirm <ID>)
            msg = upd.get("message")
            if msg and isinstance(msg.get("text"), str):
                txt = msg["text"].strip()
                if txt.startswith("/confirm "):
                    oid = txt.split(maxsplit=1)[1].strip()
                    if oid:
                        bus.enqueue("orders.confirm", {"id": oid}, source="telegram")
                        send_message(f"OK: confirm {oid}")
                        try:
                            send_message("MarketLab Control", reply_markup=build_main_menu())
                        except Exception:
                            pass
                    else:
                        send_message("Bitte ID angeben: /confirm <ID>")
        time.sleep(1)
    except Exception:
        time.sleep(2)
