import os
from dotenv import load_dotenv
from shared.system.telegram_notifier import TelegramNotifier

load_dotenv()
enabled = str(os.getenv("TELEGRAM_ENABLED","0")) == "1"
routes = {
    "CONTROL": os.getenv("TG_CHAT_CONTROL"),
    "LOGS": os.getenv("TG_CHAT_LOGS"),
    "ORDERS": os.getenv("TG_CHAT_ORDERS"),
    "ALERTS": os.getenv("TG_CHAT_ALERTS"),
}
tn = TelegramNotifier(token=os.getenv("TELEGRAM_BOT_TOKEN",""), enabled=enabled, routes=routes)
print(tn.startup_probe())
