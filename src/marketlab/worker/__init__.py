from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Sequence

from src.marketlab.bootstrap.env import load_env
from src.marketlab.daemon.worker import Worker
from src.marketlab.ipc import bus


def _stop_path() -> Path:
    root = Path(__file__).resolve().parents[3]
    stop_file = root / "runtime" / "stop"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    return stop_file


def _log_start() -> None:
    ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    print(f"[worker] start {ts}", flush=True)


def _log_stop() -> None:
    print("worker.stop", flush=True)


def _log_error(exc: Exception) -> None:
    print(f"worker.error {type(exc).__name__}: {exc}", flush=True)


def _prepare_env() -> str:
    settings = load_env(mirror=True)
    db_path = Path(settings.ipc_db).resolve()
    os.environ[bus.DB_ENV] = str(db_path)
    bus.bus_init()
    return str(db_path)


def _process_once(worker: Worker) -> None:
    try:
        worker.process_one()
    except Exception as exc:  # pragma: no cover
        _log_error(exc)


def run_daemon(interval: float) -> None:
    _prepare_env()
    stop_file = _stop_path()
    running = True

    def _sig_handler(*_: object) -> None:
        nonlocal running
        running = False

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except Exception:
        pass

    _log_start()
    worker = Worker()
    while running:
        if stop_file.exists():
            running = False
            break
        _process_once(worker)
        if stop_file.exists():
            running = False
            break
        deadline = time.time() + interval
        while running and time.time() < deadline:
            if stop_file.exists():
                running = False
                break
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.1, remaining))
    _log_stop()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="marketlab.worker")
    parser.add_argument("--interval", type=float, default=1.0, help="Loop sleep interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Process a single bus command and exit.")
    args = parser.parse_args(argv)

    interval = max(float(args.interval), 0.05)

    if args.once:
        _prepare_env()
        _log_start()
        worker = Worker()
        _process_once(worker)
        _log_stop()
        return 0

    run_daemon(interval=interval)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
