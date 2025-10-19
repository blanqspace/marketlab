#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import time
from pathlib import Path
from typing import List

ENV_PATH = Path(os.environ.get("MARKETLAB_ENV", ".env"))
BACKUP_DIR = Path(os.environ.get("MARKETLAB_ENV_BACKUPS", "runtime/env_backups"))


def _ensure() -> None:
    ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    if not ENV_PATH.exists():
        ENV_PATH.touch()


def _backup_env() -> None:
    ts = time.strftime("%Y%m%d-%H%M%S")
    base = f"{ENV_PATH.name}.{ts}.bak"
    backup_path = BACKUP_DIR / base
    counter = 1
    while backup_path.exists():
        backup_path = BACKUP_DIR / f"{ENV_PATH.name}.{ts}.{counter}.bak"
        counter += 1
    shutil.copy2(ENV_PATH, backup_path)


def _serialize_lines(lines: List[str]) -> str:
    return ("\n".join(lines)).rstrip() + "\n"


def set_key(key: str, val: str) -> None:
    _ensure()
    _backup_env()
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*)([^\n#]*?)(\s*(#.*))?$")
    with ENV_PATH.open("r", encoding="utf-8") as fh:
        raw_lines = fh.read().splitlines()
    updated = False
    new_lines: List[str] = []
    for line in raw_lines:
        match = pattern.match(line)
        if match:
            prefix = match.group(1)
            comment = match.group(3) or ""
            new_line = f"{prefix}{val}{comment}"
            new_lines.append(new_line)
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        new_lines.append(f"{key}={val}")
    ENV_PATH.write_text(_serialize_lines(new_lines), encoding="utf-8")


def get_key(key: str, default: str = "") -> str:
    if not ENV_PATH.exists():
        return default
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*([^#\n]*)")
    with ENV_PATH.open("r", encoding="utf-8") as fh:
        for line in fh:
            match = pattern.match(line)
            if match:
                return match.group(1).strip()
    return default


__all__ = ["set_key", "get_key", "ENV_PATH", "BACKUP_DIR"]
