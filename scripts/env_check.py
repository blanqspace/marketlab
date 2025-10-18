#!/usr/bin/env python3
"""Validate MarketLab environment without leaking secrets."""

from __future__ import annotations

from marketlab.bootstrap.env import load_env

TOKEN_PARTS = 2


def mask_token(token: str | None) -> str:
    if not token:
        return "-"
    parts = token.split(":", 1)
    if len(parts) == TOKEN_PARTS and parts[0].isdigit():
        return f"{parts[0]}:****"
    return token[:4] + "****"


def main() -> None:
    settings = load_env(mirror=True)
    telegram = settings.telegram
    print(
        {
            "env_mode": settings.env_mode,
            "ipc_db": settings.ipc_db,
            "telegram": {
                "enabled": bool(telegram.enabled),
                "mock": bool(telegram.mock),
                "chat_control": telegram.chat_control,
                "token": mask_token(
                    telegram.bot_token.get_secret_value() if telegram.bot_token else None
                ),
                "allowlist_count": len(telegram.allowlist or []),
            },
        }
    )


if __name__ == "__main__":
    main()
