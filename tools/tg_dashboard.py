"""
Telegram Mock Dashboard (local)
- Läuft nur mit TELEGRAM_MOCK=1
- Zeigt alle 1s den zuletzt gesendeten Mock-Output
- Tasten: [m]=/menu, [s]=/status, [p]=/pause, [r]=/resume, [x]=/stop, [q]=quit
"""
from __future__ import annotations
import os, time, json, sys
from pathlib import Path

try:
    from marketlab.services.telegram_service import telegram_service  # simulate_update(...)
    from marketlab.services.telegram_service import _is_mock  # type: ignore
except Exception as e:
    print("Importfehler:", e)
    sys.exit(1)

MOCK_DIR = Path("runtime/telegram_mock")
MSG_WITH_KB = MOCK_DIR / "sendMessage_with_keyboard.json"
MSG_PLAIN   = MOCK_DIR / "sendMessage.json"

def clear():
    try:
        os.system("cls" if os.name == "nt" else "clear")
    except Exception:
        pass

def read_last_payload() -> dict | None:
    # Priorität: mit Keyboard, dann plain
    for p in (MSG_WITH_KB, MSG_PLAIN):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None

def fmt_payload(p: dict | None) -> list[str]:
    if not p:
        return ["<keine gesendete Nachricht gefunden>"]
    lines = []
    text = p.get("text", "").strip()
    lines.append(f"Text: {text!r}")
    if "reply_markup" in p:
        kb = p["reply_markup"].get("inline_keyboard", [])
        btns = []
        for row in kb:
            row_txt = " | ".join([b.get("text","?") for b in row])
            btns.append("  [" + row_txt + "]")
        if btns:
            lines.append("Buttons:")
            lines.extend(btns)
    return lines

def send_cmd(cmd: str):
    # Simuliert eingehende Updates für den Poller
    telegram_service.simulate_update(cmd)

def key_loop():
    # Windows: msvcrt für single-key; sonst fallback auf input()
    use_msvcrt = (os.name == "nt")
    if use_msvcrt:
        try:
            import msvcrt  # type: ignore
        except Exception:
            use_msvcrt = False

    last_ts = 0.0
    while True:
        now = time.time()
        if now - last_ts >= 1.0:
            clear()
            print("Telegram Mock Dashboard  |  TELEGRAM_MOCK=1 erforderlich")
            print("Keys: [m]=menu  [s]=status  [p]=pause  [r]=resume  [x]=stop  [q]=quit\n")
            payload = read_last_payload()
            for line in fmt_payload(payload):
                print(line)
            last_ts = now

        if use_msvcrt:
            if msvcrt.kbhit():
                ch = msvcrt.getwch().lower()
                if ch == "q":
                    return
                elif ch == "m":
                    send_cmd("/menu")
                elif ch == "s":
                    send_cmd("/status")
                elif ch == "p":
                    send_cmd("/pause")
                elif ch == "r":
                    send_cmd("/resume")
                elif ch == "x":
                    send_cmd("/stop")
                time.sleep(0.3)
        else:
            try:
                cmd = input("\nBefehl [m/s/p/r/x/q] + Enter: ").strip().lower()
            except EOFError:
                return
            if cmd in ("q", "quit", "exit"):
                return
            mapping = {"m":"/menu","s":"/status","p":"/pause","r":"/resume","x":"/stop"}
            if cmd in mapping:
                send_cmd(mapping[cmd])
            time.sleep(0.3)

def main():
    if not _is_mock():
        print("❌ TELEGRAM_MOCK ist nicht aktiv. Setze TELEGRAM_MOCK=1 und starte erneut.")
        sys.exit(1)
    MOCK_DIR.mkdir(parents=True, exist_ok=True)
    key_loop()

if __name__ == "__main__":
    main()

