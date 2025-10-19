#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import pathlib
import signal
import subprocess
import time
from typing import Callable, Dict, List, Optional

BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
REPORT_DIR = pathlib.Path(os.environ.get("REPORT_DIR", "runtime/reports"))
REPORT_DIR.mkdir(parents=True, exist_ok=True)
SLACK_PID_FILE = REPORT_DIR / "slack.pid"
WORKER_PID_FILE = REPORT_DIR / "confirm_worker.pid"


def _env_with_path() -> Dict[str, str]:
    env = os.environ.copy()
    current = env.get("PYTHONPATH")
    bits: List[str] = ["src"]
    if current:
        bits.append(current)
    env["PYTHONPATH"] = os.pathsep.join(bits)
    return env


report: Dict[str, object] = {
    "mode": "simulation"
    if os.environ.get("SLACK_SIMULATION", "").lower() in {"1", "true", "yes"}
    else "real",
    "steps": [],
    "pass": True,
}
order_token = os.environ.get("SIM_ORDER_TOKEN") or f"ORD{int(time.time())}"
report["order_token"] = order_token


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_process(pid_file: pathlib.Path) -> None:
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
    except ValueError:
        pid_file.unlink(missing_ok=True)
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            break
        except PermissionError:
            break
        time.sleep(0.3)
        if not _pid_alive(pid):
            break
    pid_file.unlink(missing_ok=True)


def _record_step(
    name: str,
    cmd: str,
    rc: int,
    duration: float,
    out: str = "",
    err: str = "",
) -> None:
    report["steps"].append(
        {
            "name": name,
            "cmd": cmd,
            "rc": rc,
            "duration": round(duration, 3),
            "out": out,
            "err": err,
        }
    )
    report["pass"] &= rc == 0


def start_background(name: str, args: List[str], log_path: pathlib.Path, pid_file: pathlib.Path) -> None:
    _kill_process(pid_file)
    env = _env_with_path()
    started = time.time()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(log_path, "a", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                args,
                cwd=str(BASE_DIR),
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
            )
    except Exception as exc:
        _record_step(
            name,
            " ".join(args) + " &",
            1,
            time.time() - started,
            err=str(exc),
        )
        return
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(2)
    alive = _pid_alive(proc.pid)
    rc = 0 if alive else (proc.poll() or 1)
    err = "" if alive else f"process exited with code {rc}"
    _record_step(
        name,
        " ".join(args) + " &",
        rc,
        time.time() - started,
        err=err,
    )


def step(
    name: str,
    cmd: str,
    on_success: Optional[Callable[[subprocess.CompletedProcess[str]], None]] = None,
) -> bool:
    env = _env_with_path()
    started = time.time()
    proc = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(BASE_DIR),
        env=env,
    )
    finished = time.time()
    ok = proc.returncode == 0
    out = proc.stdout.strip()
    err = proc.stderr.strip()
    _record_step(name, cmd, proc.returncode, finished - started, out=out, err=err)
    if ok and on_success:
        try:
            on_success(proc)
        except Exception as exc:
            _record_step(
                f"{name}_post",
                f"{cmd} [post]",
                1,
                0.0,
                err=f"post-step failed: {exc}",
            )
            ok = False
    return ok


simulation = report["mode"] == "simulation"
sim_path = REPORT_DIR / "slack_sim.jsonl"
if simulation and sim_path.exists():
    sim_path.unlink()

start_background(
    "start_slack",
    ["python", "-m", "marketlab", "slack"],
    pathlib.Path("/tmp/slack_bot.log"),
    SLACK_PID_FILE,
)
step(
    "selftest",
    "python -m marketlab slack:selftest --token SIM1 --symbol AAPL --qty 1 --px 100",
)
start_background(
    "start_worker",
    ["python", "-m", "marketlab", "worker:confirm"],
    pathlib.Path("/tmp/confirm_worker.log"),
    WORKER_PID_FILE,
)
step(
    "enqueue_cli",
    f"MARKETLAB_ACTOR=cli:sim python -m marketlab ctl enqueue --cmd orders.confirm --args '{{\"token\":\"{order_token}\"}}' --source cli",
)
step(
    "enqueue_slack",
    f"MARKETLAB_ACTOR=slack:sim python -m marketlab ctl enqueue --cmd orders.confirm --args '{{\"token\":\"{order_token}\"}}' --source slack",
)
step(
    "tail_check",
    "python -m marketlab ctl tail --limit 40",
)

if simulation and sim_path.exists():
    try:
        with sim_path.open("r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        report["slack_sim_events"] = lines[-6:]
    except Exception as exc:
        report["slack_sim_error"] = f"{type(exc).__name__}: {exc}"
        report["pass"] = False


def _persist_pid_snapshot() -> None:
    state = {}
    if SLACK_PID_FILE.exists():
        state["slack_pid"] = SLACK_PID_FILE.read_text().strip()
    if WORKER_PID_FILE.exists():
        state["worker_pid"] = WORKER_PID_FILE.read_text().strip()
    if state:
        report["background"] = state

result_path = REPORT_DIR / "result.json"
_persist_pid_snapshot()
with result_path.open("w", encoding="utf-8") as handle:
    json.dump(report, handle, ensure_ascii=False, indent=2)

print(json.dumps(report, ensure_ascii=False, indent=2))
