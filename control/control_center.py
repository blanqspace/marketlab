from __future__ import annotations
import json, time, threading, queue, os
from pathlib import Path
from typing import Any, Dict, Optional

# ---------- Persistenz ----------
RUNTIME = Path("runtime"); AUDIT_DIR = Path("reports/audit")
SAFE_FILE = RUNTIME / "safe_mode.json"; HB_FILE = RUNTIME / "heartbeat.json"

def _read_json(p: Path, default: Any) -> Any:
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return default

def _write_json(p: Path, obj: Any) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _append_audit(rec: Dict[str, Any]) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fn = AUDIT_DIR / (time.strftime("%Y%m%d") + ".jsonl")
    with fn.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

# ---------- Control Center ----------
class ControlCenter:
    def __init__(self):
        self.q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.running = False
        self.worker: Optional[threading.Thread] = None
        # Loop-Steuerung
        self.loop_on = False
        self.loop_interval = 0
        self._next_loop_ts = 0.0

    def submit(self, cmd: str, args: Dict[str, Any] | None = None, src: str = "terminal") -> None:
        ev = {"ts": time.time(), "cmd": cmd.upper(), "args": args or {}, "src": src}
        self.q.put(ev)
        _append_audit({"type": "enqueue", **ev})

    def start(self):
        if self.running: return
        self.running = True
        self.worker = threading.Thread(target=self._loop, daemon=True, name="control-worker")
        self.worker.start()

    def stop(self):
        self.running = False

    def _loop(self):
        # <<< Asyncio-Loop im Thread bereitstellen >>>
        import asyncio
        asyncio.set_event_loop(asyncio.new_event_loop())
        while self.running:
            # 1) Periodische Bot-Loops
            now = time.time()
            if self.loop_on and now >= self._next_loop_ts:
                try:
                    self._run_once()
                except Exception as e:
                    _append_audit({"type":"error","ev":{"cmd":"RUN_ONCE(loop)"},"err":str(e)})
                    self._notify(f"RUN_ONCE(loop) Fehler: {e}", level="alert")
                finally:
                    self._next_loop_ts = now + max(10, self.loop_interval)

            # 2) Events verarbeiten
            try:
                ev = self.q.get(timeout=0.5)
            except queue.Empty:
                self._heartbeat()
                continue
            try:
                _append_audit({"type": "dequeue", **ev})
                self._handle(ev)
            except Exception as e:
                _append_audit({"type":"error","ev":ev,"err":str(e)})
                self._notify(f"Control-Fehler: {e}", level="alert")

    # ---------- Handler ----------
    def _handle(self, ev: Dict[str, Any]) -> None:
        cmd = ev["cmd"]; args = ev["args"]
        if cmd in {"RUN_ONCE","PLACE","BUY","SELL"} and self._safe_on():
            self._notify(f"SAFE-MODE aktiv. '{cmd}' blockiert.", level="warning")
            _append_audit({"type":"blocked_safe", **ev}); return

        if cmd == "RUN_ONCE":
            self._run_once()
            self._notify("RUN_ONCE ausgeführt.", level="info")
        elif cmd == "LOOP_ON":
            itv = self._read_interval()
            self.loop_interval = itv
            self.loop_on = True
            self._next_loop_ts = 0.0
            self._notify(f"LOOP_ON (alle {itv}s).", level="info")
        elif cmd == "LOOP_OFF":
            self.loop_on = False
            self._notify("LOOP_OFF.", level="warning")
        elif cmd == "CANCEL_ALL":
            self._cancel_all()
        elif cmd == "SAFE_ON":
            self._set_safe(True)
        elif cmd == "SAFE_OFF":
            self._set_safe(False)
        elif cmd == "STATUS":
            st = self.status()
            self._notify(f"STATUS: {json.dumps(st, ensure_ascii=False)}", level="info")
        else:
            self._notify(f"Unbekanntes Kommando: {cmd}", level="warning")

    # ---------- Aktionen ----------
    def _run_once(self):
        from modules.bot.automation import run_once
        run_once("config/bot.yaml")

    def _read_interval(self) -> int:
        try:
            import yaml
            with open("config/bot.yaml", "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            return int(cfg.get("interval_sec", 120))
        except Exception:
            return 120

    def _cancel_all(self):
        try:
            from shared.ibkr.ibkr_client import IBKRClient
            with IBKRClient(module="control", task="cancel") as ib:
                ib.client.reqGlobalCancel()
            self._notify("Alle offenen Orders storniert.", level="warning")
        except Exception as e:
            self._notify(f"CancelAll fehlgeschlagen: {e}", level="alert")

    # ---------- SAFE/Heartbeat/Status ----------
    def _safe_on(self) -> bool:
        st = _read_json(SAFE_FILE, {"safe": False})
        return bool(st.get("safe", False))

    def _set_safe(self, on: bool):
        _write_json(SAFE_FILE, {"safe": bool(on), "ts": time.time()})
        self._notify(("SAFE_ON" if on else "SAFE_OFF"), level=("warning" if on else "info"))

    def _heartbeat(self):
        hb = {"ts": time.time(), "safe": self._safe_on(), "loop_on": self.loop_on}
        _write_json(HB_FILE, hb)

    def status(self) -> Dict[str, Any]:
        hb = _read_json(HB_FILE, {})
        return {"safe": self._safe_on(), "loop_on": self.loop_on,
                "last_hb": hb.get("ts"), "queue_size": self.q.qsize(),
                "interval_sec": self.loop_interval}

    # ---------- Notifier ----------
    def _notify(self, msg: str, level: str = "info"):
        try:
            from shared.system.telegram_notifier import to_control, to_alerts
            (to_control if level.lower() == "info" else to_alerts)(msg)
        except Exception:
            pass
        print(f"[{level.upper()}] {msg}")

# Singleton
control = ControlCenter()
