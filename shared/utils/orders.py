import json
from pathlib import Path

ORDERS_FILE = Path("runtime/orders/orders.json")

def load_orders():
    if not ORDERS_FILE.exists():
        return []
    try:
        return json.loads(ORDERS_FILE.read_text(encoding="utf-8")).get("orders", [])
    except Exception:
        return []

def save_orders(orders):
    ORDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ORDERS_FILE.write_text(json.dumps({"orders": orders}, indent=2, ensure_ascii=False), encoding="utf-8")

def cancel_order(symbol):
    orders = load_orders()
    for o in orders:
        if o["symbol"].upper() == symbol.upper() and o.get("status") == "open":
            o["status"] = "cancelled"
    save_orders(orders)
    return True

def add_order(symbol, side, qty, price):
    orders = load_orders()
    orders.append({
        "symbol": symbol.upper(),
        "side": side.lower(),
        "qty": float(qty),
        "price": float(price),
        "status": "open"
    })
    save_orders(orders)
    return True
