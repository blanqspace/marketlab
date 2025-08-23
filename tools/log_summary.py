import os
from pathlib import Path
from datetime import datetime
import re
from shared.telegram_notifier.telegram_notifier import send_telegram_alert  # Wichtig!

LOG_DIR = Path("logs")
KEYWORDS = ["ERROR", "Exception", "CRITICAL", "WARNING", "Traceback"]

def summarize_logs(date: str = None):
    summary = []
    date_str = date or datetime.now().strftime("%Y-%m-%d")

    for module_dir in LOG_DIR.iterdir():
        if not module_dir.is_dir():
            continue
        log_file = module_dir / f"{date_str}.log"
        if not log_file.exists():
            continue

        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            errors = [line.strip() for line in lines if any(k in line for k in KEYWORDS)]
            if errors:
                summary.append((module_dir.name, len(errors), errors[-1].strip(), errors))
            else:
                summary.append((module_dir.name, 0, "OK", []))

    return summary

def send_telegram_errors(summary):
    """Sende kritische Fehler per Telegram."""
    error_lines = []

    for module, count, _, all_errors in summary:
        if count == 0:
            continue
        error_lines.append(f"🔧 {module} ({count} Fehler)")
        for line in all_errors[-3:]:  # Nur letzte 3 Fehler pro Modul senden
            error_lines.append(f"  {line}")
    
    if error_lines:
        message = "⚠️ Fehler beim robust_lab:\n\n" + "\n".join(error_lines)
        send_telegram_alert(message)
        
def print_summary():
    print("\n🔍 Log-Übersicht (heute):\n")
    summary = summarize_logs()
    for module, count, last, _ in summary:
        status = "✅ OK" if count == 0 else f"❗️{count} Fehler"
        print(f"{module:<20} | {status:<15} | Letzter Eintrag: {last[:80]}")

if __name__ == "__main__":
    print_summary()
