# modules/trade/cancel.py

from pathlib import Path; import sys
ROOT = Path(__file__).resolve().parents[2]  # Projekt-Root
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from typing import Optional, List
from shared.ibkr.ibkr_client import IBKRClient




ACTIVE = {"Submitted","PreSubmitted","ApiPending","PendingSubmit","PartiallyFilled","PendingCancel"}

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
            print("Keine passenden offenen Orders gefunden."); return []
        for tr in target:
            ib.cancelOrder(tr.order)
        ib.sleep(0.5)
        ids = [t.order.orderId for t in target]
        print(f"✅ Storno gesendet für {len(ids)} Order(s): {ids}")
        return ids
