# modules/trade/common.py
from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional
from ib_insync import IB, Stock, Forex, Contract
from ib_insync import IB, Contract


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STATUS_DE = {
    "PendingSubmit": "Wird an den Broker gesendet",
    "ApiPending": "Warten auf API",
    "PreSubmitted": "Vorab eingereicht",
    "Submitted": "Eingereicht/Offen",
    "PendingCancel": "Storno angefordert",
    "Cancelled": "Storniert",
    "Inactive": "Inaktiv",
    "Filled": "Vollständig ausgeführt",
    "PartiallyFilled": "Teilweise ausgeführt",
    "ApiCancelled": "Per API storniert",
}

# einfache Alias-Korrekturen (erweiterbar)
ALIASES = {
    "APPL": "AAPL",
}

def normalize_symbol(s: str) -> str:
    s = (s or "").strip().upper()
    return ALIASES.get(s, s)

def is_paper(ib: IB) -> bool:
    try:
        return any(str(a).upper().startswith("DU") for a in ib.managedAccounts())
    except Exception:
        return False

def contract_for(symbol: str, asset: str) -> Contract:
    sym = normalize_symbol(symbol)
    asset = (asset or "stock").strip().lower()
    if asset == "forex":
        return Forex(sym)
    return Stock(sym, "SMART", "USD")

def mid_or_last(ib: IB, c: Contract) -> Optional[float]:
    try:
        ib.reqMarketDataType(3)  # delayed OK
    except Exception:
        pass
    t = ib.reqMktData(c, "", False, False)
    ib.sleep(1.0)
    try:
        b, a = getattr(t, "bid", None), getattr(t, "ask", None)
        if b and a:
            return (b + a) / 2
        return getattr(t, "last", None) or getattr(t, "close", None)
    finally:
        try: ib.cancelMktData(t)
        except Exception: pass

def fmt_price(o) -> str:
    ot = (getattr(o, "orderType", "") or "").upper()
    lmt = getattr(o, "lmtPrice", None)
    stp = getattr(o, "auxPrice", None)
    if ot in ("MKT","MARKET"): return "MKT"
    if ot in ("LMT","LIMIT"):  return "LMT" if lmt is None else f"LMT {lmt}"
    if ot in ("STP","STOP"):   return "STP" if stp is None else f"STP {stp}"
    if ot.replace("_"," ") in ("STP LMT","STOP LIMIT"):
        left = "STP" if stp is None else f"STP {stp}"
        right= "LMT" if lmt is None else f"LMT {lmt}"
        return f"{left} / {right}"
    return ot or "-"



__all__ = [
    "STATUS_DE",
    "is_paper",
    "contract_for",
    "mid_or_last",
    "fmt_price",
    "qualify_or_raise",  # ← NEU
]

def qualify_or_raise(ib: IB, c: Contract) -> Contract:
    """
    Qualifiziert einen Contract über IB. Liefert den qualifizierten Contract
    oder wirft eine RuntimeError, wenn nicht qualifizierbar.
    """
    try:
        res = ib.qualifyContracts(c)
    except Exception as e:
        raise RuntimeError(f"Qualifikation fehlgeschlagen: {e}")
    if not res:
        raise RuntimeError(f"Contract konnte nicht qualifiziert werden: {c}")
    return res[0]
