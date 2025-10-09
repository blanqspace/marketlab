"""
Telegram diagnostic tool (Phase 5b compatible)

- Prüft die Telegram-Konfiguration (.env / settings)
- Testet, ob der Bot funktioniert (getMe)
- Kompatibel mit Pylint (Variante A: cast + SecretStr)
- Unterstützt MOCK-Mode und Real-Mode
"""

import os
import json
import requests
from typing import cast
from pydantic import SecretStr
from marketlab.settings import settings


def get_bot_token() -> str | None:
    """
    Gibt den Telegram-Bot-Token sicher zurück.
    Unterstützt Pydantic SecretStr + Umgebungsvariable.
    """
    token = None

    # Falls in Settings vorhanden (SecretStr oder normaler String)
    if getattr(settings.telegram, "bot_token", None):
        try:
            token = cast(SecretStr, settings.telegram.bot_token).get_secret_value()
        except AttributeError:
            token = str(settings.telegram.bot_token)

    # Falls Umgebungsvariable gesetzt
    if not token:
        token = os.getenv("TELEGRAM_BOT_TOKEN")

    return token


def main():
    tok = get_bot_token()
    if not tok:
        print("❌ Kein Telegram-Bot-Token gefunden.")
        return

    base = f"https://api.telegram.org/bot{tok}"
    mock = os.getenv("TELEGRAM_MOCK", "0") in ("1", "true", "True")

    print("Mock-Modus:", mock)
    print("Bot-Check wird ausgeführt...\n")

    if mock:
        print("🧩 MOCK aktiv: Es werden keine echten Requests gesendet.")
        print("  → Prüfe stattdessen runtime/telegram_mock/*.json")
        return

    try:
        # Webhook entfernen (sichere Verbindung prüfen)
        r = requests.post(f"{base}/deleteWebhook", timeout=6)
        r.raise_for_status()

        # getMe anfordern
        resp = requests.get(f"{base}/getMe", timeout=10)
        print("Status:", resp.status_code)
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))

        if data.get("ok"):
            print("\n✅ Telegram-Verbindung funktioniert.")
        else:
            print("\n⚠️ Telegram antwortet, aber ok=False – überprüfe Token oder Netzwerk.")

    except Exception as e:
        print(f"❌ Fehler bei der Verbindung: {e}")


if __name__ == "__main__":
    main()
