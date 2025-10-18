# modules/trade/common.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional
from ib_insync import IB, Stock, Forex, Contract

# Projekt-Root für Imports sicherstellen (marketlab/)
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Englischer Status -> Deutsch (für Listings)
STATUS_DE = {
    "PendingSubmit":     "Wird an den Broker gesendet",
    "ApiPending":        "Wartet auf API-Verarbeitung",
    "PreSubmitted":      "Vorab eingereicht (evtl. vor Börsenöffnung)",
    "Submitted":         "Eingereicht/Offen (aktiv)",
    "PendingCancel":     "Storno angefordert",
    "Cancelled":         "Storniert",
    "Inactive":          "Inaktiv (Regel/Routing-Problem)",
    "Filled":            "Vollständig ausgeführt",
    "PartiallyFilled":   "Teilweise ausgeführt",
    "ApiCancelled":      "Per API storniert",
}

__all__ = [
    "STATUS_DE",
    "is_paper",
    "contract_for",
    "mid_or_last",
    "fmt_price",
    "qualify_or_raise",  # ⬅ hinzugefügt
]

def is_paper(ib: IB) -> bool:
    """True, wenn mindestens ein DU…-Account (Paper) verfügbar ist."""
    try:
        return any(str(a).upper().startswith("DU") for a in ib.managedAccounts())
    except Exception:
        return False

def contract_for(symbol: str, asset: str) -> Contract:
    """IBKR-Contract für Symbol/Asset (asset: 'stock' oder 'forex')."""
    asset = (asset or "stock").strip().lower()
    if asset == "forex":
        return Forex(symbol)
    return Stock(symbol, "SMART", "USD")

def mid_or_last(ib: IB, c: Contract) -> Optional[float]:
    """
    Mid (Bid/Ask-Mittel) oder Last/Close, falls Mid fehlt.
    Unterdrückt harmlose cancelMktData-Warnungen.
    """
    try:
        ib.reqMarketDataType(3)  # 3 = delayed OK
    except Exception:
        pass
    t = ib.reqMktData(c, "", False, False)
    ib.sleep(1.0)
    try:
        bid = getattr(t, "bid", None)
        ask = getattr(t, "ask", None)
        if bid is not None and ask is not None:
            return (bid + ask) / 2
        return getattr(t, "last", None) or getattr(t, "close", None)
    finally:
        try:
            ib.cancelMktData(t)
        except Exception:
            pass

def _clean_placeholder(v) -> Optional[float]:
    """IB-Platzhalter wie 1.797693e+308 → None."""
    try:
        fv = float(v)
        if fv > 1e100:
            return None
        return fv
    except Exception:
        return None

def fmt_price(o) -> str:
    """
    Hübsche Orderpreis-Darstellung:
    - MKT
    - LMT 123.45
    - STP 120.00
    - STP 120.00 / LMT 121.00
    """
    ot = (getattr(o, "orderType", "") or "").upper()
    lmt = _clean_placeholder(getattr(o, "lmtPrice", None))
    stp = _clean_placeholder(getattr(o, "auxPrice", None))

    if ot in ("MKT", "MARKET"):
        return "MKT"
    if ot in ("LMT", "LIMIT"):
        return f"LMT {lmt}" if lmt is not None else "LMT"
    if ot in ("STP", "STOP"):
        return f"STP {stp}" if stp is not None else "STP"
    if ot.replace("_", " ") in ("STP LMT", "STOP LIMIT"):
        left = f"STP {stp}" if stp is not None else "STP"
        right = f"LMT {lmt}" if lmt is not None else "LMT"
        return f"{left} / {right}"
    return ot or "-"

# ✅ NEU: Contract-Qualifizierung zentral
def qualify_or_raise(ib: IB, c: Contract) -> Contract:
    """
    Qualifiziert einen IBKR-Contract und gibt die konkrete Contract-Variante zurück.
    Hebt eine klare Fehlermeldung, wenn Qualifizierung fehlschlägt.
    """
    try:
        res = ib.qualifyContracts(c)
    except Exception as e:
        raise RuntimeError(f"Contract-Qualifizierung fehlgeschlagen: {e}")
    if not res:
        raise RuntimeError(f"Contract konnte nicht qualifiziert werden: {c!r}")
    return res[0]

