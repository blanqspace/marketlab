
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    ROOT / "pyproject.toml",
    ROOT / "README.md",
    ROOT / "src/marketlab/__init__.py",
    ROOT / "src/marketlab/__main__.py",
    ROOT / "src/marketlab/cli.py",
    ROOT / "src/marketlab/settings.py",
    ROOT / "src/marketlab/utils/logging.py",
    ROOT / "src/marketlab/data/__init__.py",
    ROOT / "src/marketlab/data/adapters.py",
]

FAIL = 0

def check_files() -> None:
    global FAIL
    for p in REQUIRED:
        if not p.exists():
            print(f"[FAIL] missing: {p}")
            FAIL += 1
        elif p.stat().st_size == 0:
            print(f"[FAIL] empty file: {p}")
            FAIL += 1
        else:
            print(f"[OK] {p.relative_to(ROOT)}")


def check_import() -> None:
    global FAIL
    try:
        __import__("marketlab")
        print("[OK] import marketlab")
    except Exception as e:
        print(f"[FAIL] import marketlab: {e}")
        FAIL += 1


def check_cli_help() -> None:
    global FAIL
    cmds = [
        [sys.executable, "-m", "marketlab", "--help"],
        [sys.executable, "-m", "marketlab", "backtest", "--help"],
        [sys.executable, "-m", "marketlab", "replay", "--help"],
        [sys.executable, "-m", "marketlab", "paper", "--help"],
        [sys.executable, "-m", "marketlab", "live", "--help"],
    ]
    for c in cmds:
        try:
            out = subprocess.run(c, cwd=ROOT, capture_output=True, text=True, timeout=20)
            if out.returncode != 0:
                raise RuntimeError(out.stderr.strip() or out.stdout.strip())
            print(f"[OK] {' '.join(c[2:])}")
        except Exception as e:
            print(f"[FAIL] {' '.join(c[2:])}: {e}")
            FAIL += 1


def check_env_parsing() -> None:
    global FAIL
    env = os.environ.copy()
    env.setdefault("ENV_MODE", "DEV")
    env.setdefault("TWS_HOST", "127.0.0.1")
    env.setdefault("TWS_PORT", "7497")
    env.setdefault("TELEGRAM_ENABLED", "false")
    cmd = [
        sys.executable,
        "-c",
        (
            "from marketlab.settings import settings; "
            "print(settings.env_mode, settings.ibkr.host, settings.ibkr.port, settings.telegram.enabled)"
        ),
    ]
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=15, env=env)
        if out.returncode != 0:
            raise RuntimeError(out.stderr.strip())
        print(f"[OK] env parsing -> {out.stdout.strip()}")
    except Exception as e:
        print(f"[FAIL] env parsing: {e}")
        FAIL += 1


if __name__ == "__main__":
    check_files()
    check_import()
    check_cli_help()
    check_env_parsing()
    if FAIL:
        print(f"EXIT with {FAIL} failure(s)")
        sys.exit(1)
    print("ALL CHECKS PASSED")
