# modules/trade/menu.py
from __future__ import annotations

import sys, time
from pathlib import Path
from typing import Optional, List, Dict, Any
from .common import qualify_or_raise


from ib_insync import IB, MarketOrder, LimitOrder, StopOrder, StopLimitOrder, ExecutionFilter

# Projekt-Root für Imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.ibkr.ibkr_client import IBKRClient
from .common import is_paper, contract_for, mid_or_last, fmt_price

# Vorschläge / Verfügbarkeit (dynamisch)
try:
    from shared.symbols.picker import suggestions, autocorrect
    from shared.symbols.availability import get_available
except Exception:
    suggestions = None
    autocorrect = None
    get_available = None

# Reporting (optional)
try:
    from shared.diag.report import append_event
except Exception:
    def append_event(kind: str, payload: Dict[str, Any] | None = None) -> None:
        pass

# ======= UI-Helfer ==========================================================
def header(title: str):
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)
    print("Hinweis: 0=Zurück  M=Menü  Q=Beenden  H=Hinweise")

def _nav_check(s: str):
    s = (s or "").strip().lower()
    if s in ("0", "b", "back"):
        raise KeyboardInterrupt
    if s in ("m", "menu"):
        raise SystemExit
    if s in ("q", "quit", "x", "exit"):
        raise SystemExit

def ask(label: str, default: str | None = None) -> str:
    raw = input(f"{label}{f' [{default}]' if default is not None else ''}: ").strip()
    if raw == "" and default is not None:
        raw = default
    _nav_check(raw)
    return raw

def ask_int(label: str, default: int | None = None, valid: List[int] | None = None) -> int:
    while True:
        try:
            v = int(ask(label, str(default) if default is not None else None))
            if valid and v not in valid:
                print(f"Bitte {valid} wählen."); continue
            return v
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            print("Bitte Zahl eingeben.")

def ask_float(label: str, default: float | None = None) -> float:
    while True:
        try:
            raw = ask(label, str(default) if default is not None else None)
            return float(raw)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception:
            print("Bitte Zahl eingeben, z. B. 1 oder 123.45.")

# ======= Presets ============================================================
# Minimaler integrierter Katalog. Du kannst eigene Presets in config laden.
PRESETS: Dict[str, Dict[str, Any]] = {
    "scalp_stock": {
        "title": "Schneller Market-Kauf",
        "desc": "Market BUY, intraday.",
        "asset": "stock",
        "side": "BUY",
        "type": "MKT",
        "qty": 10,
        "tif": "DAY",
    },
    "short_stock": {
        "title": "Market-Short",
        "desc": "Market SELL, intraday.",
        "asset": "stock",
        "side": "SELL",
        "type": "MKT",
        "qty": 20,
        "tif": "DAY",
    },
    "swing_limit": {
        "title": "Swing-Limit",
        "desc": "Limit ~1% unter Mid, GTC.",
        "asset": "stock",
        "side": "BUY",
        "type": "LMT",
        "qty": 50,
        "tif": "GTC",
        "safe_dev": 1.0,  # %
    },
    "breakout_buy_stoplimit": {
        "title": "Breakout BUY Stop-Limit",
        "desc": "Stop knapp über Mid, Limit ~0.6% darüber.",
        "asset": "stock",
        "side": "BUY",
        "type": "STOP_LIMIT",
        "qty": 5,
        "tif": "DAY",
        "safe_dev": 0.6,  # % oberhalb
    },
    "forex_breakout": {
        "title": "FX Breakout Stop-Limit (Trockenlauf)",
        "desc": "Stop-Limit ~0.5% über Mid, Dry-Run.",
        "asset": "forex",
        "side": "BUY",
        "type": "STOP_LIMIT",
        "qty": 10000,
        "tif": "GTC",
        "safe_dev": 0.5,
        "dry_run": True,
    },
}

def _choose_preset() -> tuple[str, Dict[str, Any]] | None:
    header("Quick Place • Preset-Auswahl")
    keys = list(PRESETS.keys())
    for i, k in enumerate(keys, 1):
        p = PRESETS[k]
        print(f"[{i:2}] {k:<26} – {p.get('title','')}  ({p.get('desc','')})")
    print("[ 0] Zurück")
    idx = ask_int("Auswahl", valid=list(range(0, len(keys)+1)))
    if idx == 0:
        return None
    k = keys[idx-1]
    return k, PRESETS[k]

# ======= Symbol-Prompt mit Vorschlägen/Autokorrektur =======================
def prompt_symbols(default_sym: str = "AAPL") -> list[str]:
    """
    Zeigt Vorschläge, korrigiert Tippfehler, filtert NUR wenn Availability-Cache befüllt ist.
    Fällt sonst auf ungefilterte Liste zurück und versucht eine leichte IB-Qualifikation.
    """
    # 1) Vorschläge
    try:
        if suggestions:
            print("Vorschläge:", ", ".join(suggestions("", 12)))
        else:
            print("Vorschläge: AAPL, AMD, AMZN, AUDUSD, EURUSD, GBPUSD, GOOG, META, MSFT, NVDA, QQQ, SPY")
    except Exception:
        print("Vorschläge: AAPL, AMD, AMZN, AUDUSD, EURUSD, GBPUSD, GOOG, META, MSFT, NVDA, QQQ, SPY")

    # 2) Eingabe + Autokorrektur
    raw = ask("Symbole (Komma)", default_sym).strip()
    parts = [s.strip().upper() for s in raw.split(",") if s.strip()]
    try:
        if autocorrect:
            parts = [autocorrect(s) for s in parts]
    except Exception:
        pass

    # 3) Optionaler Availability-Filter NUR wenn Cache Daten hat
    filtered = parts
    try:
        if get_available:
            avail = get_available() or {}
            if any(avail.values()):  # Cache hat Einträge
                usable = []
                for s in parts:
                    info = avail.get(s) or {}
                    if info.get("live") or info.get("delayed") or info.get("historical"):
                        usable.append(s)
                filtered = usable or parts  # nie leer filtern
    except Exception:
        pass

    # 4) Mini-Qualifikation via IB, falls möglich, um Tippfehler/ungültige zu erkennen
    #    Nicht strikt: nur herausfiltern, was eindeutig nicht qualifiziert.
    try:
        from shared.ibkr.ibkr_client import IBKRClient
        from .common import contract_for
        checked = []
        with IBKRClient(module="symbol_probe", task="prompt_check") as ib:
            for s in filtered:
                try:
                    c = contract_for(s, "stock")  # stock als Default; FX erkenntst du über Preset
                    c = qualify_or_raise(ib, c)
                    checked.append(s)
                except Exception:
                    # nicht hart verwerfen – Nutzer darf trotzdem testen
                    checked.append(s)
        filtered = checked or filtered
    except Exception:
        pass

    if not filtered:
        print("Keine verfügbaren Symbole erkannt. Führe zuerst Diagnose → Symbol-Scan aus.")
    return filtered


# ======= Order-Build =======================================================
def _safe_prices(side: str, mid: Optional[float], dev_pct: float,
                 order_type: str, lmt: Optional[float], stp: Optional[float]):
    if mid is None or dev_pct <= 0:
        return lmt, stp
    side = side.upper()
    ot = order_type.upper()
    if side == "BUY":
        base_up = round(mid * (1 + dev_pct / 100), 4)
        base_dn = round(mid * (1 - dev_pct / 100), 4)
    else:
        base_up = round(mid * (1 + dev_pct / 100), 4)
        base_dn = round(mid * (1 - dev_pct / 100), 4)
    if ot in ("LMT", "LIMIT"):
        lmt = base_dn if side == "BUY" else base_up
    elif ot in ("STP", "STOP"):
        stp = base_up if side == "BUY" else base_dn
    elif ot.replace("_", " ") in ("STP LMT", "STOP LIMIT"):
        stp = base_up if side == "BUY" else base_dn
        lmt = round(stp * (1 + (0.3/100) if side == "BUY" else 1 - (0.3/100)), 4)  # Limit leicht hinter Stop
    return lmt, stp

def _build_order(order_type: str, side: str, qty: float,
                 lmt: Optional[float], stp: Optional[float], tif: str):
    side = side.upper()
    ot = order_type.upper()
    if ot in ("MKT", "MARKET"):
        return MarketOrder(side, totalQuantity=qty, tif=tif)
    if ot in ("LMT", "LIMIT"):
        if lmt is None:
            raise ValueError("Limit-Preis fehlt.")
        return LimitOrder(side, totalQuantity=qty, lmtPrice=float(lmt), tif=tif)
    if ot in ("STP", "STOP"):
        if stp is None:
            raise ValueError("Stop-Preis fehlt.")
        return StopOrder(side, totalQuantity=qty, auxPrice=float(stp), tif=tif)
    if ot.replace("_", " ") in ("STP LMT", "STOP LIMIT"):
        if stp is None or lmt is None:
            raise ValueError("Stop/Limit-Preis fehlt.")
        return StopLimitOrder(side, totalQuantity=qty, auxPrice=float(stp), lmtPrice=float(lmt), tif=tif)
    raise ValueError(f"Unbekannter Ordertyp: {order_type}")

# ======= Screens ===========================================================
def list_screen():
    header("Orders anzeigen (alles → optional filtern)")
    with IBKRClient(module="order_executor", task="list") as ib:
        ib.reqOpenOrders(); ib.sleep(0.4)
        trades = ib.trades()

        # 1) Alles kompakt zeigen
        print("\nAlle Orders (kompakt):")
        if not trades:
            print("(keine)")
        else:
            hdr = f"{'ID':>6}  {'Symbol':<12} {'Side':<4} {'Qty':>7}  {'Type/Price':<18} {'TIF':<6} {'Route':<8}  {'Status':<14}  {'Filled/Rem':>12}"
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
                filled = getattr(s, "filled", 0) or 0
                rem    = getattr(s, "remaining", 0) or 0
                print(f"{o.orderId:>6}  {sym:<12} {side:<4} {qty:>7}  {typ:<18} {tif:<6} {route:<8}  {st:<14}  {filled:>5}/{rem:<6}")

        # 2) Optional: Filter danach
        flt = ask("Filter (leer=keiner)  z.B. 'sym=AAPL status=Submitted'", "")
        if flt:
            want_sym = None; want_status = None
            for tok in flt.split():
                if tok.lower().startswith("sym="): want_sym = tok.split("=",1)[1].upper()
                if tok.lower().startswith("status="): want_status = tok.split("=",1)[1]
            def ok(tr):
                o,s,c = tr.order, tr.orderStatus, tr.contract
                if want_sym:
                    sym = getattr(c, "localSymbol", getattr(c,"symbol","")).upper()
                    if sym != want_sym: return False
                if want_status:
                    st = s.status if s else ""
                    if st != want_status: return False
                return True
            ft = [t for t in trades if ok(t)]
            print("\nGefiltert:")
            if not ft:
                print("(keine)")
            else:
                for tr in ft:
                    o, s, c = tr.order, tr.orderStatus, tr.contract
                    sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
                    print(f"  id={o.orderId}  {sym}  {o.action} {o.totalQuantity}  {fmt_price(o)}  {s.status if s else '-'}")

    input("\nEnter=weiter ...")

def cancel_screen():
    header("Orders stornieren")
    print("1) Nach Order-ID")
    print("2) Alle offenen")
    print("3) Nach Symbol")
    mode = ask_int("Auswahl", valid=[1,2,3])

    ACTIVE = {"Submitted","PreSubmitted","ApiPending","PendingSubmit","PartiallyFilled","PendingCancel"}
    with IBKRClient(module="order_executor", task="cancel") as ib:
        ib.reqOpenOrders(); ib.sleep(0.3)
        trs = ib.trades()

        target = []
        if mode == 1:
            oid = ask_int("Order-ID")
            target = [t for t in trs if t.order.orderId == oid and t.orderStatus and t.orderStatus.status in ACTIVE]
        elif mode == 2:
            target = [t for t in trs if t.orderStatus and t.orderStatus.status in ACTIVE]
        else:
            sym = ask("Symbol (z. B. AAPL)").upper()
            for t in trs:
                st = getattr(t, "orderStatus", None)
                c  = getattr(t, "contract", None)
                if not (st and c): continue
                csym = getattr(c, "localSymbol", getattr(c, "symbol", "")).upper()
                if st.status in ACTIVE and csym == sym:
                    target.append(t)

        if not target:
            print("Keine passenden offenen Orders.")
        else:
            for tr in target:
                ib.cancelOrder(tr.order)
            ib.sleep(0.4)
            ids = [t.order.orderId for t in target]
            print(f"Storno gesendet für {len(ids)}: {ids}")
            append_event("order_autocancel", {"ids": ids})

    input("\nEnter=weiter ...")

def quick_place_screen():
    # Preset wählen
    choice = _choose_preset()
    if not choice:
        return
    key, preset = choice
    header(f"Quick Place • Preset: {key}")
    print(preset.get("title",""))
    if preset.get("desc"):
        print(preset["desc"])

    # Symbole
    syms = prompt_symbols("AAPL")
    if not syms:
        _ = ask("Enter=zurück", "")
        return

    # Menge überschreiben?
    qty_over = ask("Menge überschreiben (leer=Preset)", "").strip()
    qty = float(qty_over) if qty_over else float(preset.get("qty", 1))

    asset = preset.get("asset", "stock")
    side  = preset.get("side", "BUY").upper()
    ot    = preset.get("type", "MKT").upper()
    tif   = preset.get("tif", "DAY").upper()
    safe_dev = float(preset.get("safe_dev", 0.0))
    dry_run = bool(preset.get("dry_run", False))

    with IBKRClient(module="order_executor", task=f"quick_{key}") as ib:
        if not is_paper(ib):
            print("Hinweis: Kein Paper-Account erkannt (DU…).")

        for sym in syms:
            c = contract_for(sym, asset)
            try:
                c = qualify_or_raise(ib, c)
            except Exception as e:
                print(f"❌ {sym}: {e}")
                append_event("order_error", {"symbol": sym, "message": str(e)})
                continue

            mid = mid_or_last(ib, c)
            # automatische Preise
            lmt = None; stp = None
            lmt, stp = _safe_prices(side, mid, safe_dev, ot, lmt, stp)

            # Safety: keine Preisorders ohne Referenz
            if ot in ("LMT", "STP", "STOP_LIMIT") and (mid is None) and (lmt is None and stp is None):
                print(f"❌ {sym}: kein Preis verfügbar (weder Mid/Last).")
                append_event("order_error", {"symbol": sym, "message": "no_price"})
                continue

            try:
                order = _build_order(ot, side, qty, lmt, stp, tif)
            except Exception as e:
                print(f"❌ {sym}: {e}")
                append_event("order_error", {"symbol": sym, "message": str(e)})
                continue

            print(f"→ {sym}: {side} {qty} {ot}  LMT={getattr(order,'lmtPrice',None)} STP={getattr(order,'auxPrice',None)}  TIF={tif}  (mid={mid})")

            if dry_run:
                print("🧪 Dry-Run – nicht gesendet.")
                append_event("order_dryrun", {"symbol": sym, "preset": key})
                continue

            tr = ib.placeOrder(c, order)
            ib.sleep(0.5)
            st = tr.orderStatus.status if tr.orderStatus else "-"
            print(f"✓ id={tr.order.orderId} status={st}")
            append_event("order_sent", {"symbol": sym, "preset": key, "status": st})

    input("\nEnter=weiter ...")

# ======= Hauptmenü (Trade) =================================================
def main_menu():
    while True:
        try:
            header("Trade Hub")
            print("1) Quick Place (mit Preset)")
            print("2) Presets anzeigen")
            print("3) Orders anzeigen")
            print("4) Orders stornieren")
            print("0) Zurück")
            ch = ask_int("Auswahl", valid=[0,1,2,3,4])
            if ch == 0:
                break
            if ch == 1:
                quick_place_screen()
            elif ch == 2:
                header("Presets")
                for k, v in PRESETS.items():
                    print(f"- {k}: {v.get('title','')}  [{v.get('asset','')}/{v.get('type','')}]  {v.get('desc','')}")
                input("\nEnter=weiter ...")
            elif ch == 3:
                list_screen()
            elif ch == 4:
                cancel_screen()
        except KeyboardInterrupt:
            break
        except SystemExit:
            sys.exit(0)

if __name__ == "__main__":
    main_menu()


