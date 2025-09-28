from __future__ import annotations
from pathlib import Path

def _read_clean(asset: str, sym: str, barsize: str):
    safe_bar = barsize.replace(" ","")
    p = Path(f"data_clean/{asset.upper()}_{sym.upper()}_{safe_bar}.csv")
    if not p.exists(): raise FileNotFoundError(p)
    rows=[]
    for ln in p.read_text(encoding="utf-8").splitlines()[1:]:
        if not ln.strip(): continue
        dt,o,h,l,c,v = ln.split(",")
        rows.append((dt,float(o),float(h),float(l),float(c),int(float(v) if v else 0)))
    return rows

def _sma(xs, n):
    out=[None]*len(xs); s=0.0
    for i,x in enumerate(xs):
        s+=x
        if i>=n: s-=xs[i-n]
        if i>=n-1: out[i]=s/n
    return out

def compute_signal_sma(symbol: str, asset: str, barsize: str, fast: int, slow: int):
    rows=_read_clean(asset, symbol, barsize)
    closes=[r[4] for r in rows]
    sf=_sma(closes, fast); ss=_sma(closes, slow)
    i=len(closes)-1
    if sf[i] is None or ss[i] is None:
        return {"symbol":symbol, "side":"HOLD", "reason":"zu wenig Bars"}
    last_cross = None
    # simple cross detection
    for j in range(i-1, slow-2, -1):
        if sf[j] is None or ss[j] is None: break
        up = sf[j-1] <= ss[j-1] and sf[j] > ss[j]
        dn = sf[j-1] >= ss[j-1] and sf[j] < ss[j]
        if up: last_cross=("BUY", rows[j][0]); break
        if dn: last_cross=("SELL", rows[j][0]); break
    if last_cross:
        side, when = last_cross
        return {"symbol":symbol, "side":side, "reason":f"SMA{fast}>{slow} Cross {when}"}
    return {"symbol":symbol, "side":"HOLD", "reason":f"SMA{fast} vs {slow} ohne Cross"}

