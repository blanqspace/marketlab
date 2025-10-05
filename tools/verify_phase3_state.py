from __future__ import annotations
from marketlab.core.state_manager import STATE, RunState, Command

# simple offline check: simulate commands and snapshot
STATE.reset()
STATE.set_mode("test")
STATE.set_state(RunState.RUN)
STATE.set_target(10)
STATE.inc_processed(3)
snap1 = STATE.snapshot()
STATE.post(Command.PAUSE)
cmd = STATE.get_nowait()
assert cmd == Command.PAUSE
print({"ok": True, "snap": snap1})
