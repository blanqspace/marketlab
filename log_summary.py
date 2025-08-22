# my_tools/log_summary.py
import os
from pathlib import Path
from datetime import datetime
import re

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
            errors = [line for line in lines if any(k in line for k in KEYWORDS)]
            if errors:
                summary.append((module_dir.name, len(errors), errors[-1].strip()))
            else:
                summary.append((module_dir.name, 0, "OK"))

    return summary

def print_summary():
    print("\n🔍 Log-Übersicht (heute):\n")
    summary = summarize_logs()
    for module, count, last in summary:
        status = "✅ OK" if count == 0 else f"❗️{count} Fehler"
        print(f"{module:<20} | {status:<15} | Letzter Eintrag: {last[:80]}")

if __name__ == "__main__":
    print_summary()
