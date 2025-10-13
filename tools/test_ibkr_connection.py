import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

import pandas as pd
import pytest
from ib_insync import IB, Stock, util

pytestmark = [pytest.mark.ibkr, pytest.mark.network]

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4002
DEFAULT_CLIENT_ID = 7
DEFAULT_SYMBOL = "AAPL"
DEFAULT_DATA_DIR = Path("data")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


def resolve_parameters() -> tuple[str, int, int, str, Path]:
    host = os.getenv("TWS_HOST", DEFAULT_HOST)
    port = _env_int("TWS_PORT", DEFAULT_PORT)
    client_id = _env_int("IBKR_CLIENT_ID", DEFAULT_CLIENT_ID)
    symbol = os.getenv("TEST_SYMBOL", DEFAULT_SYMBOL)
    data_dir = Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR))
    return host, port, client_id, symbol, data_dir


def _print_header(host: str, port: int, client_id: int) -> None:
    line = "=" * 80
    print(line)
    print(f"IBKR connectivity test: host={host} port={port} client_id={client_id}")
    print(line)


def _log_accounts(ib: IB) -> None:
    accounts = ib.managedAccounts()
    print(f"Accounts: {accounts or 'none visible'}")


def _log_realtime_quote(ib: IB, contract: Stock) -> None:
    ticker = ib.reqMktData(contract)
    ib.sleep(3)
    print(f"Realtime {contract.symbol}: bid={ticker.bid}, ask={ticker.ask}, last={ticker.last}")
    ib.cancelMktData(contract)


def _log_bars(ib: IB, contract: Stock) -> None:
    bars = ib.reqHistoricalData(
        contract,
        endDateTime="",
        durationStr="1 D",
        barSizeSetting="1 min",
        whatToShow="TRADES",
        useRTH=True,
        formatDate=1,
    )
    if bars:
        df = util.df(bars)
        print(f"Historical bars received: {len(df)} rows")
        print(df.head(3))
    else:
        print("No historical bars returned.")


def _log_local_files(data_dir: Path) -> None:
    files: Sequence[Path] = list(data_dir.glob("*.csv")) + list(data_dir.glob("*.parquet"))
    if not files:
        print(f"No local CSV or Parquet files found in {data_dir.resolve()}.")
        return
    for file_path in files[:3]:
        if file_path.suffix == ".csv":
            df = pd.read_csv(file_path)
        else:
            df = pd.read_parquet(file_path)
        print(f"Loaded {file_path.name}: {len(df)} rows, columns={list(df.columns)[:6]}")


def run_ibkr_check(host: str, port: int, client_id: int, symbol: str, data_dir: Path) -> int:
    _print_header(host, port, client_id)
    ib = IB()
    try:
        ib.connect(host, port, clientId=client_id, timeout=10)
        print("Connection established.")
    except Exception as exc:  # pragma: no cover - network failure path
        print(f"Connection failed: {exc}", file=sys.stderr)
        return 1

    status = 0

    try:
        try:
            _log_accounts(ib)
        except Exception as exc:  # pragma: no cover - network failure path
            status = 1
            print(f"Account query failed: {exc}", file=sys.stderr)

        contract = Stock(symbol, "SMART", "USD")

        try:
            _log_realtime_quote(ib, contract)
        except Exception as exc:  # pragma: no cover - network failure path
            status = 1
            print(f"Realtime quote failed: {exc}", file=sys.stderr)

        try:
            _log_bars(ib, contract)
        except Exception as exc:  # pragma: no cover - network failure path
            status = 1
            print(f"Historical data failed: {exc}", file=sys.stderr)

        try:
            _log_local_files(data_dir)
        except Exception as exc:  # pragma: no cover - local file failure path
            status = 1
            print(f"Local file import failed: {exc}", file=sys.stderr)
    finally:
        ib.disconnect()
        print("Disconnected from IBKR.")
        print("=" * 80)

    return status


def test_ibkr_connection():
    host, port, client_id, symbol, data_dir = resolve_parameters()
    assert (
        run_ibkr_check(host, port, client_id, symbol, data_dir) == 0
    ), "IBKR connectivity check reported failures."


def main() -> int:
    parser = argparse.ArgumentParser(description="Run IBKR connectivity diagnostics.")
    parser.add_argument("--host", default=os.getenv("TWS_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=_env_int("TWS_PORT", DEFAULT_PORT))
    parser.add_argument(
        "--client-id", type=int, default=_env_int("IBKR_CLIENT_ID", DEFAULT_CLIENT_ID)
    )
    parser.add_argument("--symbol", default=os.getenv("TEST_SYMBOL", DEFAULT_SYMBOL))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("DATA_DIR", DEFAULT_DATA_DIR)),
    )
    args = parser.parse_args()
    return run_ibkr_check(args.host, args.port, args.client_id, args.symbol, args.data_dir)


if __name__ == "__main__":
    sys.exit(main())
