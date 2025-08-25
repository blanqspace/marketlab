import sys
import importlib
import subprocess
import os
from pathlib import Path

from tools.log_summary import summarize_logs, send_telegram_errors
from shared.utils.logger import get_logger
from shared.core.config_loader import load_env, load_json_config
from shared.utils.lock_tools import create_lock
from shared.system.thread_tools import start_named_thread

APP_NAME = "TradingBot"  # Logger- und Lock-Name neutral
logger = get_logger(APP_NAME, log_to_console=True)


def cleanup_old_locks():
    lock_dir = Path("runtime/locks")
    if not lock_dir.exists():
        return
    for lockfile in lock_dir.glob("*.lock"):
        try:
            lockfile.unlink()
            logger.info(f"🧹 Alte Lock-Datei entfernt: {lockfile}")
        except Exception as e:
            logger.warning(f"Lock {lockfile} konnte nicht gelöscht werden: {e}")


def check_previous_errors():
    summary = summarize_logs()
    send_telegram_errors(summary)


def _thread_target_run_module(stop_event, modulename: str):
    try:
        logger.info(f"🟢 Starte Modul: {modulename}")
        module = importlib.import_module(f"modules.{modulename}.main")
        if hasattr(module, "run"):
            module.run()
        else:
            logger.warning(f"Modul {modulename} hat keine run()-Funktion.")
    except Exception as e:
        logger.error(f"❌ Fehler beim Start von Modul {modulename}: {e}")


def start_activated_modules():
    config = load_json_config("config/startup.json", fallback={"modules": {}})
    modules = config.get("modules", {})
    for modulename, active in modules.items():
        if not active:
            logger.info(f"🟡 Modul deaktiviert: {modulename}")
            continue
        start_named_thread(
            name=f"modul_{modulename}",
            target=_thread_target_run_module,
            args=(modulename,),
            daemon=True,
            track=True
        )


def run_sanity():
    """
    Führt tools/sanity_check.py aus.
    Keine Report-Erstellung. UTF-8 erzwungen. Nicht-blockierend für Start,
    aber Warnung bei Returncode != 0.
    """
    try:
        py = sys.executable or "python"
        args = [py, "tools/sanity_check.py"]

        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")

        logger.info(f"🧪 Sanity-Check starte:")
        res = subprocess.run(
            args, check=False, capture_output=True, text=True, env=env,
            encoding="utf-8", errors="replace"
        )
        if res.stdout:
            for line in res.stdout.splitlines():
                if line.strip():
                    logger.info(line)
        if res.stderr:
            for line in res.stderr.splitlines():
                if line.strip():
                    logger.warning(line)
        if res.returncode != 0:
            logger.warning(f"Sanity-Check meldete Returncode {res.returncode} (weiter mit Start).")
    except FileNotFoundError:
        logger.warning("tools/sanity_check.py nicht gefunden – überspringe Sanity-Check.")
    except Exception as e:
        logger.warning(f"Sanity-Check konnte nicht ausgeführt werden: {e}")


def main():
    logger.info(f"🚀 Starte System: {APP_NAME}")
    load_env()
    cleanup_old_locks()

    if not create_lock(APP_NAME):
        logger.error(f"⛔️ {APP_NAME} bereits aktiv. Abbruch.")
        return

    try:
        check_previous_errors()
        run_sanity()
        start_activated_modules()
    except Exception as e:
        logger.exception(f"Fehler beim Start: {e}")
    finally:
        logger.info("✅ Systemstart abgeschlossen.")


if __name__ == "__main__":
    main()
