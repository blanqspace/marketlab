from shared.logger import get_logger
from shared.config_loader import load_env, get_env_var, load_json_config
from shared.lock_tools import create_lock, remove_lock
from shared.telegram_notifier import send_telegram_alert
from shared.thread_tools import start_named_thread
from shared.file_utils import file_exists
from pathlib import Path
import time

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
        logger.info(f"Alte Lock-Datei entfernt: {lockfile}")


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
    """
    Lädt startup.json und startet alle aktiv gesetzten Module als Threads.
    """
    config = load_json_config("config/startup.json")
    modules = config.get("modules", {})

    for modulename, active in modules.items():
        if active:
            try:
                logger.info(f"Starte Modul: {modulename}")
                # Import wird dynamisch simuliert (z. B. modules.data_fetcher.main)
                exec(f"import modules.{modulename}.main as {modulename}_main")
                start_named_thread(modulename, eval(f"{modulename}_main.run"))
            except Exception as e:
                logger.error(f"❌ Fehler beim Start von Modul {modulename}: {e}")
                send_telegram_alert(f"❌ Fehler beim Start von *{modulename}*:\n{e}")
        else:
            logger.info(f"Modul deaktiviert: {modulename}")


def main():
    logger.info("🚀 Starte System: main_runner")
    
    load_env()
    
    if not create_lock("main_runner"):
        logger.error("main_runner bereits aktiv. Abbruch.")
        return

    try:
        cleanup_old_locks()
        check_previous_errors()
        start_activated_modules()
    except Exception as e:
        logger.exception(f"Fehler beim Start: {e}")
        send_telegram_alert(f"❌ Hauptstartfehler: {e}")
    finally:
        # NICHT sofort Lock entfernen → bleibt aktiv, während Threads laufen
        logger.info("Systemstart abgeschlossen.")

if __name__ == "__main__":
    main()
