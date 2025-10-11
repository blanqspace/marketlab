from __future__ import annotations

from datetime import datetime, timezone, timedelta


def iso_utc() -> str:
    """Return current UTC time in ISO 8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(s: str) -> datetime:
    """Parse ISO 8601 string to aware datetime.

    Accepts strings with or without Z suffix.
    """
    try:
        return datetime.fromisoformat(s)
    except Exception:
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return datetime.now(timezone.utc)


def fmt_mm_ss(delta: timedelta) -> str:
    """Format a timedelta as MM:SS (clamped to non-negative)."""
    total = max(0, int(delta.total_seconds()))
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"

