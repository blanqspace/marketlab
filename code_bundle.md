# 📦 Code-Bundle


## `modules\bot\automation.py`
- Zweck: Bot-Orchestrierung: run_once, Loop ON/OFF, State & Summary.
- Zeilen: 341, Kommentare: 19, Funktionen: 18

```python
# modules/bot/automation.py
from __future__ import annotations
import json, time, sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Projekt-Root für Imports sicherstellen
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Projekt-Imports
from shared.utils.logger import get_logger
from modules.data.ingest import ingest_one
from modules.trade.ops import place_orders
from modules.trade.common import contract_for  # ggf. später genutzt

# ASK-Flow
from modules.bot.ask_flow import run_ask_flow, ask_flow_status, cancel_ask_flow

# Telegram-Router
from shared.system.telegram_notifier import (
    to_control, to_logs, to_orders, to_alerts,
)

log = get_logger("bot")

# ----------------------------- Helpers ---------------------------------
def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d")

def _safe_bar(barsize: str) -> str:
    return barsize.replace(" ", "")

def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config fehlt: {path}")
    import yaml
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _ensure_dirs():
    for p in ["data", "data_clean", "reports/reco", "runtime"]:
        Path(p).mkdir(parents=True, exist_ok=True)

def _read_csv_closes(csv_path: Path) -> Tuple[List[str], List[float]]:
    if not csv_path.exists():
        return [], []
    lines = [ln for ln in csv_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    if not lines:
        return [], []
    hdr = [h.strip() for h in lines[0].split(",")]
    idx = {h: i for i, h in enumerate(hdr)}
    out_ts, out_c = [], []
    for ln in lines[1:]:
        parts = ln.split(",")
        try:
            out_ts.append(parts[idx["datetime"]])
            out_c.append(float(parts[idx["close"]]))
        except Exception:
            continue
    return out_ts, out_c

def _notify_summary(lines: List[str]):
    if not lines:
        return
    to_logs("ℹ️ INFO:\n" + "\n".join(lines))

def _sma(series: List[float], window: int) -> List[Optional[float]]:
    out = [None] * len(series)
    s = 0.0
    for i, v in enumerate(series):
        s += v
        if i >= window:
            s -= series[i - window]
        if i >= window - 1:
            out[i] = s / window
    return out

def _last_cross_dir(fast: List[Optional[float]], slow: List[Optional[float]]) -> Optional[Tuple[int, str]]:
    n = min(len(fast), len(slow))
    prev = None
    last = None
    for i in range(n):
        if fast[i] is None or slow[i] is None:
            continue
        sgn = 1 if fast[i] > slow[i] else (-1 if fast[i] < slow[i] else 0)
        if prev is None:
            prev = sgn
            continue
        if sgn != prev and sgn != 0:
            last = (i, "BUY" if sgn > 0 else "SELL")
        prev = sgn
    return last

def _signal_for_symbol(sym: str, asset: str, barsize: str, strat: Dict[str, Any]) -> Dict[str, Any]:
    safe_bar = _safe_bar(barsize)
    clean = Path(f"data_clean/{asset}_{sym}_{safe_bar}.csv")
    ts, closes = _read_csv_closes(clean)
    if len(closes) == 0:
        return {"symbol": sym, "error": "no_clean_data", "path": str(clean)}
    fast_n = int(strat.get("fast", 10))
    slow_n = int(strat.get("slow", 20))
    sf = _sma(closes, fast_n)
    ss = _sma(closes, slow_n)
    lc = _last_cross_dir(sf, ss)
    if not lc:
        return {"symbol": sym, "signal": None, "reason": "no_cross"}
    i, side = lc
    ts_cross = ts[i] if i < len(ts) else None
    return {
        "symbol": sym,
        "signal": {"action": side, "t": ts_cross, "kind": "sma_cross", "fast": fast_n, "slow": slow_n},
        "path": str(clean),
    }

def _write_reco(signals: List[Dict[str, Any]], cfg: Dict[str, Any], cycle_id: str) -> Path:
    d = Path("reports/reco") / _today_str()
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"reco_{cycle_id}.json"
    payload = {
        "cycle_id": cycle_id,
        "ts_utc": datetime.now(timezone.utc).isoformat(),
        "config": {
            "data": cfg.get("data", {}),
            "strategy": cfg.get("strategy") or cfg.get("strat") or {},
            "exec": cfg.get("exec", {}),
        },
        "signals": signals,
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out

def _save_state(cycle_id: str, reco_file: Path):
    st = {"last_cycle_id": cycle_id, "last_reco": str(reco_file)}
    Path("runtime").mkdir(parents=True, exist_ok=True)
    (Path("runtime") / "bot_state.json").write_text(json.dumps(st, indent=2), encoding="utf-8")

def _load_state() -> Dict[str, Any]:
    p = Path("runtime/bot_state.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

# ----------------------------- Public API --------------------------------
def run_once(cfg_path: str = "config/bot.yaml") -> None:
    _ensure_dirs()
    cfg = _load_yaml(Path(cfg_path))

    data_cfg = cfg.get("data", {})
    exec_cfg = cfg.get("exec", {}) or {}
    strat_cfg = cfg.get("strategy") or cfg.get("strat")
    if not strat_cfg:
        raise KeyError("strategy")

    asset = (exec_cfg.get("asset") or "stock").lower()
    barsize = data_cfg.get("barsize", "5 mins")
    duration = data_cfg.get("duration", "5 D")
    what = data_cfg.get("what", "TRADES")
    rth = bool(data_cfg.get("rth", True))

    symbols = cfg.get("symbols") or ["AAPL", "MSFT", "SPY"]
    symbols = [s.strip().upper() for s in symbols if s and s.strip()]

    cycle_id = _now_ts()
    hdr = f"▶ Cycle {cycle_id}  ({len(symbols)} Symbole)  strat={strat_cfg.get('name','sma_cross')}  {barsize}"
    print(hdr)
    to_logs(hdr)

    # 1) Ingest
    for sym in symbols:
        try:
            msg = f"🚀 Fetch {sym} | {asset} | {duration} | {barsize} | what={what} | RTH={rth}"
            print(msg); to_logs(msg)
            ingest_one(symbol=sym, asset=asset, duration=duration, barsize=barsize, what=what, rth=rth, overwrite=False)
        except Exception as e:
            err = f"❌ Ingest-Fehler {sym}: {e}"
            print(err); to_alerts(err)

    # 2) Signale
    signals: List[Dict[str, Any]] = []
    for sym in symbols:
        try:
            sig = _signal_for_symbol(sym, asset, barsize, strat_cfg)
            signals.append(sig)
        except Exception as e:
            signals.append({"symbol": sym, "error": f"signal_failed:{e}"})
            to_alerts(f"signal_failed {sym}: {e}")

    reco_file = _write_reco(signals, cfg, cycle_id)
    print(f"✓ Signals → {reco_file}")
    to_logs(f"✓ Signals → {reco_file}")

    # 3) Exec
    mode = (exec_cfg.get("mode") or "ASK").upper()  # ASK | AUTO | OFF
    qty = float(exec_cfg.get("qty", 1))
    tif = exec_cfg.get("tif", "DAY")
    order_type = (exec_cfg.get("order_type", "MKT") or "MKT").upper()

    placed = 0
    if mode == "AUTO":
        to_place: List[str] = []
        sides: List[str] = []
        for s in signals:
            sig = s.get("signal")
            if not sig:
                continue
            action = sig.get("action")
            if action in ("BUY", "SELL"):
                to_place.append(s["symbol"]); sides.append(action)
        if to_place:
            buys = [sym for sym, side in zip(to_place, sides) if side == "BUY"]
            sells = [sym for sym, side in zip(to_place, sides) if side == "SELL"]
            if buys:
                to_orders(f"AUTO → BUY {buys} qty={qty} {order_type} tif={tif}")
                place_orders(buys, asset, "BUY", order_type, qty, None, None, tif, safe_dev=0, dry_run=False)
                placed += len(buys)
            if sells:
                to_orders(f"AUTO → SELL {sells} qty={qty} {order_type} tif={tif}")
                place_orders(sells, asset, "SELL", order_type, qty, None, None, tif, safe_dev=0, dry_run=False)
                placed += len(sells)
        msg = f"exec: AUTO  placed={placed}"
        print(msg); to_logs(msg)

    # ASK-Mode Parametrisierung (blocking | async)
    ask_mode = (cfg.get("telegram", {}).get("ask_mode") or "blocking").lower()
    ask_window = int(cfg.get("telegram", {}).get("ask_window_sec", 120))

    if mode == "ASK":
        try:
            print("[ASK_DEBUG] calling run_ask_flow…", {"qty": qty, "tif": tif, "order_type": order_type})
            st = ask_flow_status()
            started_at = float(st.get("started_at", 0) or 0)
            still_active = bool(st.get("active"))
            age = time.time() - started_at if started_at else 0.0

            # Kollisionsschutz im Loop:
            if still_active and age <= ask_window + 5:
                to_control("ASK noch aktiv → Skip in dieser Iteration.")
                # trotzdem Status-Infos zu den Signalen posten
            elif still_active and age > ask_window + 5:
                # Hängenden Flow aufräumen
                to_control("ASK hängt → sende Cancel und starte neu.")
                try:
                    cancel_ask_flow()
                except Exception:
                    pass
                time.sleep(1.0)
                placed = run_ask_flow(signals, exec_cfg, mode=ask_mode, window_sec=ask_window)
            else:
                placed = run_ask_flow(signals, exec_cfg, mode=ask_mode, window_sec=ask_window)
        except Exception as e:
            print(f"❌ ASK-Flow Fehler: {e}")
            placed = 0

        # Infozeilen (immer)
        for s in signals:
            sig = s.get("signal")
            if not sig:
                continue
            line = f"ASK → {s['symbol']} {sig['action']} {qty} {order_type} (tif={tif})"
            print(line); to_orders(line)

        if placed == -1:
            msg = f"exec: ASK  placed=running (async, window={ask_window}s)"
        else:
            msg = f"exec: ASK  placed={placed}"
        print(msg); to_logs(msg)

    if mode == "OFF":
        msg = "exec: OFF (nur Signale)"
        print(msg); to_logs(msg)

    # 4) State
    _save_state(cycle_id, reco_file)

    # 5) Telegram-Summary (LOGS)
    feed: List[str] = []
    for s in signals:
        sig = s.get("signal")
        if not sig:
            continue
        feed.append(f"{s['symbol']}: {sig['action']}  (sma {sig['fast']}/{sig['slow']})")
    feed.append(f"exec: {mode}  placed={placed}")
    _notify_summary(feed)

def start_loop(cfg_path: str = "config/bot.yaml", interval_sec: int | None = None) -> None:
    cfg = _load_yaml(Path(cfg_path))
    itv = int(interval_sec or cfg.get("interval_sec", 120))

    # Intervall an ASK-Fenster anpassen: itv >= ask_window + 30
    try:
        ask_window = int(cfg.get("telegram", {}).get("ask_window_sec", 120))
        itv = max(itv, ask_window + 30)
    except Exception:
        pass

    info = f"⏱  Bot-Loop gestartet (alle {itv}s). Abbruch mit Ctrl+C."
    print(info); to_control(info)
    try:
        while True:
            run_once(cfg_path)
            time.sleep(itv)
    except KeyboardInterrupt:
        msg = "\n⏹  Bot gestoppt."
        print(msg); to_control(msg.strip())

def print_status():
    st = _load_state()
    if not st:
        print("Runtime-State: {}")
        to_control("STATUS: {}")
        return
    txt = json.dumps(st, indent=2, ensure_ascii=False)
    print(txt); to_control(f"STATUS:\n{txt}")

# --- ASK-Flow CLI-Helpers ---
def ask_flow_cancel_cli():
    try:
        cancel_ask_flow()
        print("✓ ASK-Flow: Abbruchsignal gesendet.")
        to_control("ASK-Flow: Abbruchsignal gesendet.")
    except Exception as e:
        err = f"❌ ASK-Flow Abbruch-Fehler: {e}"
        print(err); to_alerts(err)

def ask_flow_status_cli():
    try:
        st = ask_flow_status()
        txt = json.dumps(st, indent=2, ensure_ascii=False)
        print(txt); to_control(f"ASK-Flow Status:\n{txt}")
    except Exception as e:
        err = f"❌ ASK-Flow Status-Fehler: {e}"
        print(err); to_alerts(err)

```

## `modules\bot\ask_flow.py`
- Zweck: ASK-Flow: Inline-Buttons/Timeout, Freigaben, idempotentes Dismiss.
- Zeilen: 192, Kommentare: 4, Funktionen: 10

```python
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
    OFFSET_FILE.write_text(json.dumps({"offset": ofs}), encoding="utf-8")

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
        except Exception:
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

def ask_flow_status() -> Dict[str, Any]:
    st = _load_state()
    st["active"] = bool(LOCK_FILE.exists()) or bool(st.get("active"))
    return st

```

## `control\control_center.py`
- Zweck: Control/Event-Bus: RUN_ONCE, LOOP_ON/OFF, SAFE, STATUS.
- Zeilen: 161, Kommentare: 11, Funktionen: 17

```python
from __future__ import annotations
import json, time, threading, queue, os
from pathlib import Path
from typing import Any, Dict, Optional

# ---------- Persistenz ----------
RUNTIME = Path("runtime"); AUDIT_DIR = Path("reports/audit")
SAFE_FILE = RUNTIME / "safe_mode.json"; HB_FILE = RUNTIME / "heartbeat.json"

def _read_json(p: Path, default: Any) -> Any:
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return default

def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _append_audit(rec: Dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fn = AUDIT_DIR / (time.strftime("%Y%m%d") + ".jsonl")
    with fn.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------- Control Center ----------
class ControlCenter:
    def __init__(self):
        self.q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.running = False
        self.worker: Optional[threading.Thread] = None
        # Loop-Steuerung
        self.loop_on = False
        self.loop_interval = 0
        self._next_loop_ts = 0.0

    def submit(self, cmd: str, args: Dict[str, Any] | None = None, src: str = "terminal") -> None:
        ev = {"ts": time.time(), "cmd": cmd.upper(), "args": args or {}, "src": src}
        self.q.put(ev)
        _append_audit({"type": "enqueue", **ev})

    def start(self):
        if self.running: return
        self.running = True
        self.worker = threading.Thread(target=self._loop, daemon=True, name="control-worker")
        self.worker.start()

    def stop(self):
        self.running = False

    def _loop(self):
        # <<< Asyncio-Loop im Thread bereitstellen >>>
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        while self.running:
            # 1) Periodische Bot-Loops
            now = time.time()
            if self.loop_on and now >= self._next_loop_ts:
                try:
                    self._run_once()
                except Exception as e:
                    _append_audit({"type":"error","ev":{"cmd":"RUN_ONCE(loop)"},"err":str(e)})
                    self._notify(f"RUN_ONCE(loop) Fehler: {e}", level="alert")
                finally:
                    self._next_loop_ts = now + max(10, self.loop_interval)

            # 2) Events verarbeiten
            try:
                ev = self.q.get(timeout=0.5)
            except queue.Empty:
                self._heartbeat()
                continue
            try:
                _append_audit({"type": "dequeue", **ev})
                self._handle(ev)
            except Exception as e:
                _append_audit({"type":"error","ev":ev,"err":str(e)})
                self._notify(f"Control-Fehler: {e}", level="alert")

    # ---------- Handler ----------
    def _handle(self, ev: Dict[str, Any]) -> None:
        cmd = ev["cmd"]; args = ev["args"]
        if cmd in {"RUN_ONCE","PLACE","BUY","SELL"} and self._safe_on():
            self._notify(f"SAFE-MODE aktiv. '{cmd}' blockiert.", level="warning")
            _append_audit({"type":"blocked_safe", **ev}); return

        if cmd == "RUN_ONCE":
            self._run_once()
            self._notify("RUN_ONCE ausgeführt.", level="info")
        elif cmd == "LOOP_ON":
            itv = self._read_interval()
            self.loop_interval = itv
            self.loop_on = True
            self._next_loop_ts = 0.0
            self._notify(f"LOOP_ON (alle {itv}s).", level="info")
        elif cmd == "LOOP_OFF":
            self.loop_on = False
            self._notify("LOOP_OFF.", level="warning")
        elif cmd == "CANCEL_ALL":
            self._cancel_all()
        elif cmd == "SAFE_ON":
            self._set_safe(True)
        elif cmd == "SAFE_OFF":
            self._set_safe(False)
        elif cmd == "STATUS":
            st = self.status()
            self._notify(f"STATUS: {json.dumps(st, ensure_ascii=False)}", level="info")
        else:
            self._notify(f"Unbekanntes Kommando: {cmd}", level="warning")

    # ---------- Aktionen ----------
    def _run_once(self):
        from modules.bot.automation import run_once
        run_once("config/bot.yaml")

    def _read_interval(self) -> int:
        try:
            import yaml
            with open("config/bot.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return int(cfg.get("interval_sec", 120))
        except Exception:
            return 120

    def _cancel_all(self):
        try:
            from shared.ibkr.ibkr_client import IBKRClient
            with IBKRClient(module="control", task="cancel") as ib:
                ib.client.reqGlobalCancel()
            self._notify("Alle offenen Orders storniert.", level="warning")
        except Exception as e:
            self._notify(f"CancelAll fehlgeschlagen: {e}", level="alert")

    # ---------- SAFE/Heartbeat/Status ----------
    def _safe_on(self) -> bool:
        st = _read_json(SAFE_FILE, {"safe": False})
        return bool(st.get("safe", False))

    def _set_safe(self, on: bool):
        _write_json(SAFE_FILE, {"safe": bool(on), "ts": time.time()})
        self._notify(("SAFE_ON" if on else "SAFE_OFF"), level=("warning" if on else "info"))

    def _heartbeat(self):
        hb = {"ts": time.time(), "safe": self._safe_on(), "loop_on": self.loop_on}
        _write_json(HB_FILE, hb)

    def status(self) -> Dict[str, Any]:
        hb = _read_json(HB_FILE, {})
        return {"safe": self._safe_on(), "loop_on": self.loop_on,
                "last_hb": hb.get("ts"), "queue_size": self.q.qsize(),
                "interval_sec": self.loop_interval}

    # ---------- Notifier ----------
    def _notify(self, msg: str, level: str = "info"):
        try:
            from shared.system.telegram_notifier import to_control, to_alerts
            (to_control if level.lower() == "info" else to_alerts)(msg)
        except Exception:
            pass
        print(f"[{level.upper()}] {msg}")

# Singleton
control = ControlCenter()

```

---

**Kopierzeile:**
`modules\bot\automation.py, modules\bot\ask_flow.py, control\control_center.py`