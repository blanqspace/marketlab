# modules/diag/pnl.py
from __future__ import annotations

import sys, time, csv
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional

# Projekt-Root für Imports
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ib_insync import IB
from shared.ibkr.ibkr_client import IBKRClient

# Ausgabe-Verzeichnisse
OUT_DIR = Path("reports/summary/pnl_sessions")
OUT_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class PnLPoint:
    ts: datetime
    unrealized: float
    realized: float
    daily: float

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)

def _fmt_hhmmss_local(ts: datetime) -> str:
    # Anzeige in lokaler Zeit (nur Uhrzeit)
    return ts.astimezone().strftime("%H:%M:%S")

def _write_csv(acct: str, rows: List[PnLPoint]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"pnl_stream_{acct}_{stamp}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["datetime_utc","unrealized","realized","daily"])
        for r in rows:
            w.writerow([r.ts.isoformat(), f"{r.unrealized:.2f}", f"{r.realized:.2f}", f"{r.daily:.2f}"])
    return path

def _write_summary(acct: str, rows: List[PnLPoint], pos_lines: List[str], csv_path: Optional[Path]) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUT_DIR / f"pnl_session_{acct}_{stamp}.txt"
    with path.open("w", encoding="utf-8") as fh:
        fh.write(f"PnL-Session Summary ({acct}) @ {_now_utc().isoformat()}\n")
        if pos_lines:
            fh.write("Positionen:\n")
            for ln in pos_lines:
                fh.write("  " + ln + "\n")
        if rows:
            fh.write("\nLetzter PnL:\n")
            fh.write(f"  Unrealized: {rows[-1].unrealized:.2f}\n")
            fh.write(f"  Realized:   {rows[-1].realized:.2f}\n")
            fh.write(f"  Daily:      {rows[-1].daily:.2f}\n")
        if csv_path:
            fh.write(f"\nCSV: {csv_path}\n")
    return path

def _print_header(acct: str, pos_lines: List[str]):
    print(f"\nPnL-Dashboard (Account: {acct})")
    if pos_lines:
        print("Positionen:")
        for ln in pos_lines:
            print(" ", ln)
    print(f"{'Zeit':<10}  {'Unrealized':>11}  {'Realized':>11}  {'Daily':>11}")

def _collect_positions(ib: IB) -> List[str]:
    out = []
    try:
        for p in ib.positions():
            c = p.contract
            sym = getattr(c, "localSymbol", getattr(c, "symbol", "?"))
            out.append(f"{sym:<12} {p.position:>8.2f} @ {p.avgCost}")
    except Exception:
        pass
    return out

def pnl_dashboard(runtime_sec: int = 30, csv_out: bool = True, show_positions: bool = True):
    """
    Streamt PnL (reqPnL) für das erste verfügbare Konto.
    Laufzeit in Sekunden; am Ende optional CSV + kurze Session-Zusammenfassung.
    """
    with IBKRClient(module="diag", task="pnl_dashboard") as ib:
        accts = ib.managedAccounts()
        acct = accts[0] if accts else None
        if not acct:
            print("❌ Kein Account gefunden.")
            return

        # optional Positionen
        pos_lines = _collect_positions(ib) if show_positions else []

        # PnL stream abonnieren
        pnl = ib.reqPnL(acct, "")
        rows: List[PnLPoint] = []

        _print_header(acct, pos_lines)

        t_end = time.time() + max(1, int(runtime_sec))
        last_print = 0.0

        try:
            while time.time() < t_end:
                ib.sleep(0.2)  # Events einsammeln
                # PnL Objekt aktualisiert sich; Werte auslesen
                u = getattr(pnl, "unrealizedPnL", 0.0) or 0.0
                r = getattr(pnl, "realizedPnL", 0.0) or 0.0
                d = getattr(pnl, "dailyPnL", 0.0) or 0.0
                point = PnLPoint(ts=_now_utc(), unrealized=float(u), realized=float(r), daily=float(d))
                rows.append(point)

                # moderat drucken (max ~5 Zeilen/Sek.)
                if time.time() - last_print >= 0.3:
                    print(f"{_fmt_hhmmss_local(point.ts):<10}  {point.unrealized:>11.2f}  {point.realized:>11.2f}  {point.daily:>11.2f}")
                    last_print = time.time()
        finally:
            try:
                ib.cancelPnL(pnl)
            except Exception:
                pass

        csv_path = _write_csv(acct, rows) if (csv_out and rows) else None
        txt_path = _write_summary(acct, rows, pos_lines, csv_path)
        if txt_path:
            print(f"(Summary: {txt_path})")
