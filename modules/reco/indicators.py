# modules/reco/indicators.py
from __future__ import annotations
from typing import List, Dict, Any, Optional, Tuple


# rows: [(dt, open, high, low, close, volume), ...]
def _col(rows, i) -> List[float]:
    return [float(r[i]) for r in rows]


def sma(series: List[float], n: int) -> List[Optional[float]]:
    out, s = [None]*len(series), 0.0
    for i, v in enumerate(series):
        s += v
        if i >= n: s -= series[i-n]
        if i >= n-1: out[i] = s/n
    return out


def ema(series: List[float], n: int) -> List[Optional[float]]:
    out = [None]*len(series)
    if not series or n <= 1: 
        return out
    k = 2/(n+1)
    s = series[0]
    out[0] = s
    for i in range(1, len(series)):
        s = series[i]*k + s*(1-k)
        out[i] = s
    return out


def rsi(series: List[float], n: int = 14) -> List[Optional[float]]:
    out = [None]*len(series)
    gains, losses = 0.0, 0.0
    for i in range(1, len(series)):
        ch = series[i] - series[i-1]
        gains += max(ch, 0.0); losses += max(-ch, 0.0)
        if i >= n:
            prev = series[i-n]
            # roll window
            ch0 = series[i-n+1] - prev
            gains -= max(ch0, 0.0); losses -= max(-ch0, 0.0)
        if i >= n:
            rs = (gains/n) / ((losses/n) if losses != 0 else 1e-9)
            out[i] = 100 - 100/(1+rs)
    return out


def atr(high: List[float], low: List[float], close: List[float], n: int = 14) -> List[Optional[float]]:
    tr: List[float] = [0.0]*len(close)
    for i in range(len(close)):
        if i == 0:
            tr[i] = high[i] - low[i]
        else:
            tr[i] = max(high[i]-low[i], abs(high[i]-close[i-1]), abs(low[i]-close[i-1]))
    return sma(tr, n)


def bbands(series: List[float], n: int = 20, mult: float = 2.0) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    ma = sma(series, n)
    up, dn = [None]*len(series), [None]*len(series)
    for i in range(len(series)):
        if i < n-1 or ma[i] is None:
            continue
        win = series[i-n+1:i+1]
        m = ma[i]
        var = sum((x-m)**2 for x in win)/n
        sd = var**0.5
        up[i] = m + mult*sd
        dn[i] = m - mult*sd
    return ma, up, dn


def macd(series: List[float], fast: int = 12, slow: int = 26, sig: int = 9) -> Tuple[List[Optional[float]], List[Optional[float]], List[Optional[float]]]:
    efast = ema(series, fast)
    eslow = ema(series, slow)
    macd_line = [None if (efast[i] is None or eslow[i] is None) else (efast[i]-eslow[i]) for i in range(len(series))]
    signal = ema([x if x is not None else 0.0 for x in macd_line], sig)
    hist = [None if (macd_line[i] is None or signal[i] is None) else (macd_line[i]-signal[i]) for i in range(len(series))]
    return macd_line, signal, hist


def compute_indicators(rows: List[tuple], need: List[str]) -> Dict[str, List[Optional[float]]]:
    """need z. B.: ['SMA(10)','SMA(20)','RSI(14)','ATR(14)','BB(20,2)','MACD(12,26,9)']"""
    need = [s.replace(" ", "").upper() for s in need]
    o = _col(rows, 1); h = _col(rows, 2); l = _col(rows, 3); c = _col(rows, 4)
    out: Dict[str, List[Optional[float]]] = {}
    for token in need:
        if token.startswith("SMA("):
            n = int(token[4:-1]); out[f"SMA{n}"] = sma(c, n)
        elif token.startswith("EMA("):
            n = int(token[4:-1]); out[f"EMA{n}"] = ema(c, n)
        elif token.startswith("RSI("):
            n = int(token[4:-1]); out[f"RSI{n}"] = rsi(c, n)
        elif token.startswith("ATR("):
            n = int(token[4:-1]); out[f"ATR{n}"] = atr(h, l, c, n)
        elif token.startswith("BB("):
            inside = token[3:-1]
            parts = inside.split(",")
            n = int(parts[0]); mult = float(parts[1]) if len(parts) > 1 else 2.0
            ma, up, dn = bbands(c, n, mult)
            out[f"BB_MA{n}_{mult}"] = ma
            out[f"BB_UP{n}_{mult}"] = up
            out[f"BB_DN{n}_{mult}"] = dn
        elif token.startswith("MACD("):
            a,b,s = [int(x) for x in token[5:-1].split(",")]
            m, sig, hist = macd(c, a, b, s)
            out[f"MACD_{a}_{b}_{s}"] = m
            out[f"MACDSIG_{a}_{b}_{s}"] = sig
            out[f"MACDHIST_{a}_{b}_{s}"] = hist
    return out

