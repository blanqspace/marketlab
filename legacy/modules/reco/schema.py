# modules/reco/schema.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def signal_id(symbol: str, timeframe: str, strategy_id: str) -> str:
    t = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{symbol}_{timeframe.replace(' ', '')}_{strategy_id}_{t}"


@dataclass
class EntryPlan:
    order_type: str           # MKT | LMT | STP | STOP_LIMIT
    tif: str = "DAY"
    stop: Optional[float] = None
    limit: Optional[float] = None
    valid_until: Optional[str] = None


@dataclass
class RiskBlock:
    atr: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    suggested_qty: Optional[float] = None
    max_risk_cash: Optional[float] = None


@dataclass
class DataInfo:
    bars: int
    gaps: int
    source: str
    fresh: bool


@dataclass
class BacktestInfo:
    lookup: Optional[str] = None
    winrate: Optional[float] = None
    trades: Optional[int] = None
    sharpe: Optional[float] = None


@dataclass
class Signal:
    id: str
    ts: str
    symbol: str
    asset: str
    timeframe: str
    lookback_bars: int
    price_ref: float
    side: str                     # BUY | SELL | HOLD | FLAT
    strategy_id: str
    confidence: Optional[float]
    reasons: List[str]
    entry_plan: EntryPlan
    risk: RiskBlock
    data: DataInfo
    backtest: Optional[BacktestInfo] = None

    def to_jsonable(self) -> Dict[str, Any]:
        d = asdict(self)
        return d

