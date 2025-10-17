"""
Telegram Mock CLI (robust, no flicker)
- Läuft mit TELEGRAM_MOCK=1
- Kommandos per Zeile: menu, status, pause, resume, stop, follow, quit, help
- Ausgabe: letzte gesendete Nachricht (plain/keyboard), ohne Screen-Clear
- 'follow': zeigt neue Bot-Nachrichten live, bis Strg+C
"""
from __future__ import annotations
import sys, time, json
from pathlib import Path
from marketlab.services.telegram_service import telegram_service, _is_mock  # type: ignore

MOCK_DIR = Path("runtime/telegram_mock")
MSG_WITH_KB = MOCK_DIR / "sendMessage_with_keyboard.json"
MSG_PLAIN   = MOCK_DIR / "sendMessage.json"

def _load_json(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def _last_payload() -> tuple[Path | None, dict | None, float]:
    # Priorität: mit Keyboard, dann plain
    cand = []
    if MSG_WITH_KB.exists(): cand.append(MSG_WITH_KB)
    if MSG_PLAIN.exists():   cand.append(MSG_PLAIN)
    if not cand:
        return None, None, 0.0
    p = max(cand, key=lambda x: x.stat().st_mtime)
    return p, _load_json(p), p.stat().st_mtime

def _print_payload(payload: dict | None) -> None:
    if not payload:
        print("— keine gesendete Nachricht gefunden —")
        return
    text = payload.get("text", "").strip()
    print(f"Text: {text!r}")
    kb = (payload.get("reply_markup") or {}).get("inline_keyboard") or []
    if kb:
        print("Buttons:")
        for row in kb:
            print("  [" + " | ".join(b.get("text","?") for b in row) + "]")

def _send(cmd: str) -> None:
    telegram_service.simulate_update(cmd)

def cmd_once(cmd: str) -> None:
    before = _last_payload()[2]
    _send(cmd)
    # Warte kurz auf neue Ausgabe
    deadline = time.time() + 2.0
    shown = False
    while time.time() < deadline:
        _, payload, ts = _last_payload()
        if ts > before:
            _print_payload(payload)
            shown = True
            break
        time.sleep(0.1)
    if not shown:
        # Fallback: zeige aktuellen Stand
        _, payload, _ = _last_payload()
        _print_payload(payload)

def cmd_follow() -> None:
    print("Folge neuen Nachrichten. Strg+C beendet.")
    last_ts = _last_payload()[2]
    try:
        while True:
            _, payload, ts = _last_payload()
            if ts > last_ts:
                print("\n— neue Nachricht —")
                _print_payload(payload)
                last_ts = ts
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("\nFollow beendet.")

def main():
    if not _is_mock():
        print("❌ TELEGRAM_MOCK ist nicht aktiv. Setze TELEGRAM_MOCK=1.")
        sys.exit(1)
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    print("Telegram Mock CLI. Kommandos: menu, status, pause, resume, stop, follow, help, quit")
    while True:
        try:
            line = input("> ").strip().lower()
        except EOFError:
            break
        if line in ("quit","q","exit"):
            break
        if line in ("help","h","?"):
            print("Kommandos: menu, status, pause, resume, stop, follow, help, quit")
            continue
        if line == "follow":
            cmd_follow()
            continue
        mapping = {
            "menu": "/menu",
            "status": "/status",
            "pause": "/pause",
            "resume": "/resume",
            "stop": "/stop",
        }
        if line in mapping:
            cmd_once(mapping[line])
        elif line == "":
            continue
        else:
            print("Unbekannt. Nutze: help")

if __name__ == "__main__":
    main()

