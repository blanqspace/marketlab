# modules/trade/ops.py
from __future__ import annotations

from pathlib import Path
import sys
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ib_insync import MarketOrder, LimitOrder, StopOrder, StopLimitOrder, ExecutionFilter
from shared.ibkr.ibkr_client import IBKRClient
from .common import is_paper, contract_for, mid_or_last, fmt_price

# Telegram-Routing
try:
    from shared.system.telegram_notifier import to_orders, to_logs, to_alerts
except Exception:
    def to_orders(_): pass
    def to_logs(_): pass
    def to_alerts(_): pass

ACTIVE = {"Submitted","PreSubmitted","ApiPending","PendingSubmit","PendingCancel","PartiallyFilled"}

# ---------- intern ----------
def _build_order(order_type: str, side: str, qty: float,
                 lmt: Optional[float], stp: Optional[float], tif: str):
    side = side.upper()
    ot = order_type.upper()

    if ot in ("MKT","MARKET"):
        return MarketOrder(side, qty, tif=tif)

    if ot in ("LMT","LIMIT"):
        if lmt is None:
            raise ValueError("Limit-Preis erforderlich für LIMIT")
        return LimitOrder(side, qty, float(lmt), tif=tif)

    if ot in ("STP","STOP"):
        if stp is None:
            raise ValueError("Stop-Preis erforderlich für STOP")
        # StopOrder(action, totalQuantity, auxPrice, ...)
        return StopOrder(side, qty, float(stp), tif=tif)

    if ot.replace("_"," ") in ("STP LMT","STOP LIMIT"):
        if stp is None or lmt is None:
            raise ValueError("Stop- und Limit-Preis erforderlich für STOP_LIMIT")
        # StopLimitOrder(action, totalQuantity, auxPrice, lmtPrice, ...)
        return StopLimitOrder(side, qty, float(stp), float(lmt), tif=tif)

    raise ValueError(f"Unbekannter Ordertyp: {order_type}")

def _safe_prices(side: str, mid: Optional[float], dev_pct: float,
                 order_type: str, lmt: Optional[float], stp: Optional[float]):
    if mid is None or not dev_pct or dev_pct <= 0:
        return lmt, stp
    side = side.upper(); ot = order_type.upper()
    base = round(mid * (1 - dev_pct/100), 2) if side=="BUY" else round(mid * (1 + dev_pct/100), 2)
    if ot in ("LMT","LIMIT"): lmt = base if lmt is None else lmt
    elif ot in ("STP","STOP"): stp = base if stp is None else stp
    elif ot.replace("_"," ") in ("STP LMT","STOP LIMIT"):
        stp = base if stp is None else stp
        lmt = base if lmt is None else lmt
    return lmt, stp

# ---------- API ----------
def place_orders(
    symbols: List[str],
    asset: str,
    side: str,
    order_type: str,
    qty: float,
    lmt: Optional[float],
    stp: Optional[float],
    tif: str,
    safe_dev: float = 50.0,
    dry_run: bool = False,
    cancel_after: Optional[float] = None
):
    symbols = [s.strip().upper() for s in symbols if s.strip()]
    with IBKRClient(module="order_executor", task=f"place_{order_type}") as ib:
        if not is_paper(ib):
            msg = "⚠️ Hinweis: Kein DU… Paper-Account erkannt."
            print(msg); to_alerts(msg)
        for sym in symbols:
            c = contract_for(sym, asset)
            try:
                q = ib.qualifyContracts(c)
                if not q:
                    msg = f"❌ {sym}: Unknown/ungültiger Contract."
                    print(msg); to_alerts(msg); continue
                c = q[0]
            except Exception as e:
                msg = f"❌ {sym}: Contract-Qualifizierung fehlgeschlagen: {e}"
                print(msg); to_alerts(msg); continue

            mid = mid_or_last(ib, c)
            lmt_adj, stp_adj = _safe_prices(side, mid, safe_dev, order_type, lmt, stp)

            try:
                order = _build_order(order_type, side, qty, lmt_adj, stp_adj, tif)
            except Exception as e:
                msg = f"❌ {sym}: {e}"
                print(msg); to_alerts(msg); continue

            line = f"→ {sym}: {side} {qty} {order_type}  LMT={getattr(order,'lmtPrice',None)} STP={getattr(order,'auxPrice',None)}  TIF={tif}  (mid={mid})"
            print(line); to_orders(line)
            if dry_run:
                print("🧪 Dry-Run – nicht gesendet."); to_logs("🧪 Dry-Run – nicht gesendet."); continue

            tr = ib.placeOrder(c, order); ib.sleep(0.5)
            ok = f"✓ id={tr.order.orderId} status={tr.orderStatus.status}"
            print(ok); to_orders(ok)
            if cancel_after and cancel_after > 0:
                ib.sleep(cancel_after)
                ib.cancelOrder(order); ib.sleep(0.5)
                msg = f"✖ auto-cancel → {tr.orderStatus.status}"
                print(msg); to_orders(msg)

def list_orders(show_all: bool = True, show_exec: bool = False, show_pos: bool = False) -> None:
    with IBKRClient(module="order_executor", task="list") as ib:
        ib.reqOpenOrders(); ib.sleep(0.5)
        trades = ib.trades()
        if not show_all:
            trades = [t for t in trades if t.orderStatus and t.orderStatus.status in ACTIVE]

        print("\nAlle Orders (kompakt):"); to_logs("Alle Orders (kompakt):")
        if not trades:
            print("(keine)"); to_logs("(keine)")
        else:
            hdr = f"{'ID':>6}  {'Symbol':<12} {'Side':<4} {'Qty':>7}  {'Type/Price':<18} {'TIF':<6} {'Route':<8}  {'Status':<14}  {'Filled/Rem':>12}"
            print(hdr); print("-"*len(hdr)); to_logs(hdr)
            for tr in trades:
                o, s, c = tr.order, tr.orderStatus, tr.contract
                sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
                route = getattr(c, "exchange", "-") or "-"
                side = (o.action or "-").upper()
                qty  = o.totalQuantity
                tif  = o.tif or "-"
                typ  = fmt_price(o)
                st   = s.status if s and s.status else "-"
                filled = getattr(s, "filled", 0) or 0
                rem    = getattr(s, "remaining", 0) or 0
                line = f"{o.orderId:>6}  {sym:<12} {side:<4} {qty:>7}  {typ:<18} {tif:<6} {route:<8}  {st:<14}  {filled:>5}/{rem:<6}"
                print(line); to_logs(line)

        if show_exec:
            print("\nAusführungen (heute):"); to_logs("Ausführungen (heute):")
            ex = ib.reqExecutions(ExecutionFilter())
            if not ex:
                print("(keine)"); to_logs("(keine)")
            else:
                for f in ex:
                    sym = getattr(f.contract, "localSymbol", "?")
                    line = f"{f.time}  {sym}  {f.side}  {f.shares}@{f.price}  execId={f.execId}"
                    print(line); to_logs(line)

        if show_pos:
            print("\nPositionen:"); to_logs("Positionen:")
            pos = ib.positions()
            if not pos:
                print("(keine)"); to_logs("(keine)")
            else:
                for p in pos:
                    c = p.contract
                    sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
                    line = f"{sym:<12} {p.position:>8} @ {p.avgCost}"
                    print(line); to_logs(line)

def cancel_orders(order_id: Optional[int] = None, symbol: Optional[str] = None, cancel_all: bool = False) -> List[int]:
    with IBKRClient(module="order_executor", task="cancel") as ib:
        ib.reqOpenOrders(); ib.sleep(0.3)
        trs = ib.trades()
        target = []
        if cancel_all:
            target = [t for t in trs if t.orderStatus and t.orderStatus.status in ACTIVE]
        elif order_id is not None:
            target = [t for t in trs if t.order.orderId == order_id and t.orderStatus.status in ACTIVE]
        elif symbol:
            sym = symbol.upper().strip()
            for t in trs:
                st = getattr(t, "orderStatus", None)
                c  = getattr(t, "contract", None)
                if not (st and c): continue
                csym = getattr(c, "localSymbol", getattr(c, "symbol", "")).upper()
                if st.status in ACTIVE and csym == sym:
                    target.append(t)
        if not target:
            msg = "Keine passenden offenen Orders gefunden."
            print(msg); to_logs(msg); return []
        for tr in target:
            ib.cancelOrder(tr.order)
        ib.sleep(0.5)
        ids = [t.order.orderId for t in target]
        msg = f"✅ Storno gesendet für {len(ids)}: {ids}"
        print(msg); to_orders(msg)
        return ids
