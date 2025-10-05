# modules/bot/ask_flow.py
from __future__ import annotations
import json, time, threading
from pathlib import Path
from typing import Any, Dict, List

from shared.utils.logger import get_logger
import shared.system.telegram_notifier as tg
from modules.trade.ops import place_orders

log = get_logger("ask_flow")

OFFSET_FILE = Path("runtime/telegram_offset.json")
LOCK_FILE   = Path("runtime/telegram_poll.lock")
STATE_FILE  = Path("runtime/telegram_poll_state.json")
CANCEL_FILE = Path("runtime/telegram_poll.cancel")

def _load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0

def _save_offset(ofs: int) -> None:
    OFFSET_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OFFSET_FILE.with_suffix('.tmp')
    tmp.write_text(json.dumps({"offset": ofs}), encoding='utf-8')
    tmp.replace(OFFSET_FILE)

def _save_state(d: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")

def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _build_keyboard(signals: List[Dict[str, Any]], qty: float, order_type: str, tif: str) -> list[list[dict]]:
    rows: list[list[dict]] = []
    for s in signals:
        sig = s.get("signal")
        if not sig:
            continue
        act = (sig.get("action") or "").upper()
        if act not in ("BUY", "SELL"):
            continue
        sym = s["symbol"]
        rows.append([
            {"text": f"✅ {sym} {act} {qty}", "callback_data": f"order|{act}|{sym}|{qty}|{order_type}|{tif}"},
            {"text": f"🚫 {sym} Skip",        "callback_data": f"skip|{sym}"},
        ])
    if not rows:
        rows.append([{"text": "OK", "callback_data": "noop"}])
    return rows

# robustes Aufräumen der Inline-Buttons
def _rm_markup_with_retry(chat_id, message_id, text_done="Interaktion beendet.", retries=3) -> bool:
    for _ in range(max(1, retries)):
        try:
            tg.edit_message_reply_markup(chat_id, message_id, None)
            tg.edit_message_text(chat_id, message_id, text_done)
            return True
        except Exception as e:
            se = str(e).lower()
            if "400" in se and ("not modified" in se or "not found" in se):
                return True
            time.sleep(0.8)
    return False

def _poll_loop(chat_id: int | str, message_id: int, exec_cfg: Dict[str, Any],
               window_sec: int, initial_offset: int) -> None:
    """Hintergrund-Loop. Beendet bei Timeout oder CANCEL_FILE."""
    try:
        LOCK_FILE.write_text("1")
        placed = 0
        offset = initial_offset
        deadline = time.time() + max(10, window_sec)

        while time.time() < deadline:
            if CANCEL_FILE.exists():
                log.info("ASK-Flow: cancel signal received.")
                break

            upd = tg.get_updates(offset=offset, timeout=20, limit=20)
            if not upd or not upd.get("ok"):
                continue

            for item in upd.get("result", []):
                offset = max(offset, int(item["update_id"]) + 1)
                cb = item.get("callback_query")
                if not cb:
                    continue
                data = cb.get("data", "")
                cbid = cb.get("id")

                try:
                    if data.startswith("order|"):
                        _, side, sym, q, ot, tf = data.split("|", 5)
                        place_orders(
                            [sym],
                            asset=exec_cfg.get("asset", "stock"),
                            side=side,
                            order_type=ot,
                            qty=float(q),
                            lmt=None,
                            stp=None,
                            tif=tf,
                            safe_dev=float(exec_cfg.get("safe_dev", 0.0) or 0.0),
                            dry_run=False,
                            cancel_after=None,
                        )
                        placed += 1
                        tg.answer_callback(cbid, f"{sym} {side} ausgeführt")
                    elif data.startswith("skip|"):
                        _, sym = data.split("|", 1)
                        tg.answer_callback(cbid, f"{sym} übersprungen")
                    else:
                        tg.answer_callback(cbid, "OK")
                except Exception as e:
                    # show_alert=True wird in notifier.answer_callback unterstützt
                    tg.answer_callback(cbid, f"Fehler: {e}")

            _save_offset(offset)

        # Buttons entfernen + Status
        cleaned = _rm_markup_with_retry(chat_id, message_id)
        _save_state({"active": False, "placed": placed, "ended_at": time.time(),
                     "chat_id": chat_id, "message_id": message_id, "cleaned": bool(cleaned)})
    finally:
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            CANCEL_FILE.unlink(missing_ok=True)
        except Exception:
            pass

def run_ask_flow(signals: List[Dict[str, Any]], exec_cfg: Dict[str, Any],
                 *, mode: str = "blocking", window_sec: int = 120) -> int:
    """
    mode: "blocking" | "async"
    Rückgabe: bei blocking = placed, bei async = -1 (läuft im Hintergrund)
    """
    if LOCK_FILE.exists():
        log.warning("ASK-Flow: bereits aktiv. Überspringe Start.")
        return -1 if mode == "async" else 0

    qty = float(exec_cfg.get("qty", 1))
    tif = exec_cfg.get("tif", "DAY")
    order_type = (exec_cfg.get("order_type", "MKT") or "MKT").upper()

    ok, res = tg.send_inline_keyboard(
        "Bestätige Orders:",
        _build_keyboard(signals, qty, order_type, tif),
        channel="orders"
    )
    if not ok:
        log.error("Telegram send failed")
        return 0

    chat_id = res["chat"]["id"]
    message_id = res["message_id"]
    _save_state({
        "active": True,
        "chat_id": chat_id,
        "message_id": message_id,
        "placed": 0,
        "started_at": time.time(),
        "window_sec": int(window_sec),
    })

    if mode == "async":
        t = threading.Thread(
            target=_poll_loop,
            args=(chat_id, message_id, exec_cfg, window_sec, _load_offset()),
            daemon=True,
        )
        t.start()
        return -1

    _poll_loop(chat_id, message_id, exec_cfg, window_sec, _load_offset())
    st = _load_state()
    return int(st.get("placed", 0))

def cancel_ask_flow() -> None:
    CANCEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CANCEL_FILE.write_text("1")
    st = _load_state()
    try:
        if st.get("chat_id") and st.get("message_id"):
            _rm_markup_with_retry(st["chat_id"], st["message_id"], "Abgebrochen.")
    except Exception:
        pass

def ask_flow_status() -> Dict[str, Any]:
    st = _load_state()
    st["active"] = bool(LOCK_FILE.exists()) or bool(st.get("active"))
    return st
