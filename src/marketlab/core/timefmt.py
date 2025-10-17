from __future__ import annotations

from datetime import datetime, timedelta, timezone


def iso_utc() -> str:
    """Return current time as ISO 8601 UTC string with 'Z'."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(s: str) -> datetime:
    """Parse ISO 8601 string into aware datetime. Falls back to UTC naive if needed."""
    s = (s or "").strip()
    try:
        return datetime.fromisoformat(s)
    except Exception:
        try:
            # common case: Z suffix
            if s.endswith("Z"):
                return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            pass
    # Fallback to epoch zero UTC if parsing fails
    return datetime.fromtimestamp(0, tz=timezone.utc)


def fmt_mm_ss(delta: timedelta) -> str:
    """Format a timedelta as mm:ss (zero-padded)."""
    total = int(delta.total_seconds())
    if total < 0:
        total = 0
    m, s = divmod(total, 60)
    return f"{m:02d}:{s:02d}"

