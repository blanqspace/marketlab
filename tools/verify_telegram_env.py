from __future__ import annotations

import os
import re
import sys
from typing import List, Tuple

from marketlab.settings import settings


def _parse_allowlist(csv: str | None) -> Tuple[List[int], List[str]]:
    if not csv:
        return [], []
    oks: List[int] = []
    errs: List[str] = []
    for raw in csv.split(","):
        s = raw.strip()
        if not s:
            continue
        try:
            oks.append(int(s))
        except Exception:
            errs.append(s)
    return oks, errs


def _validate_token(tok: str | None) -> bool:
    if not tok:
        return False
    # Typical format: 123456789:XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    return bool(re.match(r"^\d+:[A-Za-z0-9_-]{20,}$", tok))


def verify_telegram_env() -> int:
    # Validate against runtime env instead of settings, to match actual process
    enabled = str(os.getenv("TELEGRAM_ENABLED", "")).strip().lower() in ("1", "true")
    mock = str(os.getenv("TELEGRAM_MOCK", "")).strip().lower() in ("1", "true")
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_raw = os.getenv("TG_CHAT_CONTROL")
    allow_raw = os.getenv("TG_ALLOWLIST") or ""
    allow_ids, allow_errs = _parse_allowlist(allow_raw)

    errors: List[str] = []

    if not enabled:
        print("ERROR: TELEGRAM_ENABLED not true")
        return 2

    if mock:
        # In mock mode: token not required, but chat id still useful for consistency
        if not chat_raw:
            errors.append("TG_CHAT_CONTROL missing (even in mock)")
    else:
        # Real mode requires proper token and chat id
        if not token:
            errors.append("TELEGRAM_BOT_TOKEN missing")
        elif not _validate_token(token):
            errors.append("TELEGRAM_BOT_TOKEN format looks invalid (expected <digits>:<secret>)")
        if not chat_raw:
            errors.append("TG_CHAT_CONTROL missing")

    # Validate chat id type
    if chat_raw:
        try:
            int(chat_raw)
        except Exception:
            errors.append("TG_CHAT_CONTROL must be integer (negative for groups)")

    # Validate allowlist
    if allow_raw:
        if allow_errs:
            errors.append(f"TG_ALLOWLIST contains non-integers: {', '.join(allow_errs)}")

    if errors:
        print("ERROR: Telegram environment invalid")
        for e in errors:
            print(f"- {e}")
        print("Hints:")
        print("- Ensure TELEGRAM_ENABLED=1 to enable, TELEGRAM_MOCK=0 for real API")
        print("- Set TELEGRAM_BOT_TOKEN to '123456789:...'")
        print("- Set TG_CHAT_CONTROL to your control chat id (negative for groups)")
        print("- Set TG_ALLOWLIST to comma-separated user ids allowed to control bot")
        return 2

    print("OK: Telegram environment looks valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify_telegram_env())
