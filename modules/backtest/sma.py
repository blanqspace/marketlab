# modules/backtest/sma.py
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional

REQUIRED = ["datetime","open","high","low","close","volume"]

def _read_csv(path: Path) -> List[Tuple[str,float,float,float,float,int]]:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    hdr = [h.strip() for h in lines[0].split(",")]
    idx = {h:i for i,h in enumerate(hdr)}
    for need in REQUIRED:
        if need not in idx:
            raise ValueError(f"Pflichtspalte fehlt: {need}")
    rows=[]
    for ln in lines[1:]:
        parts = ln.split(",")
        try:
            rows.append((
                parts[idx["datetime"]],
                float(parts[idx["open"]]),
                float(parts[idx["high"]]),
                float(parts[idx["low"]]),
                float(parts[idx["close"]]),
                int(float(parts[idx["volume"]])) if parts[idx["volume"]] else 0
            ))
        except Exception:
            # fehlerhafte Zeile überspringen
            continue
    rows.sort(key=lambda r: r[0])
    return rows

def _sma(series: List[float], window: int) -> List[Optional[float]]:
    out = [None]*len(series)
    s=0.0
    for i,v in enumerate(series):
        s += v
        if i>=window: s -= series[i-window]
        if i>=window-1: out[i] = s/window
    return out

def run_backtest(
    csv_path: Path,
    fast: int = 10,
    slow: int = 20,
    spread: float = 0.0,
    slippage: float = 0.0,
    fee: float = 0.0,
    cash0: float = 100000.0,
    risk: float = 1.0,
    exec_mode: str = "close",   # "close" | "next_open"
    out_dir: Optional[Path] = None,
    equity_out: Optional[Path] = None,
):
    rows = _read_csv(csv_path)
    if len(rows) < max(fast,slow)+5:
        raise RuntimeError("Zu wenig Bars für SMA-Fenster.")

    closes = [r[4] for r in rows]
    opens  = [r[1] for r in rows]
    s_fast = _sma(closes, fast)
    s_slow = _sma(closes, slow)

    ts_run = datetime.now().strftime("%Y%m%d_%H%M%S")
    outd = out_dir or Path(f"reports/runs/{ts_run}")
    outd.mkdir(parents=True, exist_ok=True)
    trade_csv  = outd / "trades.csv"
    equity_csv = outd / "equity.csv"
    summary    = outd / "summary.txt"

    cash = cash0
    pos_qty = 0.0
    entry_px = None
    trades: List[Tuple[str,str,float,float,float]] = []  # (type,dt,price,qty,pnl)
    equity_hist: List[Tuple[str,float]] = []
    peak = cash0
    max_dd = 0.0

    # Hilfsfunktionen
    def _exec_price(side: str, bar_close: float, bar_open_next: float, for_entry: bool) -> float:
        """
        Liefert Ausführungspreis inkl. Spread/Slippage, je nach exec_mode.
        side: 'BUY'/'SELL'; for_entry: True=Entry, False=Exit
        Spreadmodell: BUY zahlt +spread/2, SELL erhält -spread/2; slippage immer gegen dich.
        """
        if exec_mode == "next_open":
            px = bar_open_next
        else:
            px = bar_close
        if side == "BUY":
            px = px + (spread/2.0) + slippage
        else:
            px = px - (spread/2.0) - slippage
        return px

    # iterieren
    last_idx = len(rows)-1
    for i in range(len(rows)):
        dt, o, h, l, c, v = rows[i]
        sf, ss = s_fast[i], s_slow[i]

        # Equity auf Basis Close
        eq = cash + (pos_qty * c if pos_qty>0 else 0.0)
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
        equity_hist.append((dt, eq))

        # solange keine Signale: weiter
        if sf is None or ss is None:
            continue

        want_long = (sf > ss)
        in_pos = pos_qty > 0

        # Für next_open brauchen wir i+1
        nxt_open = rows[i+1][1] if i < last_idx else c
        nxt_dt   = rows[i+1][0] if i < last_idx else dt

        # Exit bei Cross-down
        if in_pos and not want_long:
            fill = _exec_price("SELL", c, nxt_open, for_entry=False)
            fill_dt = nxt_dt if exec_mode=="next_open" and i<last_idx else dt
            pnl = pos_qty*(fill - entry_px) - fee
            cash += pnl
            trades.append(("EXIT", fill_dt, fill, pos_qty, pnl))
            pos_qty = 0.0
            entry_px = None

        # Entry bei Cross-up
        if (not in_pos) and want_long:
            use_cash = cash * risk
            if use_cash > 0:
                fill = _exec_price("BUY", c, nxt_open, for_entry=True)
                fill_dt = nxt_dt if exec_mode=="next_open" and i<last_idx else dt
                qty = use_cash / fill
                pos_qty = qty
                entry_px = fill
                cash -= fee
                trades.append(("ENTRY", fill_dt, fill, qty, -fee))

    # Am Ende glattstellen (Konvention)
    if pos_qty > 0:
        dt, o, h, l, c, v = rows[-1]
        fill = _exec_price("SELL", c, c, for_entry=False)
        pnl = pos_qty*(fill - entry_px) - fee
        cash += pnl
        trades.append(("EXIT", dt, fill, pos_qty, pnl))
        pos_qty = 0.0

    # Kennzahlen
    end_eq = equity_hist[-1][1] if equity_hist else cash
    ret_abs = end_eq - cash0
    n_trades = sum(1 for t in trades if t[0]=="EXIT")
    wins = sum(1 for t in trades if t[0]=="EXIT" and t[4] > 0)
    winrate = (wins/n_trades*100.0) if n_trades>0 else 0.0
    dd_pct = (max_dd/cash0*100.0) if cash0>0 else 0.0

    # Dateien schreiben
    with trade_csv.open("w", encoding="utf-8") as f:
        f.write("type,datetime,price,qty,pnl\n")
        for t in trades:
            f.write(",".join([t[0], t[1], str(t[2]), str(t[3]), str(t[4])]) + "\n")

    with equity_csv.open("w", encoding="utf-8") as f:
        f.write("datetime,equity\n")
        for dt,eq in equity_hist:
            f.write(f"{dt},{eq}\n")

    with (Path(summary)).open("w", encoding="utf-8") as f:
        f.write("SMA Cross Backtest\n")
        f.write(f"File: {csv_path}\n")
        f.write(f"Params: fast={fast}, slow={slow}, spread={spread}, slippage={slippage}, fee={fee}, cash={cash0}, risk={risk}, exec={exec_mode}\n")
        f.write(f"Trades (Exits): {n_trades}\n")
        f.write(f"Winrate: {winrate:.1f}%\n")
        f.write(f"PnL: {ret_abs:.2f}\n")
        f.write(f"End Equity: {end_eq:.2f}\n")
        f.write(f"Max Drawdown: {max_dd:.2f} ({dd_pct:.2f}%)\n")

    if equity_out:
        with Path(equity_out).open("w", encoding="utf-8") as f:
            f.write("datetime,equity\n")
            for dt,eq in equity_hist:
                f.write(f"{dt},{eq}\n")

    # Konsole
    print("✅ Backtest fertig")
    print(f"  Trades (Exits): {n_trades}")
    print(f"  Winrate:       {winrate:.1f}%")
    print(f"  PnL:           {ret_abs:.2f}")
    print(f"  End Equity:    {end_eq:.2f}")
    print(f"  Max DD:        {max_dd:.2f} ({dd_pct:.2f}%)")
    print(f"💾 Trades:  {trade_csv}")
    print(f"💾 Equity:  {equity_csv}")
    print(f"🧾 Summary: {summary}")

def main():
    import argparse
    ap = argparse.ArgumentParser(description="SMA Cross Backtest (Close oder Next-Open Ausführung)")
    ap.add_argument("csv", help="Bereinigte CSV (z. B. data_clean/stock_AAPL_5mins.csv)")
    ap.add_argument("--fast", type=int, default=10)
    ap.add_argument("--slow", type=int, default=20)
    ap.add_argument("--spread", type=float, default=0.0)
    ap.add_argument("--slippage", type=float, default=0.0)
    ap.add_argument("--fee", type=float, default=0.0)
    ap.add_argument("--cash", type=float, default=100000.0)
    ap.add_argument("--risk", type=float, default=1.0)
    ap.add_argument("--exec", choices=["close","next_open"], default="close", help="Ausführung am Close oder am nächsten Open")
    ap.add_argument("--out-dir", type=str, default=None)
    ap.add_argument("--equity-out", type=str, default=None)
    args = ap.parse_args()

    try:
        run_backtest(
            csv_path=Path(args.csv),
            fast=args.fast, slow=args.slow,
            spread=args.spread, slippage=args.slippage, fee=args.fee,
            cash0=args.cash, risk=args.risk,
            exec_mode=args.exec,
            out_dir=Path(args.out_dir) if args.out_dir else None,
            equity_out=Path(args.equity_out) if args.equity_out else None,
        )
    except Exception as e:
        print("❌", e); sys.exit(1)

if __name__ == "__main__":
    main()
