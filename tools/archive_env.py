#!/usr/bin/env python3
from __future__ import annotations

import datetime as _dt
import os
from pathlib import Path
from typing import List


ENV_PATH = Path(".env")
ARCHIVE_PATH = Path(".env.archive")
TELEGRAM_PREFIX = "TELEGRAM_"


def _read_env_lines() -> List[str]:
    if not ENV_PATH.exists():
        return []
    return ENV_PATH.read_text(encoding="utf-8").splitlines()


def _write_env_lines(lines: List[str]) -> None:
    ENV_PATH.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def archive_telegram_keys() -> None:
    lines = _read_env_lines()
    if not lines:
        print(".env nicht gefunden – keine Änderungen vorgenommen.")
        return

    kept: List[str] = []
    archived: List[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            kept.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key.startswith(TELEGRAM_PREFIX):
            archived.append(line)
        else:
            kept.append(line)

    # ensure TELEGRAM_ENABLED=0 present exactly once
    kept = [ln for ln in kept if not ln.strip().startswith("TELEGRAM_ENABLED=")]
    kept.append("TELEGRAM_ENABLED=0")

    if archived:
        ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        timestamp = _dt.datetime.utcnow().isoformat(timespec="seconds")
        with ARCHIVE_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"# Archived Telegram keys {timestamp} UTC\n")
            for entry in archived:
                fh.write(entry.rstrip() + "\n")
        print(f"{len(archived)} TELEGRAM_* Einträge nach .env.archive verschoben.")
    else:
        print("Keine TELEGRAM_* Einträge gefunden – Archiv unverändert.")

    _write_env_lines(kept)
    print("TELEGRAM_ENABLED=0 in .env gesetzt.")


def main() -> None:
    if os.getenv("TELEGRAM_ENABLED") and os.environ["TELEGRAM_ENABLED"] != "0":
        os.environ["TELEGRAM_ENABLED"] = "0"
    archive_telegram_keys()


if __name__ == "__main__":
    main()
