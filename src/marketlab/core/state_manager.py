from __future__ import annotations
from enum import Enum, auto
from dataclasses import dataclass, field
from queue import Queue, Empty
from threading import Event
from typing import Optional

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
    _queue: Queue[Command] = field(default_factory=Queue)
    _stop_evt: Event = field(default_factory=Event)

    def set_mode(self, mode: str) -> None:
        self.mode = mode

    def set_state(self, st: RunState) -> None:
        self.state = st
        if st == RunState.EXIT:
            self._stop_evt.set()

    def post(self, cmd: Command) -> None:
        self._queue.put(cmd)

    def get_nowait(self) -> Optional[Command]:
        try:
            return self._queue.get_nowait()
        except Empty:
            return None

    def should_stop(self) -> bool:
        return self.state == RunState.EXIT or self._stop_evt.is_set()

STATE = StateManager()