# modules/bot/automation.py
# -*- coding: utf-8 -*-
import time, json, csv
from pathlib import Path
from typing import Callable, Optional, List, Dict, Any

from shared.utils.logger import get_logger
from shared.system.telegram_notifier import to_control, to_logs, to_alerts  # Legacy-kompatibel

logger = get_logger("automation")

class Automation:
    """
    Minimal-Orchestrierung ohne externe Modul-Abhängigkeiten.
    Pipeline: Ingest (Datei-Check) → Reco (Dummy) → Decision (No-Op) → Exec (No-Op) → Reports.
    """
    def __init__(self,
                 symbols: Optional[List[str]] = None,
                 data_cfg: Optional[Dict[str, Any]] = None,
                 strategy_cfg: Optional[Dict[str, Any]] = None,
                 exec_cfg: Optional[Dict[str, Any]] = None):
        self.symbols = symbols or ["AAPL", "MSFT", "SPY"]
        self.data_cfg = data_cfg or {"duration": "2 D", "barsize": "5 mins", "what": "TRADES", "rth": 1}
        self.strategy_cfg = strategy_cfg or {"name": "sma_cross", "fast": 10, "slow": 20}
        self.exec_cfg = exec_cfg or {"mode": "ASK", "asset": "STK", "order_type": "MKT", "qty": 1, "tif": "DAY"}
        self.last_run_id: Optional[str] = None
        self.safe_mode: bool = False

    # ---------------- helpers ----------------
    def _file_ingest(self, sym: str) -> Dict[str, Any]:
        clean = Path("data_clean") / f"stock_{sym}_5mins.csv"
        raw = Path("data") / f"stock_{sym}_5mins.csv"
        p = clean if clean.exists() else raw if raw.exists() else None
        rows = 0
        if p and p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    rows = sum(1 for _ in csv.reader(f))
            except Exception as e:
                logger.warning(f"read csv failed {sym}: {e}")
        return {"symbol": sym, "exists": bool(p), "path": str(p) if p else None, "rows": rows}

    def _write_run_report(self, run_id: str, ingest_reports: List[Dict[str, Any]]):
        outdir = Path("reports") / "runs" / run_id
        outdir.mkdir(parents=True, exist_ok=True)
        for rep in ingest_reports:
            (outdir / f"ingest_{rep['symbol']}_5mins.json").write_text(
                json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    # ---------------- public API ----------------
    def run_once(self) -> str:
        run_id = time.strftime("%Y%m%d_%H%M%S")
        self.last_run_id = run_id
        t0 = time.time()
        to_logs(f"run_once start {run_id}")

        # 1) Ingest (Datei-Check)
        ingest_reports: List[Dict[str, Any]] = []
        try:
            for sym in self.symbols:
                rep = self._file_ingest(sym)
                ingest_reports.append(rep)
            ok_cnt = sum(1 for r in ingest_reports if r["exists"])
            to_logs(f"ingest_ok {ok_cnt}/{len(ingest_reports)} files")
            self._write_run_report(run_id, ingest_reports)
        except Exception as e:
            to_alerts(f"ingest_error {e}")
            logger.exception("ingest failed")
            return run_id

        # 2) Reco (Dummy)
        reco = {r["symbol"]: {"signal": None, "reason": "dummy"} for r in ingest_reports}

        # 3) Decision (No-Op)
        decisions = {"orders": [], "reason": "noop"}

        # 4) Exec (No-Op, SAFE respektiert)
        placed = 0
        to_control(f"exec_done safe={self.safe_mode} placed={placed}")

        dt = time.time() - t0
        to_logs(f"run_once end {run_id} dt={dt:.2f}s")
        return run_id

    def start_loop(self, interval_sec: int, should_continue_cb: Callable[[], bool]):
        interval_sec = max(1, int(interval_sec))
        to_control(f"loop_on interval={interval_sec}s")
        while should_continue_cb():
            t0 = time.time()
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"loop_run_error: {e}")
            dt = time.time() - t0
            time.sleep(max(0, interval_sec - dt))
        to_control("loop_off")
