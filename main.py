# main.py
from __future__ import annotations
import sys, os, json, time, glob, subprocess
from pathlib import Path
from datetime import datetime

# --- Projekt-Root zuerst in sys.path aufnehmen ---
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Env laden
from shared.core.config_loader import load_env
load_env()

# Control Center starten
from control.control_center import control
control.start()

# Telegram-Inline-Bot erst jetzt importieren (nach sys.path!)
from telegram.bot_inline import start_inline_bot, stop_inline_bot


# Konsole robuster (UTF-8)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SHOW_HINTS = True

# ───────────────────────── Helpers ─────────────────────────
def header(title: str):
    print("\n" + "-"*70)
    print(title)
    print("-"*70)
    if SHOW_HINTS:
        print("Hinweis: 0=Zurück  M=Menü  Q=Beenden")

def ask(prompt: str, default: str | None = None) -> str:
    s = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
    if s.lower() in ("q","quit","x","exit"):
        sys.exit(0)
    if s.lower() in ("m","menu"):
        raise KeyboardInterrupt
    if s == "" and default is not None:
        return default
    return s

def ask_int(prompt: str, valid: list[int], default: int | None = None) -> int:
    while True:
        try:
            v = ask(prompt, str(default) if default is not None else None)
            if v == "" and default is not None:
                return default
            n = int(v)
            if n not in valid:
                print(f"Bitte {valid} wählen."); continue
            return n
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception:
            print("Bitte eine Zahl eingeben.")

def pause(msg="Enter=weiter ..."):
    _ = input(msg)

def pretty_ts(ts=None):
    return (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") if ts is None else str(ts))

# ───────────────────── Control Center ─────────────────────
def control_menu():
    while True:
        header("Control Center")
        print("1) RUN_ONCE")
        print("2) LOOP_ON")
        print("3) LOOP_OFF")
        print("4) CANCEL_ALL")
        print("5) SAFE_ON")
        print("6) SAFE_OFF")
        print("7) STATUS")
        print("0) Zurück")
        ch = ask_int("Auswahl", valid=[0,1,2,3,4,5,6,7])
        if ch == 0: return
        cmd = {1:"RUN_ONCE",2:"LOOP_ON",3:"LOOP_OFF",4:"CANCEL_ALL",5:"SAFE_ON",6:"SAFE_OFF",7:"STATUS"}[ch]
        control.submit(cmd, src="terminal")
        print(f"→ gesendet: {cmd}")
        pause()

# ───────────────────── Automation (Bot) ─────────────────────
def automation_menu():
    while True:
        header("Automation (Bot)")
        print("1) Run once (Event)")
        print("2) Start loop (Event)")
        print("3) Status anzeigen (Event)")
        print("4) Config-Hinweis (bot.yaml)")
        print("5) ASK-Flow abbrechen")
        print("6) ASK-Flow Status")
        print("0) Zurück")
        ch = ask_int("Auswahl", valid=[0,1,2,3,4,5,6])
        if ch == 0: return
        try:
            if ch == 1:
                control.submit("RUN_ONCE", src="terminal")
                print("→ RUN_ONCE gesendet."); pause()
            elif ch == 2:
                control.submit("LOOP_ON", src="terminal")
                print("→ LOOP_ON gesendet."); pause()
            elif ch == 3:
                control.submit("STATUS", src="terminal")
                print("→ STATUS gesendet."); pause()
            elif ch == 4:
                print("Konfigurationsdatei: config/bot.yaml")
                print("Pflicht-Keys:")
                print("  symbols[]")
                print("  data.{duration,barsize,what,rth}")
                print("  strategy.{name,fast,slow}")
                print("  exec.{mode,asset,order_type,qty,tif}")
                print("  interval_sec")
                print("  telegram.{enabled,ask_mode,ask_window_sec}")
                pause()
            elif ch == 5:
                from modules.bot.automation import ask_flow_cancel_cli
                ask_flow_cancel_cli(); pause()
            elif ch == 6:
                from modules.bot.automation import ask_flow_status_cli
                ask_flow_status_cli(); pause()
        except KeyboardInterrupt:
            print("\n⏹ Loop gestoppt.")
        except KeyError as e:
            print(f"❌ Bot-Fehler: fehlender Config-Schlüssel: {e}"); pause()
        except Exception as e:
            print(f"❌ Bot-Fehler: {e}"); pause()

# ───────────────────── Trade Hub / Tools (unverändert) ─────────────────────
def tradehub_menu():
    try:
        from modules.trade.menu import main_menu as trade_menu
    except Exception as e:
        print(f"❌ Trade-Menü Import-Fehler: {e}"); pause(); return
    try:
        trade_menu()
    except (KeyboardInterrupt, SystemExit):
        return
    except Exception as e:
        print(f"❌ Trade-Menü Fehler: {e}"); pause()

def tools_menu():
    # ... belassen wie bei dir ...
    print("Tools belassen"); pause()

# ─────────────────────── Hauptmenü ───────────────────────
def main_menu():
    global SHOW_HINTS
    while True:
        try:
            print("\n" + "-"*70)
            print("Hauptmenü")
            print("-"*70)
            if SHOW_HINTS:
                print("Hinweis: 0=Zurück  M=Menü  Q=Beenden")
            print("1) Automation (Bot)")
            print("2) Handeln (Trade Hub)")
            print("3) Tools (Daten, Backtests, Diagnose)")
            print("4) Control Center")
            print("5) Telegram-Bot starten")   # ← NEU
            print("6) Telegram-Bot stoppen")   # ← NEU
            print("H) Hinweise an/aus")
            print("0) Beenden")
            raw = input("Auswahl: ").strip()
            if raw.lower() in ("q","quit","x","exit"): break
            if raw.lower() in ("h",): SHOW_HINTS = not SHOW_HINTS; continue
            if raw == "1": automation_menu()
            elif raw == "2": tradehub_menu()
            elif raw == "3": tools_menu()
            elif raw == "4": control_menu()
            elif raw == "5": start_inline_bot()   # ← Start im selben Prozess
            elif raw == "6": stop_inline_bot()
            elif raw == "0": break
            else: print("Bitte 0–6 oder H/Q.")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main_menu()
