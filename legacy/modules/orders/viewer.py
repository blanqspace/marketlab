# modules/orders/viewer.py
import os
import json
from pathlib import Path
from shared.utils.logger import get_logger

logger = get_logger("orders_viewer")

ORDERS_FILE = Path("runtime/orders/orders.json")

def _load_orders():
    """Lädt gespeicherte Orders aus runtime/orders/orders.json"""
    if not ORDERS_FILE.exists():
        logger.warning("Keine Order-Datei gefunden.")
        return {"orders": []}
    try:
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Fehler beim Lesen von {ORDERS_FILE}: {e}")
        return {"orders": []}

def show_orders():
    """Zeigt gespeicherte Orders in der Konsole"""
    data = _load_orders()
    orders = data.get("orders", [])
    print("\n📊 Offene Orders")
    print("--------------------------------------------------")
    if not orders:
        print("(Keine Orders gefunden)")
        return
    for o in orders:
        symbol = o.get("symbol", "?")
        side = o.get("side", "?")
        qty = o.get("qty", 0)
        price = o.get("price", 0)
        status = o.get("status", "open")
        print(f"{symbol:10} {side.upper():5} {qty:>5} @ {price:<10} [{status}]")
    print("--------------------------------------------------")
