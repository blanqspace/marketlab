from __future__ import annotations
from pathlib import Path
import sys
import json

def main() -> int:
    # Create a tiny demo CSV if missing
    data_dir = Path.cwd() / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    demo = data_dir / "AAPL_15m.csv"
    if not demo.exists():
        demo.write_text("time,open,high,low,close,volume\n2024-01-01T09:30:00,190,191,189,190.5,100000\n", encoding="utf-8")

    # Try loading via adapter
    try:
        from marketlab.data.adapters import CSVAdapter
        bars = list(CSVAdapter().fetch_bars("AAPL","15m"))
        assert len(bars) >= 1, "no rows loaded"
        row = bars[0]
        for k in ["time","open","high","low","close","volume"]:
            assert k in row, f"missing key {k}"
        print(json.dumps({"ok": True, "rows": len(bars)}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())