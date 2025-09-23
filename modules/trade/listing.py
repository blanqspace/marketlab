# modules/trade/listing.py

from pathlib import Path; import sys
ROOT = Path(__file__).resolve().parents[2]  # Projekt-Root
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from ib_insync import ExecutionFilter
from shared.ibkr.ibkr_client import IBKRClient
from .common import STATUS_DE, fmt_price


ACTIVE = {"Submitted","PreSubmitted","ApiPending","PendingSubmit","PendingCancel","PartiallyFilled"}

def list_orders(show_all=False, show_exec=False, show_pos=False) -> None:
    with IBKRClient(module="order_executor", task="list") as ib:
        ib.reqOpenOrders(); ib.sleep(0.5)
        trades = ib.trades()
        if not show_all:
            trades = [t for t in trades if t.orderStatus and t.orderStatus.status in ACTIVE]

        print("=== Open Orders" + (" (all)" if show_all else "") + " ===")
        if not trades:
            print("(keine)")
        else:
            hdr = f"{'ID':>6}  {'Symbol':<12} {'Side':<4} {'Qty':>7}  {'Type/Price':<18} {'TIF':<6} {'Route':<8}  {'Status':<14}  {'Deutsch':<26}  {'Filled/Rem':>12}"
            print(hdr); print("-"*len(hdr))
            for tr in trades:
                o, s, c = tr.order, tr.orderStatus, tr.contract
                sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
                route = getattr(c, "exchange", "-") or "-"
                side = (o.action or "-").upper()
                qty  = o.totalQuantity
                tif  = o.tif or "-"
                typ  = fmt_price(o)
                st   = s.status if s and s.status else "-"
                de   = STATUS_DE.get(st, "-")
                filled = getattr(s, "filled", 0) or 0
                rem    = getattr(s, "remaining", 0) or 0
                print(f"{o.orderId:>6}  {sym:<12} {side:<4} {qty:>7}  {typ:<18} {tif:<6} {route:<8}  {st:<14}  {de:<26}  {filled:>5}/{rem:<6}")

        if show_exec:
            print("\n=== Executions (heute) ===")
            ex = ib.reqExecutions(ExecutionFilter())
            if not ex: print("(keine)")
            else:
                for f in ex:
                    sym = getattr(f.contract, "localSymbol", "?")
                    print(f"{f.time}  {sym}  {f.side}  {f.shares}@{f.price}  execId={f.execId}")

        if show_pos:
            print("\n=== Positions ===")
            pos = ib.positions()
            if not pos: print("(keine)")
            else:
                for p in pos:
                    c = p.contract
                    sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
                    print(f"{sym:<12} {p.position:>8} @ {p.avgCost}")
