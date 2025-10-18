#!/usr/bin/env python3
"""Lightweight process guard with graceful signal handling."""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, IO, Sequence

warnings.filterwarnings("ignore", category=DeprecationWarning)


def rotate(path: Path) -> None:
    """Rotate log file, keeping a handful of history files."""
    for i in range(5, 0, -1):
        src = path.parent / f"{path.stem}.{i - 1 if i > 1 else ''}{path.suffix}"
        dst = path.parent / f"{path.stem}.{i}{path.suffix}"
        if src.exists():
            src.rename(dst)
    if path.exists():
        path.rename(path.parent / f"{path.stem}.1{path.suffix}")


class ProcGuard:
    """Run a command, forward signals, and restart when required."""

    def __init__(
        self,
        name: str,
        cmd: Sequence[str],
        *,
        keepalive: bool = False,
        logfile: Path | None = None,
        backoff: float = 3.0,
        sigint_timeout: float | None = None,
        sigterm_timeout: float | None = None,
        check_interval: float = 1.0,
        health_check: Callable[[], bool] | None = None,
        popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        if not cmd:
            raise ValueError("command required")
        self.name = name
        self.cmd = list(cmd)
        self.keepalive = keepalive
        self.logfile = logfile or (Path("logs") / f"{name}.log")
        self.backoff = float(backoff)
        self.sigint_timeout = (
            float(sigint_timeout)
            if sigint_timeout is not None
            else float(
                os.getenv(
                    "PROC_GUARD_SIGINT_TIMEOUT", os.getenv("PROC_GUARD_SHUTDOWN_TIMEOUT", "5")
                )
            )
        )
        self.sigterm_timeout = (
            float(sigterm_timeout)
            if sigterm_timeout is not None
            else float(
                os.getenv(
                    "PROC_GUARD_SIGTERM_TIMEOUT", os.getenv("PROC_GUARD_SHUTDOWN_TIMEOUT", "5")
                )
            )
        )
        self.check_interval = max(float(check_interval), 0.1)
        self.health_check = health_check
        self._popen_factory = popen_factory
        self._sleep = sleep_fn

        self._proc: subprocess.Popen[Any] | None = None
        self._log_handle: IO[str] | None = None
        self._stop = False
        self._phase = "running"
        self._deadline = float("inf")
        self._next_health_check = time.monotonic() + self.check_interval

    # ------------------------------------------------------------------ utils
    def _log(self, message: str) -> None:
        if self._log_handle is None:
            return
        self._log_handle.write(f"[{datetime.now(UTC).isoformat()}] {message}\n")
        self._log_handle.flush()

    def _spawn(self) -> bool:
        self.logfile.parent.mkdir(parents=True, exist_ok=True)
        rotate(self.logfile)
        try:
            self._log_handle = self.logfile.open("w", buffering=1, encoding="utf-8")
        except Exception:  # pragma: no cover - fallback when filesystem unhappy
            self._log_handle = sys.stdout
        self._log(f"start {self.name}: {shlex.join(self.cmd)}")
        try:
            self._proc = self._popen_factory(
                self.cmd,
                stdout=self._log_handle,
                stderr=self._log_handle,
                preexec_fn=os.setsid,
            )
        except Exception as exc:  # pragma: no cover - spawn failures are rare
            self._log(f"guard error: {exc}")
            self._cleanup()
            self._proc = None
            return False
        self._stop = False
        self._phase = "running"
        self._deadline = float("inf")
        self._next_health_check = time.monotonic() + self.check_interval
        return True

    def _cleanup(self) -> None:
        if self._log_handle and self._log_handle is not sys.stdout:
            try:
                self._log_handle.close()
            except Exception:
                pass
        self._log_handle = None

    def _send_signal(self, sig: int) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            pass

    def _begin_stop(self, phase: str, sig: int, timeout: float | None, reason: str) -> None:
        if self._phase == "sigkill":
            return
        self._stop = True
        self._phase = phase
        self._log(reason)
        self._send_signal(sig)
        self._deadline = time.monotonic() + timeout if timeout and timeout > 0 else time.monotonic()

    def _tick(self) -> int | None:
        proc = self._proc
        if proc is None:
            return 0
        rc = proc.poll()
        if rc is not None:
            return rc

        now = time.monotonic()
        if not self._stop and self.health_check and now >= self._next_health_check:
            self._next_health_check = now + self.check_interval
            ok = True
            try:
                ok = bool(self.health_check())
            except Exception as exc:  # pragma: no cover - defensive
                ok = False
                self._log(f"health check error: {exc}")
            if not ok:
                self._begin_stop(
                    "sigint", signal.SIGINT, self.sigint_timeout, "health check failed"
                )

        if self._stop and now >= self._deadline:
            if self._phase == "sigint":
                self._begin_stop(
                    "sigterm", signal.SIGTERM, self.sigterm_timeout, "escalating to SIGTERM"
                )
            elif self._phase == "sigterm":
                self._phase = "sigkill"
                self._log("escalating to SIGKILL")
                self._send_signal(signal.SIGKILL)
                self._deadline = float("inf")

        return None

    # ----------------------------------------------------------------- runtime
    def install_signal_handlers(self) -> None:
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)

    def _handle_signal(self, signum: int, frame: object | None) -> None:
        del frame
        if signum == signal.SIGINT:
            self._begin_stop("sigint", signal.SIGINT, self.sigint_timeout, "received SIGINT")
        else:
            self._begin_stop("sigterm", signal.SIGTERM, self.sigterm_timeout, "received SIGTERM")

    def run_once(self) -> int:
        if not self._spawn():
            return -1
        try:
            while True:
                rc = self._tick()
                if rc is not None:
                    return rc
                self._sleep(0.2)
        finally:
            self._cleanup()

    def run(self) -> int:
        self.install_signal_handlers()
        while True:
            rc = self.run_once()
            if not self.keepalive or rc != 0:
                return rc
            self._sleep(self.backoff)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proc_guard")
    parser.add_argument("--name", required=True)
    parser.add_argument("--keepalive", action="store_true")
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    cmd = list(args.cmd)
    while cmd and cmd[0] == "--":
        cmd.pop(0)
    if not cmd:
        print("no command", file=sys.stderr)
        return 2
    guard = ProcGuard(args.name, cmd, keepalive=args.keepalive)
    return guard.run()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
