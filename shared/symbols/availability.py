# shared/symbols/availability.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json, time
from pathlib import Path
from ib_insync import Stock, Forex, IB

from shared.ibkr.ibkr_client import IBKRClient

CACHE = Path("data/available_symbols.json")
TTL_MIN = 60  # Minuten bis Re-Scan nötig

DEFAULT_UNIVERSE: List[Tuple[str, str]] = [
    # stocks
    ("AAPL","stock"),("MSFT","stock"),("NVDA","stock"),("AMZN","stock"),("META","stock"),
    ("SPY","stock"),("QQQ","stock"),("TSLA","stock"),("GOOG","stock"),("AMD","stock"),
    # forex
    ("EURUSD","forex"),("USDJPY","forex"),("GBPUSD","forex"),("XAUUSD","forex"),("AUDUSD","forex"),
]

def _now_iso() -> str:
    return datetime.utcnow().isoformat()

def _load_cache() -> Optional[dict]:
    if not CACHE.exists(): return None
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None

def _save_cache(symbols: Dict[str, Dict]):
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    obj = {"timestamp": _now_iso(), "symbols": symbols}
    CACHE.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

def _is_stale(meta: dict) -> bool:
    try:
        ts = datetime.fromisoformat(meta.get("timestamp","").replace("Z",""))
    except Exception:
        return True
    return datetime.utcnow() - ts > timedelta(minutes=TTL_MIN)

def _contract(sym: str, typ: str):
    return Forex(sym) if typ == "forex" else Stock(sym, "SMART", "USD")

def _check_one(ib: IB, sym: str, typ: str) -> Dict:
    """Ergebnis: {"type":..., "live":bool, "delayed":bool, "historical":bool}"""
    info = {"type": typ}
    c = _contract(sym, typ)

    # 1) Live möglich?
    try:
        ib.reqMarketDataType(1)  # live
        t = ib.reqMktData(c, "", False, False)
        ib.sleep(0.8)
        if getattr(t, "bid", None) or getattr(t, "ask", None) or getattr(t, "last", None):
            info["live"] = True
        ib.cancelMktData(t)
    except Exception:
        pass

    # 2) Delayed möglich?
    if not info.get("live"):
        try:
            ib.reqMarketDataType(3)  # delayed
            t = ib.reqMktData(c, "", False, False)
            ib.sleep(0.8)
            if getattr(t, "bid", None) or getattr(t, "ask", None) or getattr(t, "last", None) or getattr(t, "close", None):
                info["delayed"] = True
                info["historical"] = True
            ib.cancelMktData(t)
        except Exception:
            pass

    # 3) Historisch als Fallback prüfen (kurzer Call)
    if not info.get("historical"):
        try:
            bars = ib.reqHistoricalData(
                c, endDateTime="", durationStr="2 D",
                barSizeSetting="1 day", whatToShow=("MIDPOINT" if typ=="forex" else "TRADES"),
                useRTH=True
            )
            if bars:
                info["historical"] = True
        except Exception:
            pass

    return info

def discover(universe: Optional[List[Tuple[str,str]]] = None, max_workers: int = 6) -> Dict[str, Dict]:
    pairs = universe or DEFAULT_UNIVERSE
    out: Dict[str, Dict] = {}
    with IBKRClient(module="availability", task="discover") as ib:
        # Qualify upfront to reduce 200-Errors
        for sym, typ in pairs:
            try:
                ib.qualify_or_raise(_contract(sym, typ))
            except Exception:
                # lasse trotzdem prüfen; _check_one wird mit delayed/hist umgehen
                pass

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_check_one, ib, s, t):(s,t) for s,t in pairs}
            for f in as_completed(futs):
                s,t = futs[f]
                try:
                    out[s] = f.result()
                except Exception:
                    out[s] = {"type": t}

    _save_cache(out)
    return out

def get_available(force: bool = False) -> Dict[str, Dict]:
    cache = _load_cache()
    if cache and not force and not _is_stale(cache):
        return cache["symbols"]
    return discover()

def list_by(method: str) -> List[str]:
    """method: live | delayed | historical | none"""
    data = get_available()
    res = []
    for s,info in data.items():
        if method == "live" and info.get("live"): res.append(s)
        elif method == "delayed" and info.get("delayed") and not info.get("live"): res.append(s)
        elif method == "historical" and info.get("historical") and not info.get("live"): res.append(s)
        elif method == "none" and not any(info.get(k) for k in ("live","delayed","historical")): res.append(s)
    return sorted(res)
