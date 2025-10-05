from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from queue import Queue, Empty
from threading import Event
from typing import Optional
import time

class RunState(Enum):
    INIT = auto()
    RUN = auto()
    PAUSE = auto()
    EXIT = auto()

class Command(Enum):
    STATUS = auto()
    PAUSE = auto()
    RESUME = auto()
    STOP = auto()

@dataclass
class StateManager:
    mode: str = "unknown"
    state: RunState = RunState.INIT
    started_ts: float = 0.0
    processed: int = 0
    target: int = 0
    _queue: Queue[Command] = field(default_factory=Queue)
    _stop_evt: Event = field(default_factory=Event)

    def reset(self) -> None:
        self.state = RunState.INIT
        self.started_ts = 0.0
        self.processed = 0
        self.target = 0
        with self._queue.mutex:
            self._queue.queue.clear()
        self._stop_evt.clear()

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_state(self, st: RunState) -> None:
        self.state = st
        if st == RunState.RUN and self.started_ts == 0.0:
            self.started_ts = time.time()
        if st == RunState.EXIT:
            self._stop_evt.set()

    def set_target(self, n: int) -> None:
        self.target = max(0, int(n))

    def inc_processed(self, n: int = 1) -> None:
        self.processed += n

    def post(self, cmd: Command) -> None:
        self._queue.put(cmd)

    def get_nowait(self) -> Optional[Command]:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def should_stop(self) -> bool:
        return self.state == RunState.EXIT or self._stop_evt.is_set()

    def uptime_sec(self) -> int:
        return int(time.time() - self.started_ts) if self.started_ts else 0

    def snapshot(self) -> dict:
        return {
            "mode": self.mode,
            "state": self.state.name,
            "uptime": self.uptime_sec(),
            "processed": self.processed,
            "target": self.target,
        }

STATE = StateManager()
