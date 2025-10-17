#!/usr/bin/env python3
import argparse, os, sys, time, subprocess, signal, pathlib, warnings, shlex
from datetime import datetime, UTC

warnings.filterwarnings("ignore", category=DeprecationWarning)


def rotate(path: pathlib.Path):
    for i in range(5, 0, -1):
        src = path.parent / f"{path.stem}.{i-1 if i>1 else ''}{path.suffix}"
        dst = path.parent / f"{path.stem}.{i}{path.suffix}"
        if src.exists():
            src.rename(dst)
    if path.exists():
        path.rename(path.parent / f"{path.stem}.1{path.suffix}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--keepalive", action="store_true")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()

    # Entferne führende "--"
    while a.cmd and a.cmd[0] == "--":
        a.cmd = a.cmd[1:]
    if not a.cmd:
        print("no command", file=sys.stderr)
        sys.exit(2)

    logfile = pathlib.Path("logs") / f"{a.name}.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)
    backoff = 3

    while True:
        rotate(logfile)
        with open(logfile, "w", buffering=1, encoding="utf-8") as lf:
            ts = datetime.now(UTC).isoformat()
            lf.write(f"[{ts}] start {a.name}: {shlex.join(a.cmd)}\n")
            try:
                proc = subprocess.Popen(a.cmd, stdout=lf, stderr=lf, preexec_fn=os.setsid)
                rc = proc.wait()
            except Exception as e:
                ts = datetime.now(UTC).isoformat()
                lf.write(f"[{ts}] guard error: {e}\n")
                rc = -1
        if rc == 0 and not a.keepalive:
            break
        time.sleep(backoff)


if __name__ == "__main__":
    main()
