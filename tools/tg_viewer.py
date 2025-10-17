"""
Local Telegram Mock Viewer
Shows the last messages saved in runtime/telegram_mock/
and lets you simulate commands like /menu or /status.
"""

import json, time, os
from pathlib import Path
from marketlab.services.telegram_service import telegram_service

MOCK = Path("runtime/telegram_mock")

def show_last():
    f = MOCK / "sendMessage_with_keyboard.json"
    if f.exists():
        print("🧭 Last message with keyboard:")
        print(json.dumps(json.load(open(f, encoding="utf-8")), indent=2, ensure_ascii=False))
    f2 = MOCK / "sendMessage.json"
    if f2.exists():
        print("🧾 Last plain message:")
        print(json.dumps(json.load(open(f2, encoding="utf-8")), indent=2, ensure_ascii=False))

def simulate():
    while True:
        cmd = input("🪄 Command to simulate (/menu, /status, /pause, /resume, /stop, q): ").strip()
        if cmd in ("q", "quit", "exit"):
            break
        telegram_service.simulate_update(cmd)
        print(f"→ simulated {cmd}")
        time.sleep(1)
        show_last()

if __name__ == "__main__":
    show_last()
    simulate()

