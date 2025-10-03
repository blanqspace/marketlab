# modules/bot/ask_flow.py
from __future__ import annotations
import json
import os
import time
import threading
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


# ------------- small IO helpers (atomic writes) -------------
def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ----------------------- state & offset ----------------------
def _load_offset() -> int:
    try:
        return int(json.loads(OFFSET_FILE.read_text(encoding="utf-8")).get("offset", 0))
    except Exception:
        return 0


def _save_offset(ofs: int) -> None:
    _write_atomic(OFFSET_FILE, json.dumps({"offset": int(ofs)}))


def _save_state(d: Dict[str, Any]) -> None:
    _write_atomic(STATE_FILE, json.dumps(d, indent=2, ensure_ascii=False))


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------- UI construction ---------------------
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


# ------------------------- polling loop ---------------------
def _poll_loop(chat_id: int | str, message_id: int, exec_cfg: Dict[str, Any],
               window_sec: int, initial_offset: int) -> None:
    """Background poller. Stops on timeout or CANCEL_FILE."""
    try:
        LOCK_FILE.write_text("1", encoding="utf-8")
        placed = 0
        offset = initial_offset
        deadline = time.time() + max(10, int(window_sec))

        while time.time() < deadline:
            if CANCEL_FILE.exists():
                log.info("ASK-Flow: cancel signal received.")
                break

            upd = tg.get_updates(offset=offset, timeout=20, limit=20)
            if not upd or not upd.get("ok"):
                continue

            for item in upd.get("result", []):
                try:
                    offset = max(offset, int(item["update_id"]) + 1)
                except Exception:
                    continue

                cb = item.get("callback_query")
                if not cb:
                    continue

                data = cb.get("data", "") or ""
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
                            safe_dev=0.0,
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
                    # Wrapper hat kein show_alert-Flag
                    tg.answer_callback(cbid, f"Fehler: {e}")

            _save_offset(offset)

        # Buttons entfernen und Text aktualisieren
        try:
            tg.edit_message_reply_markup(chat_id, message_id, None)
        except Exception:
            pass
        try:
            tg.edit_message_text(chat_id, message_id, "Interaktion beendet.")
        except Exception:
            pass

        _save_state({"active": False, "placed": placed, "ended_at": time.time()})
    finally:
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except Exception:
            pass
        try:
            CANCEL_FILE.unlink(missing_ok=True)
        except Exception:
            pass


# --------------------------- API ----------------------------
def run_ask_flow(signals: List[Dict[str, Any]], exec_cfg: Dict[str, Any],
                 *, mode: str = "blocking", window_sec: int = 120) -> int:
    """
    mode: "blocking" | "async"
    return: placed count (blocking) or -1 (async started)
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
        channel="orders",
    )
    if not ok:
        log.error("Telegram send failed")
        return 0

    try:
        chat_id = res["chat"]["id"]
        message_id = int(res["message_id"])
    except Exception:
        log.error(f"Unerwartete Telegram-Antwort: {res}")
        return 0

    _save_state({"active": True, "chat_id": chat_id, "message_id": message_id, "placed": 0, "started_at": time.time()})

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
    try:
        return int(st.get("placed", 0))
    except Exception:
        return 0


def cancel_ask_flow() -> None:
    CANCEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    CANCEL_FILE.write_text("1", encoding="utf-8")


def ask_flow_status() -> Dict[str, Any]:
    st = _load_state()
    st["active"] = bool(LOCK_FILE.exists()) or bool(st.get("active"))
    return st
