"""Package entry point for the Telegram poller.

This re-exports the legacy implementation from ``tools.tg_poller`` so both
``python -m tools.tg_poller`` and ``python -m marketlab.tools.tg_poller`` keep
working without diverging code paths.
"""

from __future__ import annotations

from tools.tg_poller import *  # type: ignore  # noqa: F401,F403
from tools.tg_poller import main as _legacy_main  # type: ignore


def main(*args, **kwargs):  # type: ignore[override]
    """Forward ``main`` to the legacy module (keeps type checkers happy)."""
    return _legacy_main(*args, **kwargs)


if __name__ == "__main__":  # pragma: no cover - module CLI
    raise SystemExit(main())
