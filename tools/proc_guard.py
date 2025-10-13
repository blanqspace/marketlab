#!/usr/bin/env python3
import argparse, os, sys, time, subprocess, signal, pathlib, warnings, shlex
from datetime import datetime, UTC


warnings.filterwarnings("ignore", category=DeprecationWarning)


def rotate(path: pathlib.Path, keep=5):
    if path.exists():
        for i in range(keep - 1, 0, -1):
            src = path.with_suffix(path.suffix + f".{i}")
            dst = path.with_suffix(path.suffix + f".{i+1}")
            if src.exists():
                src.rename(dst)
        path.rename(path.with_suffix(path.suffix + ".1"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--stopfile", default="runtime/stop")
    ap.add_argument("--max_backoff", type=int, default=60)
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    # strip one or more leading "--" separators, if present
    while a.cmd and a.cmd[0] == "--":
        a.cmd = a.cmd[1:]
    if not a.cmd:
        print("no command", file=sys.stderr)
        sys.exit(2)

    logs = pathlib.Path("logs")
    logs.mkdir(parents=True, exist_ok=True)
    logfile = logs / f"{a.name}.log"

    backoff = 1
    while True:
        if os.path.exists(a.stopfile):
            # Stopfile present → clean exit without restart
            sys.exit(0)

        rotate(logfile)
        with open(logfile, "w", buffering=1, encoding="utf-8") as lf:
            ts = datetime.now(UTC).isoformat()
            lf.write(f"[{ts}] start {a.name}: {shlex.join(a.cmd)}\n")
            try:
                # Launch child in its own process group
                proc = subprocess.Popen(
                    a.cmd,
                    stdout=lf,
                    stderr=lf,
                    preexec_fn=os.setsid,
                )

                def forward(sig, _):
                    try:
                        os.killpg(proc.pid, sig)
                    except Exception:
                        pass

                signal.signal(signal.SIGINT, forward)
                signal.signal(signal.SIGTERM, forward)

                code = proc.wait()
                lf.write(f"[{datetime.now(UTC).isoformat()}] exit code={code}\n")
            except Exception as e:
                lf.write(f"[{datetime.now(UTC).isoformat()}] guard error: {e}\n")
                code = -1

        if code == 0:
            # Normal exit → do not restart
            sys.exit(0)

        time.sleep(backoff)
        backoff = min(a.max_backoff, backoff * 2)


if __name__ == "__main__":
    main()
