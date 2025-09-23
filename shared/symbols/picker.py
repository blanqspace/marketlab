# shared/symbols/picker.py
from __future__ import annotations
from typing import List
import difflib
from shared.symbols.availability import get_available

def suggestions(prefix: str = "", n: int = 12) -> List[str]:
    data = get_available()
    universe = sorted(data.keys())
    if not prefix:
        return universe[:n]
    pref = prefix.upper()
    starts = [s for s in universe if s.startswith(pref)]
    if len(starts) >= n:
        return starts[:n]
    fuzzy = difflib.get_close_matches(pref, universe, n=n, cutoff=0.6)
    dedup = []
    for s in starts + fuzzy:
        if s not in dedup:
            dedup.append(s)
    return dedup[:n]

def autocorrect(sym: str) -> str:
    s = (sym or "").upper().strip()
    data = get_available()
    if s in data: return s
    uni = list(data.keys())
    m = difflib.get_close_matches(s, uni, n=1, cutoff=0.6)
    return m[0] if m else s
