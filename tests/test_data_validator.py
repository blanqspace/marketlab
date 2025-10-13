from __future__ import annotations
from pathlib import Path
import pandas as pd
import numpy as np

from marketlab.utils.data_validator import validate_dataset


def _write_csv(fp: Path, rows):
    df = pd.DataFrame(rows)
    df.to_csv(fp, index=False)


def test_validator_ok(tmp_path):
    fp = tmp_path / "AAPL_15m.csv"
    base = pd.date_range("2024-01-01 00:00", periods=10, freq="15min", tz="UTC")
    rows = [
        {"time": t.isoformat(), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
        for t in base
    ]
    _write_csv(fp, rows)
    res = validate_dataset(fp, "AAPL", "15m")
    assert res["status"] == "ok"
    assert res["rows"] == 10


def test_validator_warn_with_gap(tmp_path):
    fp = tmp_path / "AAPL_15m.csv"
    base = pd.date_range("2024-01-01 00:00", periods=10, freq="15min", tz="UTC")
    # drop one timestamp to create gap
    base = base.delete(5)
    rows = [
        {"time": t.isoformat(), "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}
        for t in base
    ]
    _write_csv(fp, rows)
    res = validate_dataset(fp, "AAPL", "15m")
    assert res["status"] in ("ok", "warn")
    assert res["gaps"] >= 1


def test_validator_fail_on_schema(tmp_path):
    fp = tmp_path / "AAPL_15m.csv"
    rows = [{"ts": "2024-01-01T00:00:00Z", "close": 1.0}]
    _write_csv(fp, rows)
    res = validate_dataset(fp, "AAPL", "15m")
    assert res["status"] == "fail"

