import signal

from marketlab.core.state_manager import STATE, RunState


def register_signal_handlers() -> None:
    def _stop(*_):
        STATE.set_state(RunState.EXIT)
    for sig in ("SIGINT","SIGTERM"):
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), _stop)
