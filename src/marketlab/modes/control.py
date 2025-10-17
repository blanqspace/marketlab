import time

from ..core.state_manager import STATE
from ..services.telegram_service import telegram_service


def run(settings):
    STATE.set_mode("control")
    STATE.set_state("RUN")
    telegram_service.notify_start("control")
    try:
        while not STATE.should_stop():
            time.sleep(0.25)
    finally:
        telegram_service.notify_end("control")
