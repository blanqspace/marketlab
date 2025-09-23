# modules/trade/placing.py

from pathlib import Path; import sys
ROOT = Path(__file__).resolve().parents[2]  # Projekt-Root
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))
from typing import List, Optional
from ib_insync import MarketOrder, LimitOrder, StopOrder, StopLimitOrder
from shared.ibkr.ibkr_client import IBKRClient
from .common import is_paper, contract_for, mid_or_last



def _build_order(order_type: str, side: str, qty: float,
                 lmt: Optional[float], stp: Optional[float], tif: str):
    side = side.upper()
    ot = order_type.upper()
    if ot in ("MKT","MARKET"):
        return MarketOrder(side, totalQuantity=qty, tif=tif)
    if ot in ("LMT","LIMIT"):
        if lmt is None: raise ValueError("Limit-Preis erforderlich für LIMIT")
        return LimitOrder(side, totalQuantity=qty, lmtPrice=float(lmt), tif=tif)
    if ot in ("STP","STOP"):
        if stp is None: raise ValueError("Stop-Preis erforderlich für STOP")
        return StopOrder(side, totalQuantity=qty, auxPrice=float(stp), tif=tif)
    if ot.replace("_"," ") in ("STP LMT","STOP LIMIT"):
        if stp is None or lmt is None: raise ValueError("Stop- und Limit-Preis erforderlich für STOP_LIMIT")
        return StopLimitOrder(side, totalQuantity=qty, auxPrice=float(stp), lmtPrice=float(lmt), tif=tif)
    raise ValueError(f"Unbekannter Ordertyp: {order_type}")

def _safe_prices(side: str, mid: Optional[float], dev_pct: float,
                 order_type: str, lmt: Optional[float], stp: Optional[float]):
    # nur anwenden, wenn mid eine Zahl ist
    if mid is None or isinstance(mid, float) and (mid != mid):  # NaN
        return lmt, stp  # nichts automatisch setzen
    side = side.upper(); ot = order_type.upper()
    base = round(mid * (1 - dev_pct/100), 2) if side=="BUY" else round(mid * (1 + dev_pct/100), 2)
    if ot in ("LMT","LIMIT"): lmt = base if lmt is None else lmt
    elif ot in ("STP","STOP"): stp = base if stp is None else stp
    elif ot.replace("_"," ") in ("STP LMT","STOP LIMIT"):
        stp = base if stp is None else stp
        lmt = base if lmt is None else lmt
    return lmt, stp

def place_orders(symbols: List[str], asset: str, side: str, order_type: str, qty: float,
                 lmt: Optional[float], stp: Optional[float], tif: str,
                 safe_dev: float = 50.0, dry_run: bool = False, cancel_after: Optional[float] = None):
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    with IBKRClient(module="order_executor", task=f"place_{order_type}") as ib:
        if not is_paper(ib):
            print("⚠ Kein DU… Paper-Account erkannt.")
        for sym in symbols:
            try:
                c = contract_for(sym, asset)
                c = qualify_or_raise(ib, c)   # <— harte Prüfung
                mid = ib.mid_or_last(c)
                lmt_adj, stp_adj = _safe_prices(side, mid, safe_dev, order_type, lmt, stp)

                # harte Validierung bei Limit/Stop
                ot = order_type.upper()
                if ot in ("LMT","LIMIT") and lmt_adj is None:
                    raise ValueError(f"{sym}: Kein Limit-Preis verfügbar. Mid nicht verfügbar. Preis angeben.")
                if ot in ("STP","STOP") and stp_adj is None:
                    raise ValueError(f"{sym}: Kein Stop-Preis verfügbar. Mid nicht verfügbar. Preis angeben.")
                if ot.replace("_"," ") in ("STP LMT","STOP LIMIT") and (lmt_adj is None or stp_adj is None):
                    raise ValueError(f"{sym}: Stop/Limit fehlen. Mid nicht verfügbar. Preise angeben.")

                order = _build_order(order_type, side, qty, lmt_adj, stp_adj, tif)
                print(f"→ {sym}: {side} {qty} {order_type}  LMT={getattr(order,'lmtPrice',None)} STP={getattr(order,'auxPrice',None)}  TIF={tif}  (mid={mid})")
                if dry_run:
                    print("🧪 Dry-Run – nicht gesendet.")
                    continue

                tr = ib.placeOrder(c, order); ib.sleep(0.5)
                print(f"✓ id={tr.order.orderId} status={tr.orderStatus.status}")
                if cancel_after and cancel_after > 0:
                    ib.sleep(cancel_after); ib.cancelOrder(order); ib.sleep(0.5)
                    print(f"✖ auto-cancel → {tr.orderStatus.status}")
            except Exception as e:
                print(f"❌ {sym}: {e}")
