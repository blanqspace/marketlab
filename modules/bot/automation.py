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
    # runtime defaults
    sm = Path("runtime") / "safe_mode.json"
    if not sm.exists():
        sm.write_text(json.dumps({"safe": False}, ensure_ascii=False, indent=2), encoding="utf-8")

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

def _safe_on() -> bool:
    p = Path("runtime/safe_mode.json")
    if not p.exists():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("safe", False))
    except Exception:
        return False

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

    # SAFE → Exec deaktivieren
    if _safe_on():
        to_logs("SAFE aktiv → Exec wird nicht ausgeführt.")
        mode = "OFF"

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
        # harte Untergrenze: kein Überlappen des ASK-Fensters
        if itv < ask_window + 30:
            to_logs(f"Intervall {itv}s < ask_window+30 ({ask_window+30}s) → setze auf {ask_window+30}s.")
            itv = ask_window + 30
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

if __name__ == "__main__":
    # Einfacher Start für Tests: ein einzelner Zyklus
    run_once()
