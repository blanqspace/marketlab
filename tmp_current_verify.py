from __future__ import annotations
from marketlab.settings import settings
print({
  "enabled": settings.telegram.enabled,
  "has_token": bool(settings.telegram.bot_token),
  "chat_control": settings.telegram.chat_control,
  "allowlist": settings.telegram.allowlist_csv
})