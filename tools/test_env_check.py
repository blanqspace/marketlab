import os
from dotenv import load_dotenv

load_dotenv()
t = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
print("ENABLED=", os.getenv("TELEGRAM_ENABLED"))
print("TOKEN_LEN=", len(t))
print("CONTROL_ID=", os.getenv("TG_CHAT_CONTROL"))
print("MOCK=", os.getenv("TELEGRAM_MOCK"))
