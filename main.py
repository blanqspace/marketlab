# main.py
from __future__ import annotations
import sys
import threading
from pathlib import Path
from datetime import datetime
from datetime import datetime, timezone

# ── sys.path / Env ─────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.core.config_loader import load_env  # type: ignore
load_env()

# ── Control-Center ────────────────────────────────────────
from control.control_center import control  # type: ignore
control.start()

# ── Telegram-Bots (defensiv importieren) ──────────────────
try:
    from telegram.bot_inline import start_inline_bot, stop_inline_bot  # type: ignore
except Exception:
    def start_inline_bot():  # fallback no-op
        print("Inline-Bot-Modul fehlt.")
    def stop_inline_bot():
        pass

_CMD_BOT_THREAD = None  # type: ignore

def _start_cmd_bot_in_thread() -> None:
    """Startet telegram.bot_control.start() im Hintergrund."""
    global _CMD_BOT_THREAD
    if _CMD_BOT_THREAD and _CMD_BOT_THREAD.is_alive():
        return

    def _runner():
        try:
            from telegram.bot_control import start as _start  # type: ignore
            _start()
        except Exception as e:
            print(f"bot_control Fehler: {e}")

    t = threading.Thread(target=_runner, name="tg-cmd-bot", daemon=True)
    t.start()
    _CMD_BOT_THREAD = t

# ── Console UTF-8 ─────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SHOW_HINTS = True

# ───────────── Helpers ─────────────
def _status_line() -> str:
    try:
        hb = control.status()
        safe = "ON" if hb.get("safe") else "OFF"
        lp = "ON" if hb.get("loop_on") else "OFF"
        itv = hb.get("interval_sec", 0)
        qsz = hb.get("queue_size", 0)
        last = hb.get("last_hb")
        last_iso = datetime.fromtimestamp(last, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if last else "-"
        return f"[SAFE:{safe}] [LOOP:{lp} {itv}s] [Queue:{qsz}] [Last:{last_iso}]"
    except Exception:
        return ""

def _header(title: str) -> None:
    st = _status_line()
    print("\n" + "-" * 70)
    print(title)
    if st:
        print(st)
    print("-" * 70)
    if SHOW_HINTS:
        print("Hinweis: 0=Zurück  M=Mehr  Q=Beenden")

def _ask(prompt: str, default: str | None = None) -> str:
    s = input(f"{prompt}{f' [{default}]' if default is not None else ''}: ").strip()
    if s.lower() in ("q", "quit", "x", "exit"):
        sys.exit(0)
    if s.lower() in ("m", "mehr"):
        raise KeyboardInterrupt
    if s == "" and default is not None:
        return default
    return s

def _ask_int(prompt: str, valid: list[int], default: int | None = None) -> int:
    while True:
        try:
            v = _ask(prompt, str(default) if default is not None else None)
            if v == "" and default is not None:
                return default
            n = int(v)
            if n not in valid:
                print(f"Bitte {valid} wählen.")
                continue
            return n
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception:
            print("Bitte eine Zahl eingeben.")

def _pause(msg: str = "Enter=weiter ...") -> None:
    _ = input(msg)

# ───────────── Kern-Aktionen ─────────────
def do_run_once() -> None:
    control.submit("RUN_ONCE", src="terminal")
    print("→ RUN_ONCE gesendet.")
    _pause()

def do_loop_toggle() -> None:
    st = control.status()
    if st.get("loop_on"):
        control.submit("LOOP_OFF", src="terminal")
        print("→ LOOP_OFF gesendet.")
    else:
        control.submit("LOOP_ON", src="terminal")
        print("→ LOOP_ON gesendet.")
    _pause()

def do_safe_toggle() -> None:
    st = control.status()
    if st.get("safe"):
        control.submit("SAFE_OFF", src="terminal")
        print("→ SAFE_OFF gesendet.")
    else:
        control.submit("SAFE_ON", src="terminal")
        print("→ SAFE_ON gesendet.")
    _pause()

def do_status() -> None:
    control.submit("STATUS", src="terminal")
    print("→ STATUS gesendet.")
    _pause()

# ───────────── Orders ─────────────
def orders_menu() -> None:
    _header("Orders")
    print("1) Offene Orders anzeigen")
    print("2) Alle Orders stornieren (Global Cancel)")
    print("0) Zurück")
    ch = _ask_int("Auswahl", valid=[0, 1, 2])
    if ch == 0:
        return
    if ch == 1:
        try:
            from modules.trade.ops import list_orders  # type: ignore
            print("Offene Orders:")
            # list_orders druckt selbst, liefert nichts zurück
            list_orders(show_all=True, show_exec=False, show_pos=False)
        except Exception as e:
            print(f"list_orders Fehler: {e}")
        _pause()
    elif ch == 2:
        control.submit("CANCEL_ALL", src="terminal")
        print("→ CANCEL_ALL gesendet.")
        _pause()
# ───────────── Telegram ─────────────
def telegram_menu() -> None:
    _header("Telegram")
    print("1) Inline-Bot (Buttons) starten")
    print("2) Inline-Bot stoppen")
    print("3) Control-Bot (/run_once, /loop_on, …) starten")
    print("0) Zurück")
    ch = _ask_int("Auswahl", valid=[0, 1, 2, 3])
    if ch == 0:
        return
    if ch == 1:
        start_inline_bot()
        print("Inline-Bot gestartet.")
        _pause()
    elif ch == 2:
        stop_inline_bot()
        print("Inline-Bot gestoppt.")
        _pause()
    elif ch == 3:
        _start_cmd_bot_in_thread()
        print("Control-Bot gestartet.")
        _pause()

# ───────────── Mehr (Legacy) ─────────────
def more_menu() -> None:
    while True:
        _header("Mehr (Backtest, Daten, Diagnose)")
        print("1) Trade Hub (altes Menü)")
        print("2) Tools (Daten, Backtests, Diagnose)")
        print("3) Control Center (alt)")
        print("0) Zurück")
        ch = _ask_int("Auswahl", valid=[0, 1, 2, 3])
        if ch == 0:
            return
        if ch == 1:
            _legacy_tradehub()
        elif ch == 2:
            _legacy_tools()
        elif ch == 3:
            _legacy_control_menu()

def _legacy_tradehub() -> None:
    try:
        from modules.trade.menu import main_menu as trade_menu  # type: ignore
    except Exception as e:
        print(f"Trade-Menü Import-Fehler: {e}")
        _pause()
        return
    try:
        trade_menu()
    except (KeyboardInterrupt, SystemExit):
        return
    except Exception as e:
        print(f"Trade-Menü Fehler: {e}")
        _pause()

def _legacy_tools() -> None:
    print("Tools belassen")
    _pause()

def _legacy_control_menu() -> None:
    while True:
        _header("Control Center (alt)")
        print("1) RUN_ONCE")
        print("2) LOOP_ON")
        print("3) LOOP_OFF")
        print("4) CANCEL_ALL")
        print("5) SAFE_ON")
        print("6) SAFE_OFF")
        print("7) STATUS")
        print("0) Zurück")
        ch = _ask_int("Auswahl", valid=[0, 1, 2, 3, 4, 5, 6, 7])
        if ch == 0:
            return
        cmd_map = {
            1: "RUN_ONCE", 2: "LOOP_ON", 3: "LOOP_OFF",
            4: "CANCEL_ALL", 5: "SAFE_ON", 6: "SAFE_OFF", 7: "STATUS"
        }
        cmd = cmd_map[ch]
        control.submit(cmd, src="terminal")
        print(f"→ gesendet: {cmd}")
        _pause()

# ───────────── Main ─────────────
def main_menu() -> None:
    global SHOW_HINTS
    while True:
        try:
            print("\n" + "-" * 70)
            print("Hauptmenü")
            st = _status_line()
            if st:
                print(st)
            print("-" * 70)
            if SHOW_HINTS:
                print("Hinweis: 0=Beenden  M=Mehr  H=Hinweise umschalten")
            print("1) Run once")
            print("2) Loop  ON/OFF")
            print("3) SAFE  ON/OFF")
            print("4) Status")
            print("5) Orders")
            print("9) Telegram")
            print("M) Mehr")
            print("0) Beenden")
            raw = input("Auswahl: ").strip()
            lo = raw.lower()
            if lo in ("q", "quit", "x", "exit", "0"):
                break
            if lo in ("h",):
                SHOW_HINTS = not SHOW_HINTS
                continue
            if lo in ("m", "mehr"):
                more_menu()
                continue
            if raw == "1":
                do_run_once()
            elif raw == "2":
                do_loop_toggle()
            elif raw == "3":
                do_safe_toggle()
            elif raw == "4":
                do_status()
            elif raw == "5":
                orders_menu()
            elif raw == "9":
                telegram_menu()
            else:
                print("Bitte 0,1,2,3,4,5,9 oder M.")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main_menu()
