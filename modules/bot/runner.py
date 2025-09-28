from __future__ import annotations
import time, json
from pathlib import Path
from datetime import datetime, timezone
from shared.ibkr.ibkr_client import IBKRClient
from modules.trade.common import contract_for, qualify_or_raise, mid_or_last
from modules.data.ingest import ingest_one
from modules.signal.engine import compute_signal_sma  # neu (unten)
from modules.trade.ops import place_orders        # vorhanden
from shared.utils.logger import get_logger
from shared.system.telegram_notifier import send_telegram_alert

CFG = Path("config/bot.yaml")
RUNTIME = Path("runtime/state.json")
RECO_DIR = Path("reports/reco")

def _now(): return datetime.now(timezone.utc).isoformat()

def load_cfg():
    import yaml
    return yaml.safe_load(CFG.read_text(encoding="utf-8"))

def load_state():
    if RUNTIME.exists():
        return json.loads(RUNTIME.read_text(encoding="utf-8"))
    return {"last_cycle": None, "last_errors": [], "pending": []}

def save_state(st): RUNTIME.parent.mkdir(parents=True, exist_ok=True); RUNTIME.write_text(json.dumps(st,indent=2), "utf-8")

def ensure_data(sym, cfg):
    # nutzt bestehenden ingest_one (append wenn overwrite=False)
    try:
        ingest_one(symbol=sym, asset=cfg["asset"], duration=cfg["duration"],
                   barsize=cfg["barsize"], what=cfg["what"], rth=cfg["rth"], overwrite=False)
        return True, ""
    except Exception as e:
        return False, str(e)

def decide_action(sig):
    # sig: {"symbol","side":"BUY/SELL/HOLD","reason", ...}
    side = sig["side"]
    if side in ("BUY","SELL"): return side
    return "HOLD"

def notify(lines, cfg):
    if cfg.get("telegram",{}).get("enabled"):
        try: send_telegram_alert("\n".join(lines))
        except Exception: pass

def write_reco(cycle_id, items):
    d = RECO_DIR / datetime.now().strftime("%Y%m%d")
    d.mkdir(parents=True, exist_ok=True)
    fp = d / f"reco_{cycle_id}.json"
    fp.write_text(json.dumps({"generated_at": _now(), "items": items}, indent=2, ensure_ascii=False), "utf-8")
    return fp

def run_once():
    log = get_logger("bot")
    cfg = load_cfg(); st = load_state()
    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    syms = cfg["symbols"]

    reco_items, feed = [], []
    feed.append(f"▶ Cycle {cycle_id}  ({len(syms)} Symbole)  strat={cfg['strategy']['name']}  {cfg['barsize']}")

    # 1) Daten + Signale
    for sym in syms:
        ok, err = ensure_data(sym, cfg)
        if not ok:
            msg = f"{sym}: ingest ❌ {err}"
            feed.append(msg)
            reco_items.append({"symbol": sym, "error": err})
            continue

        # Signal rechnen (SMA Cross auf CLEAN CSV)
        try:
            sig = compute_signal_sma(sym, asset=cfg["asset"], barsize=cfg["barsize"],
                                     fast=cfg["strategy"]["params"]["fast"],
                                     slow=cfg["strategy"]["params"]["slow"])
            act = decide_action(sig)
            reco_items.append({**sig, "action": act})
            feed.append(f"{sym}: {act}  • {sig['reason']}")
        except Exception as e:
            msg = f"{sym}: signal ❌ {e}"
            feed.append(msg)
            reco_items.append({"symbol": sym, "error": str(e)})

    fp = write_reco(cycle_id, reco_items)
    feed.append(f"✓ Signals → {fp}")

    # 2) Ausführung (je nach Modus)
    mode = (cfg.get("auto_mode") or "off").lower()
    if mode == "off":
        feed.append("exec: OFF (nur Signale)")
    else:
        with IBKRClient(module="bot", task="exec") as ib:
            placed = 0
            for it in reco_items:
                if it.get("error"): continue
                if it["action"] in ("BUY","SELL"):
                    if mode == "ask":
                        # Telegram/Console Bestätigung nur als Info – Bestätigungslösung kann später erweitert werden
                        feed.append(f"ASK → {it['symbol']} {it['action']} {cfg['risk']['default_qty']} MKT (tif={cfg['risk']['tif']})")
                        continue
                    try:
                        # Market ausführen (einfach), erweiterbar auf LMT/STP
                        place_orders(
                            symbols=[it["symbol"]],
                            asset=cfg["asset"], side=it["action"], order_type="MKT",
                            qty=float(cfg["risk"]["default_qty"]),
                            lmt=None, stp=None, tif=cfg["risk"]["tif"],
                            safe_dev=0.0, dry_run=False, cancel_after=None
                        )
                        placed += 1
                    except Exception as e:
                        feed.append(f"{it['symbol']}: place ❌ {e}")
            feed.append(f"exec: {mode.upper()}  placed={placed}")

    st["last_cycle"] = cycle_id
    save_state(st)
    notify(feed, cfg)
    print("\n".join(feed))

def run_forever():
    cfg = load_cfg()
    sec = int(cfg.get("run_every_sec", 120))
    while True:
        run_once()
        time.sleep(sec)

