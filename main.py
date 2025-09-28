# main.py
from __future__ import annotations
import sys, os, json, time, glob, subprocess
from pathlib import Path
from datetime import datetime

# --- Projekt-Root in sys.path aufnehmen ---
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
        raise KeyboardInterrupt  # zurück ins Hauptmenü
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
                print(f"Bitte {valid} wählen.")
                continue
            return n
        except KeyboardInterrupt:
            raise
        except SystemExit:
            raise
        except Exception:
            print("Bitte eine Zahl eingeben.")

def pause(msg="Enter=weiter ..."):
    _ = input(msg)

def read_json_safe(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def pretty_ts(ts=None):
    return (datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ") if ts is None else str(ts))

# ───────────────────── Automation (Bot) ─────────────────────
def automation_menu():
    while True:
        try:
            header("Automation (Bot)")
            print("1) Run once (ein Durchlauf jetzt)")
            print("2) Start loop (forever, Ctrl+C zum Stoppen)")
            print("3) Status anzeigen")
            print("4) Config-Hinweis (bot.yaml)")
            print("0) Zurück")
            ch = ask_int("Auswahl", valid=[0,1,2,3,4])

            if ch == 0:
                return

            if ch == 1:
                try:
                    from modules.bot.runner import run_once
                except Exception as e:
                    print(f"❌ Import-Fehler: {e}"); pause(); continue
                try:
                    run_once()
                except KeyboardInterrupt:
                    pass
                except Exception as e:
                    print(f"❌ Bot-Fehler: {e}")
                pause()

            elif ch == 2:
                try:
                    from modules.bot.runner import run_forever
                except Exception as e:
                    print(f"❌ Import-Fehler: {e}"); pause(); continue
                print("↻ Loop startet. Beenden mit Ctrl+C …")
                try:
                    run_forever()
                except KeyboardInterrupt:
                    print("\n⏹ Loop gestoppt.")
                except Exception as e:
                    print(f"❌ Bot-Fehler: {e}")
                pause()

            elif ch == 3:
                state = read_json_safe(Path("runtime/state.json"))
                print("\nRuntime-State:", json.dumps(state, indent=2, ensure_ascii=False))
                # jüngste Reco-Datei suchen
                today = datetime.utcnow().strftime("%Y%m%d")
                paths = sorted(glob.glob(f"reports/reco/{today}/reco_*.json"))
                print("Letzte Reco:", paths[-1] if paths else "(keine)")
                pause()

            elif ch == 4:
                p = Path("config/bot.yaml")
                print(f"Bot-Config: {p}  ({'fehlt' if not p.exists() else 'OK'})")
                print("Wichtige Keys: run_every_sec, auto_mode (off/ask/auto), symbols[], strategy, risk, telegram")
                pause()

        except KeyboardInterrupt:
            return

# ───────────────────── Trade Hub (manuell) ─────────────────────
def tradehub_menu():
    try:
        from modules.trade.menu import main_menu as trade_menu
    except Exception as e:
        print(f"❌ Trade-Menü Import-Fehler: {e}")
        pause(); return
    try:
        trade_menu()
    except KeyboardInterrupt:
        return
    except SystemExit:
        return
    except Exception as e:
        print(f"❌ Trade-Menü Fehler: {e}")
        pause()

# ───────────────────────── Tools ─────────────────────────
def tools_menu():
    while True:
        try:
            header("Tools")
            print("1) Daten • Historie abrufen (ein Symbol)")
            print("2) Daten • CSV prüfen (validate)")
            print("3) Backtest (SMA Cross)")
            print("4) Sanity-Check")
            print("5) IBKR-Status")
            print("6) Symbol-Scan (Paper-Berechtigungen)")
            print("7) PnL-Dashboard")
            print("0) Zurück")
            ch = ask_int("Auswahl", valid=[0,1,2,3,4,5,6,7])

            if ch == 0:
                return

            if ch == 1:
                # einfacher Single-Ingest-Dialog
                try:
                    from modules.data.ingest import ingest_one
                except Exception as e:
                    print(f"❌ Import-Fehler: {e}"); pause(); continue
                sym = ask("Symbol", "AAPL").upper()
                asset = ask("Asset (stock/forex)", "stock")
                duration = ask("Dauer (z. B. 5 D / 6 M / 1 Y)", "5 D")
                barsize = ask("Bar-Größe (z. B. 1 min / 5 mins / 15 mins / 1 day)", "5 mins")
                what = ask("WhatToShow (TRADES/MIDPOINT/BID/ASK)", "TRADES")
                rth = ask("Nur RTH? (j/n)", "j").lower().startswith("j")
                overwrite = ask("RAW überschreiben? (j/n)", "n").lower().startswith("j")
                try:
                    m = ingest_one(sym, asset=asset, duration=duration, barsize=barsize,
                                   what=what, rth=rth, overwrite=overwrite)
                    print("OK:", json.dumps(m, indent=2, ensure_ascii=False))
                except Exception as e:
                    print("❌ Ingest-Fehler:", e)
                pause()

            if ch == 2:
                # modules/data/validate.py via Subprozess (wie gehabt)
                csvp = ask("CSV-Pfad", "data/stock_AAPL_5mins.csv")
                bars = ask("Bar-Größe (für Gap-Check)", "5 mins")
                outp = ask("Gesäuberte Ausgabe-Datei (leer=keine)", "")
                cmd = [sys.executable, str(ROOT/"modules/data/validate.py"), csvp, "--barsize", bars]
                if outp.strip():
                    cmd += ["--out", outp.strip()]
                print("→", " ".join(cmd))
                try:
                    subprocess.run(cmd, check=False)
                except Exception as e:
                    print("❌ validate-Fehler:", e)
                pause()

            if ch == 3:
                # einfacher Backtest-Aufruf
                try:
                    from modules.backtest.sma import run_backtest
                except Exception as e:
                    print(f"❌ Import-Fehler: {e}"); pause(); continue
                csvp = ask("Clean-CSV (z. B. data_clean/stock_AAPL_5mins.csv)",
                           "data_clean/stock_AAPL_5mins.csv")
                fast = int(ask("SMA fast", "10"))
                slow = int(ask("SMA slow", "20"))
                execm = ask("Exec (close/next_open)", "close")
                try:
                    from pathlib import Path
                    run_backtest(Path(csvp), fast=fast, slow=slow, exec_mode=execm)
                except Exception as e:
                    print("❌ Backtest-Fehler:", e)
                pause()

            if ch == 4:
                try:
                    from modules.diag.sanity import main as sanity_main
                    sanity_main()
                except SystemExit:
                    pass
                except Exception as e:
                    print("❌ Sanity-Fehler:", e)
                pause()

            if ch == 5:
                try:
                    from modules.diag.status import main as status_main
                    status_main()
                except Exception as e:
                    print("❌ IBKR-Status-Fehler:", e)
                pause()

            if ch == 6:
                try:
                    from modules.diag.status import symbol_scan_cli
                    symbol_scan_cli()
                except Exception as e:
                    print("❌ Symbol-Scan-Fehler:", e)
                pause()

            if ch == 7:
                try:
                    from modules.diag.pnl import pnl_dashboard
                    pnl_dashboard(runtime_sec=20)
                except Exception as e:
                    print("❌ PnL-Fehler:", e)
                pause()

        except KeyboardInterrupt:
            return

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
            print("H) Hinweise an/aus")
            print("0) Beenden")
            raw = input("Auswahl: ").strip()
            if raw.lower() in ("q","quit","x","exit"):
                break
            if raw.lower() in ("h",):
                SHOW_HINTS = not SHOW_HINTS
                continue
            if raw == "1":
                automation_menu()
            elif raw == "2":
                tradehub_menu()
            elif raw == "3":
                tools_menu()
            elif raw == "0":
                break
            else:
                print("Bitte 0–3 oder H/Q.")
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    main_menu()

