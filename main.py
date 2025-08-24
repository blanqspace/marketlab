# main.py
import atexit
import sys
from pathlib import Path

from tools.log_summary import summarize_logs, send_telegram_errors  # ← sicherstellen, dass import korrekt
from shared.logger.logger import get_logger

logger = get_logger("main_runner", log_to_console=True)

def cleanup_old_locks():
    """
    Entfernt alte/verwaiste Lock-Dateien aus runtime/locks/
    """
    lock_dir = Path("runtime/locks")
    if not lock_dir.exists():
        return
    for lockfile in lock_dir.glob("*.lock"):
        lockfile.unlink()
        logger.info(f"🧹 Alte Lock-Datei entfernt: {lockfile}")

def check_previous_errors():
    """
    Prüft letzte Fehlerlogs – optional erweiterbar für kritische Warnungen.
    """
    error_log_dir = Path("logs/errors")
    latest = max(error_log_dir.glob("*.log"), default=None, key=lambda f: f.stat().st_mtime) if error_log_dir.exists() else None
    if latest and latest.stat().st_size > 0:
        logger.warning(f"⚠️ Letzte Fehlerdatei enthält Einträge: {latest}")
        send_telegram_alert(f"⚠️ Fehler beim letzten Start gefunden: {latest.name}")

def start_activated_modules():
    config = load_json_config("config/startup.json")
    modules = config.get("modules", {})

    for modulename, active in modules.items():
        if not active:
            logger.info(f"🟡 Modul deaktiviert: {modulename}")
            continue

        start_named_thread(
            name=f"modul_{modulename}",
            target=partial(run_module, modulename),  # ✅ sicheres Binden
            daemon=True,
            track=True
        )    
def run_module(name: str):
    try:
        logger.info(f"🟢 Starte Modul: {name}")
        module_path = f"modules.{name}.main"
        module = importlib.import_module(module_path)
        module.run()
    except Exception as e:
        logger.error(f"❌ Fehler beim Start von Modul {name}: {e}")
        send_telegram_alert(f"❌ Fehler beim Start von Modul *{name}*:\n{e}")

# neu oben:
import sys, subprocess, os

def run_sanity():
    """Führt sanity_check.py aus. Mit Auto-Fix, wenn SANITY_AUTO_FIX=true."""
    try:
        py = sys.executable or "python"
        args = [py, "sanity_check.py"]
        if os.getenv("SANITY_AUTO_FIX", "").strip().lower() in ("1", "true", "yes"):
            args.append("--fix")
        logger.info(f"🧪 Sanity-Check starte: {' '.join(args)}")
        res = subprocess.run(args, check=False, capture_output=True, text=True)
        if res.stdout:
            for line in res.stdout.strip().splitlines():
                logger.info(line)
        if res.stderr:
            for line in res.stderr.strip().splitlines():
                logger.warning(line)
        if res.returncode != 0:
            logger.warning(f"Sanity-Check meldete Returncode {res.returncode} (weiter mit Start).")
    except FileNotFoundError:
        logger.warning("sanity_check.py nicht gefunden – überspringe Sanity-Check.")
    except Exception as e:
        logger.warning(f"Sanity-Check konnte nicht ausgeführt werden: {e}")

def main():
    logger.info("🚀 Starte System: main_runner")
    load_env()

    # ✅ erst verwaiste Locks bereinigen, dann eigenes Lock erstellen
    cleanup_old_locks()

    if not create_lock("main_runner"):
        logger.error("⛔️ main_runner bereits aktiv. Abbruch.")
        return

    try:
        check_previous_errors()

        # ✅ Sanity-Check (optional mit Auto-Fix per ENV)
        run_sanity()

        start_activated_modules()
    except Exception as e:
        logger.exception(f"Fehler beim Start: {e}")
        send_telegram_alert(f"❌ Hauptstartfehler: {e}")
    finally:
        logger.info("✅ Systemstart abgeschlossen.")


if __name__ == "__main__":
    main()
