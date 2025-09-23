# main.py
from __future__ import annotations
import sys, subprocess
from pathlib import Path

# Projekt-Root auf sys.path
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.trade.menu import main_menu as trade_menu
from modules.data.ingest import ingest_one

PY = sys.executable  # z. B. ...\Python313\python.exe

# ── Navigation ─────────────────────────────────────────────────────────────
class GoBack(Exception): ...
class GoMain(Exception): ...
class QuitApp(Exception): ...

def _check_nav(raw: str):
    s = (raw or "").strip().lower()
    if s in ("0","b","back"): raise GoBack()
    if s in ("m","menu"):     raise GoMain()
    if s in ("q","quit","x","exit"): raise QuitApp()

def ask(label: str, default: str | None = None) -> str:
    raw = input(f"{label}{f' [{default}]' if default is not None else ''}: ").strip()
    if raw == "" and default is not None:
        return default
    _check_nav(raw)
    return raw

def ask_int(label: str, default: int | None = None, valid: list[int] | None=None) -> int:
    while True:
        try:
            val = int(ask(label, str(default) if default is not None else None))
            if valid and val not in valid:
                print(f"Bitte eine der Optionen {valid} wählen."); continue
            return val
        except (GoBack, GoMain, QuitApp): raise
        except Exception:
            print("Bitte eine Zahl eingeben.")

def header(title: str):
    print("\n" + "-"*70)
    print(title)
    print("-"*70)
    print("Hinweis: 0=Zurück  M=Menü  Q=Beenden")

# ── DATA ───────────────────────────────────────────────────────────────────
def data_menu():
    while True:
        try:
            header("Daten – Abruf & Prüfung")
            print("1) Historie abrufen (Fetch → Clean → Manifest)")
            print("2) CSV prüfen (Duplikate, Gaps)")
            print("0) Zurück")
            ch = ask_int("Auswahl", valid=[0,1,2])
            if ch == 0: return
            if ch == 1: data_ingest_one()
            if ch == 2: data_validate_csv()
        except GoBack: return
        except GoMain: return
        except QuitApp: sys.exit(0)

def data_ingest_one():
    while True:
        try:
            header("Daten • Historie abrufen")
            sym      = ask("Symbol", "AAPL").upper()
            asset_no = ask_int("Asset  1=Aktie  2=Forex", 1, [1,2])
            asset    = "stock" if asset_no==1 else "forex"
            duration = ask("Zeitraum (z. B. 5 D / 1 Y)", "5 D")
            barsize  = ask("Bar-Größe (z. B. 5 mins / 1 day)", "5 mins")
            what     = ask("Datenart (TRADES/MIDPOINT/BID/ASK)", "TRADES").upper()
            rth      = ask("Nur Handelszeit (RTH)? (j/n)", "n").lower().startswith("j")
            overwrite= ask("RAW überschreiben? (j/n)", "n").lower().startswith("j")

            man = ingest_one(sym, asset, duration, barsize, what, rth, overwrite)
            print("\n✓ Fertig.")
            print("RAW:   ", man.get("raw"))
            print("CLEAN: ", man.get("clean"))
            print("MANIF.:", man.get("manifest"))
            _ = ask("Enter=weiter", "")
            return
        except (GoBack, GoMain, QuitApp): raise
        except Exception as e:
            print("❌", e); _ = ask("Enter=zurück", ""); return

def data_validate_csv():
    while True:
        try:
            header("Daten • CSV prüfen")
            fpath = ask("CSV-Pfad", "data/stock_AAPL_5mins.csv")
            bars  = ask("Bar-Größe (für Gap-Check)", "5 mins")
            out   = ask("Gesäuberte Ausgabe-Datei (leer=keine)", "")
            args = [PY, str(ROOT/"modules"/"data"/"validate.py"), fpath, "--barsize", bars]
            if out: args += ["--out", out]
            print("→", " ".join(args))
            subprocess.run(args, check=False)
            _ = ask("Enter=weiter", "")
            return
        except (GoBack, GoMain, QuitApp): raise

# ── BACKTEST ───────────────────────────────────────────────────────────────
def backtest_menu():
    while True:
        try:
            header("Backtests")
            print("1) SMA-Strategie testen")
            print("0) Zurück")
            ch = ask_int("Auswahl", valid=[0,1])
            if ch == 0: return
            if ch == 1: bt_sma()
        except GoBack: return
        except GoMain: return
        except QuitApp: sys.exit(0)

def bt_sma():
    while True:
        try:
            header("Backtest • SMA")
            csv   = ask("CSV (bereinigt)", "data_clean/stock_AAPL_5mins.csv")
            fast  = ask("SMA schnell (z. B. 10)", "10")
            slow  = ask("SMA langsam (z. B. 20)", "20")
            execm = ask("Ausführung: close / next_open", "close")
            spread= ask("Spread pro Trade", "0.0")
            slip  = ask("Slippage", "0.0")
            fee   = ask("Gebühr fix", "0.0")
            cash  = ask("Start-Kapital", "100000")
            risk  = ask("Kapitalanteil (0..1)", "1.0")
            eqout = ask("Equity-CSV speichern (leer=nein)", "")

            args = [PY, str(ROOT/"modules"/"backtest"/"sma.py"), csv,
                    "--fast", fast, "--slow", slow, "--exec", execm,
                    "--spread", spread, "--slippage", slip, "--fee", fee,
                    "--cash", cash, "--risk", risk]
            if eqout: args += ["--equity-out", eqout]

            print("→", " ".join(args))
            subprocess.run(args, check=False)
            _ = ask("Enter=weiter", "")
            return
        except (GoBack, GoMain, QuitApp): raise

# ── Diagnose-Funktionen DIREKT im Hauptmenü ────────────────────────────────
def run_sanity_check():
    from modules.diag.sanity import main as sanity_main
    sanity_main()
    _ = ask("Enter=weiter", "")

def run_ibkr_status():
    from modules.diag.status import main as status_main
    status_main()
    _ = ask("Enter=weiter", "")

def run_symbol_scan():
    from modules.diag.status import symbol_scan_cli
    symbol_scan_cli()
    _ = ask("Enter=weiter", "")

def run_pnl_dashboard():
    from modules.diag.pnl import pnl_dashboard
    pnl_dashboard(runtime_sec=30, csv_out=True, show_positions=True)
    _ = ask("Enter=weiter", "")

# ── ROOT ───────────────────────────────────────────────────────────────────
def main():
    while True:
        try:
            header("Hauptmenü")
            # Reihenfolge: Daten vor Handeln
            print("1) Daten (Abruf & Prüfung)")
            print("2) Handeln (Trade Hub)")
            print("3) Backtests")
            # vormals „Diagnose“
            print("4) Sanity-Check")
            print("5) IBKR-Status")
            print("6) Symbol-Scan (Paper-Berechtigungen)")
            print("7) PnL-Dashboard (Paper/LIVE)")
            print("0) Beenden")
            ch = ask_int("Auswahl", valid=[0,1,2,3,4,5,6,7])
            if ch == 0: break
            if ch == 1: data_menu()
            if ch == 2: trade_menu()
            if ch == 3: backtest_menu()
            if ch == 4: run_sanity_check()
            if ch == 5: run_ibkr_status()
            if ch == 6: run_symbol_scan()
            if ch == 7: run_pnl_dashboard()
        except GoMain:  continue
        except GoBack:  continue
        except QuitApp: break

if __name__ == "__main__":
    main()
