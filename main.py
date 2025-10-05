#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import argparse
from pathlib import Path

from shared.core.config_loader import load_env
from shared.system.telegram_notifier import TelegramNotifier
from shared.utils.logger import get_logger
from modules.bot.automation import Automation

logger = get_logger("main")

# -------- CLI --------
def parse_args():
    p = argparse.ArgumentParser(description="robust_lab controller")
    p.add_argument("--run-once", action="store_true")
    p.add_argument("--loop-on", type=int, metavar="SECONDS")
    p.add_argument("--loop-off", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--safe-on", action="store_true")
    p.add_argument("--safe-off", action="store_true")
    return p.parse_args()

# -------- Telegram init --------
def _build_routes(env: dict) -> dict:
    return {
        "CONTROL": env.get("TG_CHAT_CONTROL"),
        "LOGS": env.get("TG_CHAT_LOGS") or env.get("TG_CHAT_CONTROL"),
        "ORDERS": env.get("TG_CHAT_ORDERS") or env.get("TG_CHAT_CONTROL"),
        "ALERTS": env.get("TG_CHAT_ALERTS") or env.get("TG_CHAT_CONTROL"),
        "DEFAULT": env.get("TG_CHAT_CONTROL"),
    }

def _init_telegram(env: dict) -> TelegramNotifier:
    enabled = str(env.get("TELEGRAM_ENABLED", "0")) == "1"
    token = env.get("TELEGRAM_BOT_TOKEN", "") or ""
    routes = _build_routes(env)
    tn = TelegramNotifier(token=token, enabled=enabled, routes=routes)
    if enabled and str(env.get("TELEGRAM_AUTOSTART", "0")) == "1":
        try:
            tn.startup_probe()
        except Exception as e:
            logger.error(f"telegram startup_probe failed: {e}")
    return tn

# -------- ControlCenter-Shim (kompatibel zu vorhandenen Menü-Erwartungen) --------
class ControlCenterShim:
    def __init__(self, automation: Automation):
        self.automation = automation
        self.loop_enabled = False
        self.safe_mode = False
        self._stopfile = Path("runtime/locks/loop_off")
        self._stopfile.parent.mkdir(parents=True, exist_ok=True)

    # optionale API, wird nur genutzt wenn vorhanden
    def start_heartbeat(self):  # no-op shim
        pass

    def _loop_should_continue(self):
        return self.loop_enabled and not self._stopfile.exists()

    def loop_on(self, interval_sec: int):
        self.loop_enabled = True
        try:
            if self._stopfile.exists():
                self._stopfile.unlink()
        except Exception:
            pass
        # nicht-blockierend hier; Block übernimmt main()
        self._interval = max(1, int(interval_sec))

    def loop_off(self):
        self.loop_enabled = False
        try:
            self._stopfile.touch(exist_ok=True)
        except Exception:
            pass

# -------- Menü --------
def run_menu(cc: ControlCenterShim):
    while True:
        print(
            "\n----------------------------------------------------------------------\n"
            "Hauptmenü\n"
            f"[SAFE:{'ON' if cc.safe_mode else 'OFF'}] "
            f"[LOOP:{'ON' if cc.loop_enabled else 'OFF'}]\n"
            "----------------------------------------------------------------------\n"
            "0) Beenden\n"
            "1) Run once\n"
            "2) Loop  ON/OFF\n"
            "3) SAFE  ON/OFF\n"
            "4) Status\n"
            "5) Orders (Platzhalter)\n"
        )
        choice = input("Auswahl: ").strip().lower()
        if choice == "0":
            return
        elif choice == "1":
            cc.start_heartbeat()
            cc.automation.safe_mode = cc.safe_mode
            cc.automation.run_once()
        elif choice == "2":
            if cc.loop_enabled:
                cc.loop_off()
                print("Loop: OFF")
            else:
                try:
                    interval = int(input("Intervall in Sekunden: ").strip() or "15")
                except ValueError:
                    interval = 15
                cc.start_heartbeat()
                cc.loop_on(interval)
                print(f"Loop gestartet @ {interval}s. STRG+C zum Stoppen.")
                _block_until_loop_stops(cc)
        elif choice == "3":
            cc.safe_mode = not cc.safe_mode
            print(f"SAFE: {'ON' if cc.safe_mode else 'OFF'}")
        elif choice == "4":
            print(f"Status → SAFE={cc.safe_mode} LOOP={cc.loop_enabled} LAST_RUN={cc.automation.last_run_id}")
        elif choice == "5":
            print("Orders: Platzhalter.")
        else:
            print("Ungültig.")

# -------- Helpers --------
def _block_until_loop_stops(cc: ControlCenterShim):
    try:
        # periodischer Loop mit Überlaufbehandlung
        while cc._loop_should_continue():
            t0 = time.time()
            cc.automation.safe_mode = cc.safe_mode
            try:
                cc.automation.run_once()
            except Exception as e:
                logger.error(f"loop_run_error: {e}")
            dt = time.time() - t0
            sleep = max(0, getattr(cc, "_interval", 15) - dt)
            time.sleep(sleep)
    except KeyboardInterrupt:
        cc.loop_off()

# -------- main --------
def main():
    args = parse_args()
    env = load_env()
    _ = _init_telegram(env)

    automation = Automation()
    cc = ControlCenterShim(automation)

    # Flags
    if args.safe_on:
        cc.safe_mode = True; print("SAFE=ON"); return
    if args.safe_off:
        cc.safe_mode = False; print("SAFE=OFF"); return
    if args.status:
        print(f"STATUS SAFE={cc.safe_mode} LOOP={cc.loop_enabled} LAST_RUN={automation.last_run_id}"); return
    if args.loop_off:
        cc.loop_off(); print("Loop: OFF"); return
    if args.run_once:
        cc.automation.safe_mode = cc.safe_mode
        rid = cc.automation.run_once()
        print(f"Run once done. RUN_ID={rid}"); return
    if args.loop_on is not None:
        cc.loop_on(max(1, int(args.loop_on)))
        print(f"Loop ON @ {args.loop_on}s. STRG+C zum Stoppen.")
        _block_until_loop_stops(cc); return

    # Menü
    run_menu(cc)

if __name__ == "__main__":
    main()
