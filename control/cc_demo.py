# control/cc_demo.py
from __future__ import annotations
import time, json, threading, queue, sys
from pathlib import Path
from typing import Dict, Any, Optional

RUNTIME   = Path("runtime")
AUDIT_DIR = Path("reports/audit")
SAFE_FILE = RUNTIME / "safe_mode.json"
HB_FILE   = RUNTIME / "heartbeat.json"

def _wjson(p: Path, obj: Any):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _rjson(p: Path, default: Any):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return default

def _audit(rec: Dict[str, Any]):
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    fn = AUDIT_DIR / (time.strftime("%Y%m%d") + ".jsonl")
    with fn.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

class ControlCenter:
    def __init__(self):
        self.q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.running = False
        self.worker: Optional[threading.Thread] = None
        self.loop_on = False
        self.loop_interval = 5
        self._next_loop_ts = 0.0

    def submit(self, cmd: str, args: Dict[str, Any] | None = None, src: str = "terminal"):
        ev = {"ts": time.time(), "cmd": cmd.upper(), "args": args or {}, "src": src}
        self.q.put(ev); _audit({"type":"enqueue", **ev})

    def start(self):
        if self.running: return
        self.running = True
        self.worker = threading.Thread(target=self._loop, daemon=True, name="cc-worker")
        self.worker.start()

    def stop(self): self.running = False

    # ===== core loop =====
    def _loop(self):
        while self.running:
            now = time.time()
            if self.loop_on and now >= self._next_loop_ts:
                self._tick_loop()
                self._next_loop_ts = now + self.loop_interval
            try:
                ev = self.q.get(timeout=0.5)
            except queue.Empty:
                self._heartbeat(); continue
            _audit({"type":"dequeue", **ev})
            try:
                self._handle(ev)
            except Exception as e:
                _audit({"type":"error","ev":ev,"err":str(e)})
                self._notify(f"Control-Fehler: {e}", level="alert")

    # ===== handlers =====
    def _handle(self, ev: Dict[str, Any]):
        cmd, args, src = ev["cmd"], ev["args"], ev["src"]
        if cmd in {"PLACE","RUN_ONCE"} and self._safe_on():
            self._notify(f"SAFE-MODE aktiv. '{cmd}' blockiert.", level="warning")
            _audit({"type":"blocked_safe", **ev}); return

        if cmd == "RUN_ONCE":
            self._run_once()
        elif cmd == "LOOP_ON":
            self.loop_on = True; self._next_loop_ts = 0.0
            self._notify("LOOP_ON (alle 5s).", level="info")
        elif cmd == "LOOP_OFF":
            self.loop_on = False; self._notify("LOOP_OFF.", level="warning")
        elif cmd == "SAFE_ON":
            self._set_safe(True)
        elif cmd == "SAFE_OFF":
            self._set_safe(False)
        elif cmd == "STATUS":
            st = self.status()
            self._notify(f"STATUS: {json.dumps(st, ensure_ascii=False)}", level="info")
        elif cmd == "PLACE":
            sym = args.get("sym","AAPL"); qty = float(args.get("qty",1))
            self._notify(f"PLACE demo: {sym} x {qty} (kein Broker)", level="info")
        else:
            self._notify(f"Unbekanntes Kommando: {cmd}", level="warning")

    # ===== actions =====
    def _run_once(self):
        # Demo: Signale „finden“ und Platzierung simulieren
        self._notify("RUN_ONCE: Signale=AAPL BUY, MSFT SELL (demo)", level="info")

    def _tick_loop(self):
        self._notify("LOOP tick → RUN_ONCE (demo)", level="info")
        if not self._safe_on():
            self._notify("→ würde Orders prüfen/platzieren (demo)", level="info")
        else:
            self._notify("→ SAFE-MODE blockiert Orders (demo)", level="warning")

    # ===== safe/heartbeat/status =====
    def _safe_on(self) -> bool:
        return bool(_rjson(SAFE_FILE, {"safe": False}).get("safe", False))

    def _set_safe(self, on: bool):
        _wjson(SAFE_FILE, {"safe": bool(on), "ts": time.time()})
        self._notify(("SAFE_ON" if on else "SAFE_OFF"), level=("warning" if on else "info"))

    def _heartbeat(self):
        _wjson(HB_FILE, {"ts": time.time(), "safe": self._safe_on(), "loop_on": self.loop_on})

    def status(self) -> Dict[str, Any]:
        hb = _rjson(HB_FILE, {})
        return {"safe": self._safe_on(), "loop_on": self.loop_on,
                "last_hb": hb.get("ts"), "queue_size": self.q.qsize(),
                "interval_sec": self.loop_interval}

    # ===== notifier =====
    def _notify(self, msg: str, level: str = "info"):
        print(f"[{level.upper()}] {msg}")

control = ControlCenter()

# ===== simple CLI =====
def _cli():
    print("Commands: run, loop_on, loop_off, safe_on, safe_off, place <SYM> <QTY>, status, quit")
    while True:
        try:
            raw = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw: continue
        if raw.lower() in ("q","quit","exit"): break
        parts = raw.split()
        cmd = parts[0].lower()
        if cmd == "run":
            control.submit("RUN_ONCE")
        elif cmd == "loop_on":
            control.submit("LOOP_ON")
        elif cmd == "loop_off":
            control.submit("LOOP_OFF")
        elif cmd == "safe_on":
            control.submit("SAFE_ON")
        elif cmd == "safe_off":
            control.submit("SAFE_OFF")
        elif cmd == "status":
            control.submit("STATUS")
        elif cmd == "place":
            sym = parts[1] if len(parts) > 1 else "AAPL"
            qty = float(parts[2]) if len(parts) > 2 else 1
            control.submit("PLACE", {"sym": sym, "qty": qty})
        else:
            print("Unbekannt. Nutze: run | loop_on | loop_off | safe_on | safe_off | place SYM QTY | status | quit")

# ===== simulate "telegram" events (Demo) =====
def _simulate_telegram():
    # schickt testweise SAFE_ON und danach STATUS
    time.sleep(2.0); control.submit("SAFE_ON", src="telegram")
    time.sleep(2.0); control.submit("STATUS", src="telegram")
    time.sleep(4.0); control.submit("SAFE_OFF", src="telegram")

if __name__ == "__main__":
    control.start()
    threading.Thread(target=_simulate_telegram, daemon=True).start()
    _cli()
    control.stop()
    print("Bye.")
