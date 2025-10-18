"""Compatibility wrapper for Textual dashboard entry point."""

from __future__ import annotations

from marketlab.tui.dashboard import DashboardApp as _DashboardApp
from marketlab.tui.dashboard import main as _tui_main

DashboardApp = _DashboardApp

__all__ = ["DashboardApp", "main"]


def main(argv: list[str] | None = None) -> int:
    """Delegate CLI handling to the Textual dashboard module."""
    _ = argv  # CLI flags currently unused
    _tui_main()
    return 0


if __name__ == "__main__":  # pragma: no cover - module CLI
    raise SystemExit(main())
