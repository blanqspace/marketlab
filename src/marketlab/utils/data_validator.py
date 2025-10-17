from __future__ import annotations

from pathlib import Path

import pandas as pd

_REQ = ["time", "open", "high", "low", "close", "volume"]


def _freq_from_timeframe(tf: str) -> str:
    tf = tf.strip().lower()
    if tf.endswith("m"):
        return f"{int(tf[:-1])}min"
    if tf.endswith("h"):
        return f"{int(tf[:-1])}H"
    if tf.endswith("d"):
        return f"{int(tf[:-1])}D"
    # default minute
    return "1min"


def validate_dataset(path: Path, symbol: str, timeframe: str) -> dict:
    out: dict = {
        "symbol": symbol,
        "timeframe": timeframe,
        "rows": 0,
        "start": None,
        "end": None,
        "dupes": 0,
        "gaps": 0,
        "nan_rows": 0,
        "sorted": True,
        "status": "ok",
    }
    if not Path(path).exists():
        out["status"] = "fail"
        return out
    df = pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path)
    # schema
    missing = [c for c in _REQ if c not in df.columns]
    if missing:
        out["status"] = "fail"
        return out
    # parse time
    ts = pd.to_datetime(df["time"], utc=True, errors="coerce")
    nan_rows = int(ts.isna().sum())
    df = df.loc[~ts.isna()].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    out["nan_rows"] = nan_rows
    out["rows"] = int(len(df))
    if out["rows"] == 0:
        out["status"] = "fail"
        return out
    # ordering
    sorted_ok = df["time"].is_monotonic_increasing
    out["sorted"] = bool(sorted_ok)
    if not sorted_ok:
        df = df.sort_values("time")
    out["start"] = df["time"].iloc[0].isoformat()
    out["end"] = df["time"].iloc[-1].isoformat()
    # dupes
    dupes = int(df.duplicated(subset=["time"]).sum())
    out["dupes"] = dupes
    # gaps via expected delta check
    freq = _freq_from_timeframe(timeframe)
    idx = pd.DatetimeIndex(df["time"].values)
    deltas = idx.to_series().diff().iloc[1:]
    expected = pd.to_timedelta(freq)
    gaps = int((deltas != expected).sum())
    out["gaps"] = gaps
    # status
    status = "ok"
    if missing or nan_rows > 0 or not sorted_ok or dupes > 0 or gaps > 0:
        status = "warn"
    if missing or out["rows"] == 0:
        status = "fail"
    out["status"] = status
    return out
