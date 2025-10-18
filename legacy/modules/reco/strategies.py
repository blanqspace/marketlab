# modules/reco/strategies.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from .schema import Signal, EntryPlan, RiskBlock, DataInfo, signal_id


def _last2(arr):
    n = len(arr)
    return (arr[n-2] if n >= 2 else None, arr[n-1] if n >= 1 else None)


def _entry_from_cfg(side: str, price: float, cfg: Dict[str, Any]) -> EntryPlan:
    t = (cfg.get("type") or "MKT").upper()
    tif = (cfg.get("tif") or "DAY").upper()
    stop_ofs = float(cfg.get("stop_ofs_pct", 0.0))/100.0
    lmt_ofs  = float(cfg.get("limit_ofs_pct", 0.0))/100.0

    stop = limit = None
    if t in ("STP", "STOP", "STOP_LIMIT"):
        if side == "BUY":
            stop = price*(1+stop_ofs) if stop_ofs else price
        else:
            stop = price*(1-stop_ofs) if stop_ofs else price
    if t in ("LMT", "LIMIT", "STOP_LIMIT"):
        base = stop if (t == "STOP_LIMIT" and stop is not None) else price
        if side == "BUY":
            limit = base*(1+ lmt_ofs) if lmt_ofs else base
        else:
            limit = base*(1- lmt_ofs) if lmt_ofs else base

    return EntryPlan(order_type=("STOP_LIMIT" if t.replace("_"," ")=="STOP LIMIT" else t), tif=tif, stop=stop, limit=limit)


def _risk_from_cfg(side: str, price: float, atr_val: Optional[float], cfg: Dict[str, Any]) -> RiskBlock:
    sl_mult = float(cfg.get("sl_atr_mult", 0.0))
    tp_mult = float(cfg.get("tp_atr_mult", 0.0))
    qty     = cfg.get("qty")
    max_r   = cfg.get("max_risk_cash")
    sl = tp = None
    if atr_val is not None:
        if side == "BUY":
            sl = price - sl_mult*atr_val if sl_mult else None
            tp = price + tp_mult*atr_val if tp_mult else None
        else:
            sl = price + sl_mult*atr_val if sl_mult else None
            tp = price - tp_mult*atr_val if tp_mult else None
    return RiskBlock(atr=atr_val, stop_loss=sl, take_profit=tp, suggested_qty=qty, max_risk_cash=max_r)


def eval_strategies(
    symbol: str,
    asset: str,
    timeframe: str,
    rows: List[tuple],
    indicators: Dict[str, List[Optional[float]]],
    strategies_cfg: List[Dict[str, Any]],
    lookback_bars: int,
    data_info: DataInfo,
    price_ref: float
) -> List[Signal]:
    out: List[Signal] = []
    for sc in strategies_cfg:
        sid = sc["id"]
        rules: Dict[str, Any] = sc.get("rules", {})
        entry_cfg: Dict[str, Any] = sc.get("entry", {})
        risk_cfg: Dict[str, Any] = sc.get("risk", {})

        side: Optional[str] = None
        reasons: List[str] = []

        # Rule: cross: ["SMA10","SMA20"]  -> BUY on cross up, SELL on cross down
        cross = rules.get("cross")
        if cross and len(cross) == 2:
            a, b = cross[0].upper(), cross[1].upper()
            a_prev, a_last = _last2(indicators.get(a, []))
            b_prev, b_last = _last2(indicators.get(b, []))
            if all(x is not None for x in (a_prev, a_last, b_prev, b_last)):
                if a_prev <= b_prev and a_last > b_last:
                    side = side or "BUY"; reasons.append(f"{a}>{b} (Cross up)")
                if a_prev >= b_prev and a_last < b_last:
                    side = side or "SELL"; reasons.append(f"{a}<{b} (Cross down)")

        # Rule: rsi_lt / rsi_gt
        for k, v in rules.items():
            if isinstance(v, (int, float)) and k.upper().startswith("RSI"):
                src = k.upper()  # e.g. "RSI14"
                arr = indicators.get(src)
                if arr and arr[-1] is not None:
                    if "LT" in k.upper() and arr[-1] < float(v):
                        side = side or "BUY"; reasons.append(f"{src}<{v}")
                    if "GT" in k.upper() and arr[-1] > float(v):
                        side = side or "SELL"; reasons.append(f"{src}>{v}")

        if not side:
            continue  # keine Bedingungen erfüllt

        # Risiko/Entry
        atr_key = next((k for k in indicators.keys() if k.startswith("ATR")), None)
        atr_val = indicators.get(atr_key, [None])[-1] if atr_key else None
        entry = _entry_from_cfg(side, price_ref, entry_cfg)
        risk  = _risk_from_cfg(side, price_ref, atr_val, risk_cfg)

        sig = Signal(
            id=signal_id(symbol, timeframe, sid),
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            symbol=symbol,
            asset=asset,
            timeframe=timeframe,
            lookback_bars=lookback_bars,
            price_ref=price_ref,
            side=side,
            strategy_id=sid,
            confidence=sc.get("confidence", None),
            reasons=reasons,
            entry_plan=entry,
            risk=risk,
            data=data_info,
            backtest=None
        )
        out.append(sig)
    return out

