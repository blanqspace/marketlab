from __future__ import annotations
from pathlib import Path
import json, time
from marketlab.services.telegram_service import telegram_service  # simulate_update
from marketlab.services.telegram_service import _is_mock  # type: ignore

MOCK = Path("runtime/telegram_mock")

def last_payload() -> dict | None:
    for name in ("sendMessage_with_keyboard.json", "sendMessage.json"):
        p = MOCK / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return None

def main() -> int:
    assert _is_mock(), "TELEGRAM_MOCK ist nicht aktiv. Setze ENV oder .env!"
    MOCK.mkdir(parents=True, exist_ok=True)
    telegram_service.simulate_update("/menu")
    time.sleep(1.5)
    payload = last_payload()
    if not payload:
        print("❌ Kein sendMessage*.json gefunden. Poller läuft nicht oder Mock nicht erkannt.")
        return 1
    print("✅ Output:", json.dumps(payload, indent=2, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
