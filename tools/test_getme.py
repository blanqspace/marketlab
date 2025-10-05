import os, requests
from dotenv import load_dotenv

load_dotenv()
t = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
if not t:
    raise SystemExit("Kein Token.")
print("TOKEN_LEN =", len(t))
print("ENABLED =", os.getenv("TELEGRAM_ENABLED"))
print("CONTROL_ID =", os.getenv("TG_CHAT_CONTROL"))

r = requests.get(f"https://api.telegram.org/bot{t}/getMe", timeout=10)
print("status", r.status_code)
print(r.json())
