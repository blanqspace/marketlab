import requests, json
from typing import cast
from pydantic import SecretStr
from marketlab.settings import settings

def tok()->str: return cast(SecretStr, settings.telegram.bot_token).get_secret_value()
base=f"https://api.telegram.org/bot{tok()}"
print("getUpdates now. Send /menu to your bot, then run again.")
r=requests.get(f"{base}/getUpdates", timeout=15)
j=r.json()
print(json.dumps(j, indent=2, ensure_ascii=False))
# Merke dir:
#  - message.chat.id  -> TG_CHAT_CONTROL
#  - message.from.id  -> TG_ALLOWLIST (deine User-ID)
