import os, time, json, urllib.request
from src.marketlab.services.telegram_service import telegram_service
from src.marketlab.orders.store import set_state

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
URL = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
OFFSET = None

def get_updates():
    global OFFSET
    params = {"timeout": 20}
    if OFFSET is not None:
        params["offset"] = OFFSET
    req = urllib.request.Request(
        URL,
        data=json.dumps(params).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data.get("result", [])

while True:
    try:
        for upd in get_updates():
            OFFSET = upd["update_id"] + 1
            cb = upd.get("callback_query")
            if not cb: 
                continue
            data = cb.get("data")
            if not data:
                continue
            telegram_service.handle_callback(data)
            if data.startswith("ORD:CONFIRM:"):
                oid = data.split(":")[2]; set_state(oid, "CONFIRMED")
            elif data.startswith("ORD:REJECT:"):
                oid = data.split(":")[2]; set_state(oid, "REJECTED")
        time.sleep(1)
    except Exception:
        time.sleep(2)

