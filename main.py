# main.py
import atexit
import sys
from pathlib import Path

from tools.log_summary import summarize_logs, send_telegram_errors  # ← sicherstellen, dass import korrekt
from shared.logger.logger import get_logger

logger = get_logger("main_runner", log_to_console=True)

# Exit-Funktion
def summarize_and_exit():
    summary = summarize_logs()
    critical_found = False
    summary_lines = []

    summary_lines.append("📋 Fehlerübersicht (beim Beenden des Programms):\n")

    for module, count, last_line, all_errors in summary:
        if count > 0:
            summary_lines.append(f"\n🔧 Modul: {module} ({count} Fehler)")
            for err in all_errors:
                summary_lines.append(f"  {err}")
            if any("CRITICAL" in e or "ERROR" in e for e in all_errors):
                critical_found = True

    summary_text = "\n".join(summary_lines)

    # ⬇️ Speicherort definieren
    report_path = Path("reports/error_summary.txt")
    report_path.parent.mkdir(exist_ok=True)
    report_path.write_text(summary_text, encoding="utf-8")

    # 🖨️ Terminal-Ausgabe NUR als Zusammenfassung
    print("\n📋 Fehlerübersicht (heute):")
    for module, count, *_ in summary:
        if count > 0:
            print(f"- {module}: {count} Fehler")
    if any(count > 0 for module, count, *_ in summary):
        print("→ Details siehe reports/error_summary.txt")

    # 📬 Telegram nur bei echten Fehlern
    if critical_found:
        send_telegram_errors(summary)

    # ⛔️ Exit-Code setzen, wenn Fehler
    if critical_found:
        sys.exit(1)

atexit.register(summarize_and_exit)

# 🧠 Start deiner Anwendung
print("🚀 Starte robust_lab...")
# ... dein restlicher Code ...
