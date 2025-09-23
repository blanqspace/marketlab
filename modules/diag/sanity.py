# tools/sanity_check.py
# Zweck: Schnellprüfungen vor Start. Keine Dateien/Reports.

import sys
import os
import json
from pathlib import Path

import sys
import os
from pathlib import Path

# Projekt-Root relativ zu tools/ ermitteln und ins sys.path hängen
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Konsole robuster machen (Windows)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

def ensure_dirs(paths):
    missing = [p for p in paths if not Path(p).exists()]
    return missing

def validate_json(paths):
    bad = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            bad.append((p, "missing"))
            continue
        try:
            json.load(open(path, "r", encoding="utf-8"))
        except Exception as e:
            bad.append((p, str(e)))
    return bad

def import_smoke(mods):
    failed = []
    for m in mods:
        try:
            __import__(m)
        except Exception as e:
            failed.append((m, str(e)))
    return failed

def main():
    print("Sanity-Check: Basisprüfungen laufen...")

    required_dirs = ["logs", "runtime/locks", "config"]
    required_json = [
        "config/startup.json",
        "config/client_ids.json",
        "config/healthcheck_config.json",
    ]
    required_imports = [
        "shared.utils.logger",
        "shared.core.config_loader",
        "shared.ibkr.ibkr_client",
        "shared.system.thread_tools",
    ]

    problems = []

    missing_dirs = ensure_dirs(required_dirs)
    if missing_dirs:
        problems.append(f"Missing dirs: {missing_dirs}")

    bad_json = validate_json(required_json)
    if bad_json:
        problems.append(f"Bad JSON: {bad_json}")

    failed_imports = import_smoke(required_imports)
    if failed_imports:
        problems.append(f"Import fails: {failed_imports}")

    if problems:
        print("Sanity issues detected:")
        for p in problems:
            print(" -", p)
        # Non-zero Exit signalisiert: Es gibt etwas zu prüfen.
        sys.exit(1)

    print("Sanity OK.")
    sys.exit(0)

if __name__ == "__main__":
    main()
