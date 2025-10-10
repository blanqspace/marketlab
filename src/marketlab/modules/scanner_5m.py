"""MarketLab 5m/2m Scanner.

Functions:
- scan_symbols: Load OHLCV bars via CSVAdapter and compute RSI-14,
  SMA-20, VMA-20 with simple rolling means; derive BUY/SELL/None signals.
- save_signals: Persist signals to CSV under reports/ (UTC timestamps).

Notes:
- Expects columns: time, open, high, low, close, volume (UTC timestamps).
- Drops warm-up rows to avoid NaNs in indicators.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
import logging
import pandas as pd

from ..data.adapters import CSVAdapter

log = logging.getLogger("marketlab.modules.scanner_5m")


def _rsi14(close: pd.Series, period: int = 14) -> pd.Series:
    # Simple RSI using rolling means of gains/losses
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi


def scan_symbols(symbols: list[str], timeframe: str = "5m") -> pd.DataFrame:
    """Scan multiple symbols for simple RSI/SMA signals.

    Parameters
    - symbols: list of ticker symbols
    - timeframe: "5m" (default) or "2m" supported

    Returns
    - DataFrame with columns: time, symbol, close, rsi14, sma20, vma20, signal
    """
    tf = timeframe.lower()
    if tf not in {"5m", "2m"}:
        raise ValueError("timeframe must be one of: 5m, 2m")

    adapter = CSVAdapter(base_dir="data")
    frames: list[pd.DataFrame] = []

    for sym in symbols:
        df = adapter.load_bars(sym, tf)
        if df is None or df.empty:
            log.warning("No data for %s %s", sym, tf)
            continue

        df = df.copy()
        # Indicators
        df["rsi14"] = _rsi14(df["close"])  # may produce NaN in warm-up
        df["sma20"] = df["close"].rolling(window=20, min_periods=20).mean()
        df["vma20"] = df["volume"].rolling(window=20, min_periods=20).mean()

        # Drop warm-up rows
        df = df.dropna(subset=["rsi14", "sma20", "vma20"]).reset_index(drop=True)

        # Signals
        cond_buy = (df["rsi14"] < 30) & (df["close"] > df["sma20"])
        cond_sell = (df["rsi14"] > 70) & (df["close"] < df["sma20"])
        signal = pd.Series("None", index=df.index, dtype="string")
        signal = signal.mask(cond_buy, "BUY").mask(cond_sell, "SELL")

        out = pd.DataFrame({
            "time": pd.to_datetime(df["time"], utc=True),
            "symbol": sym.upper(),
            "close": df["close"].astype(float),
            "rsi14": df["rsi14"].astype(float),
            "sma20": df["sma20"].astype(float),
            "vma20": df["vma20"].astype(float),
            "signal": signal.astype(str),
        })
        frames.append(out)

        # Log per-symbol summary
        buys = int((signal == "BUY").sum())
        sells = int((signal == "SELL").sum())
        nones = int((signal == "None").sum())
        log.info({"event": "scan.summary", "symbol": sym, "tf": tf, "BUY": buys, "SELL": sells, "None": nones})

    if not frames:
        return pd.DataFrame(columns=["time", "symbol", "close", "rsi14", "sma20", "vma20", "signal"])  # empty

    all_df = pd.concat(frames, axis=0, ignore_index=True)
    # Sort by time then symbol for nice output
    all_df = all_df.sort_values(["time", "symbol"]).reset_index(drop=True)
    return all_df


def save_signals(df: pd.DataFrame, out_path: str = "reports/signals_5m.csv") -> None:
    """Save scanner output to CSV. Ensures parent directory exists.

    - df: DataFrame from scan_symbols
    - out_path: file path under reports/
    """
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    # Aggregate summary for logs
    if not df.empty:
        buys = int((df["signal"] == "BUY").sum())
        sells = int((df["signal"] == "SELL").sum())
        nones = int((df["signal"] == "None").sum())
        log.info({"event": "scan.saved", "dst": str(path), "BUY": buys, "SELL": sells, "None": nones})

