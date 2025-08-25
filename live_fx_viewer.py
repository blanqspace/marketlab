import time
import threading
import os
import csv
import math
import json  # <- hat gefehlt
from datetime import datetime
from ib_insync import Forex

from shared.ibkr.ibkr_client import IBKRClient
from shared.symbols.symbol_selector import choose_symbol_source
from shared.ibkr.ibkr_symbol_status import check_symbol_availability
from shared.utils.logger import get_logger

# ---- Optionale Farben ------------------------------------------------------
HAS_COLOR = False
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except Exception:
    class _S:
        RESET_ALL = ""
    Fore = Style = _S()

# ---- Konstante -------------------------------------------------------------
SYMBOL_CACHE_PATH = os.path.join("runtime", "symbol_availability.json")

# ---- Logger ----------------------------------------------------------------
logger = get_logger("live_fx_dashboard", log_to_console=False)
stop_flag = False

# ---- Eingabe & Anzeige -----------------------------------------------------
def input_listener():
    global stop_flag
    while True:
        if input().strip().lower() == "q":
            stop_flag = True
            break

def clear_line():
    print("\r\033[2K", end="")

# ---- Datei Export ----------------------------------------------------------
def export_to_csv(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, mode="a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "bid", "ask", "spread"])
        writer.writerow(row)

# ---- Hilfsfunktionen -------------------------------------------------------
def _to_float(x):
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
        return float(x)
    except Exception:
        return None

def _fmt_price(x):
    return f"{x:.5f}" if x is not None else "-"

def _pip_info(spread):
    if spread is None:
        return "-", "Pips"
    pips = round(spread * 10000, 1)
    unit = "Pip" if abs(pips) == 1 else "Pips"
    return pips, unit

def _flash(text, active):
    if not active:
        return text
    if HAS_COLOR:
        return f"{Fore.YELLOW}⚡ {text}{Style.RESET_ALL}"
    return f"⚡ {text}"

def _has_quotes(ticker):
    return (ticker is not None) and (
        _to_float(ticker.bid) is not None or _to_float(ticker.ask) is not None
    )

def _snapshot_poll(ib, contract, timeout=2.0):
    try:
        ticker = ib.reqMktData(contract, "", True, False)
        ib.sleep(timeout)
        bid = _to_float(ticker.bid)
        ask = _to_float(ticker.ask)
        try:
            ib.cancelMktData(ticker)
        except Exception:
            pass
        return bid, ask
    except Exception:
        return None, None

def _subscribe_with_fallback(ib, contract, timeout=2.5):
    try:
        ib.reqMarketDataType(1)
    except Exception:
        pass
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 1
    try:
        ib.cancelMktData(t)
    except Exception:
        pass
    ib.sleep(0.1)

    ib.reqMarketDataType(3)
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 3
    try:
        ib.cancelMktData(t)
    except Exception:
        pass
    ib.sleep(0.1)

    ib.reqMarketDataType(4)
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 4
    return t, 0

# ---- Symbolmanagement ------------------------------------------------------
def load_or_search_symbols():
    """Wrapper function that uses the symbol selector module"""
    return choose_symbol_source()

# ---- Hauptfunktion ---------------------------------------------------------
def display_live_feed(symbol="EURUSD", duration=60, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=1.5):
    global stop_flag
    stop_flag = False

    ibkr_probe = IBKRClient(module="fx_probe", task=f"check_{symbol}")
    ib_probe = ibkr_probe.connect()
    try:
        if not ib_probe.reqContractDetails(Forex(symbol)):
            print(f"❌ Keine Marktdaten für {symbol}")
            return
    finally:
        ibkr_probe.disconnect()

    print(f"\n🌐 Starte Live-Dashboard für {symbol} (Dauer: {duration}s, Abbruch: 'q')")
    threading.Thread(target=input_listener, daemon=True).start()

    ibkr = IBKRClient(module="fx_live", task=f"dashboard_{symbol}")
    ib = ibkr.connect()

    ticker = None
    mode = "stream"
    md_type = 0

    try:
        contract = Forex(symbol)
        ticker, md_type = _subscribe_with_fallback(ib, contract, timeout=2.5)
        header_note = "(Live)" if md_type == 1 else "(Delayed)" if md_type == 3 else "(keine Daten)"

        print(f"\n📡 FX Live Dashboard – klassisch  {header_note}")
        print("-" * 60)
        print("Zeit     , Bid         | Ask         → Spread")
        print("-" * 60)
        print("Drücke 'q' + Enter zum Beenden\n")

        prev_bid = prev_ask = None
        bid_flash_end = ask_flash_end = 0.0
        log_path = os.path.join("logs", f"{symbol.lower()}_{datetime.now().date()}.csv")
        start_time = time.time()
        last_update_time = time.time()
        warned_stream_dead = False

        if md_type == 0:
            mode = "snapshot"
            print("ℹ️  Wechsel auf Snapshot-Modus (weder Live noch Delayed Stream verfügbar).")

        while not stop_flag and (time.time() - start_time < duration):
            now = time.time()

            if mode == "stream":
                ib.sleep(0.3)
                bid = _to_float(ticker.bid)
                ask = _to_float(ticker.ask)
            else:
                bid, ask = _snapshot_poll(ib, contract, timeout=2.0)
                time.sleep(snapshot_interval)

            spread = (ask - bid) if (bid is not None and ask is not None) else None
            updated = False
            if bid != prev_bid:
                bid_flash_end = now + flash_duration
                prev_bid = bid
                updated = True
            if ask != prev_ask:
                ask_flash_end = now + flash_duration
                prev_ask = ask
                updated = True

            if mode == "stream" and (now - last_update_time) > no_update_watchdog:
                if not warned_stream_dead:
                    print("\n⚠️  Keine Stream-Updates. Ursache: kein Abo oder konkurrierende Sitzung. Wechsle zu Snapshots.")
                    warned_stream_dead = True
                mode = "snapshot"
                try:
                    if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                        ib.cancelMktData(ticker)
                except Exception:
                    pass
                print("ℹ️  Datenquelle: verzögerte Snapshots.")
                continue

            if updated:
                last_update_time = now
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                export_to_csv(
                    log_path,
                    [
                        timestamp,
                        f"{bid:.5f}" if bid is not None else "",
                        f"{ask:.5f}" if ask is not None else "",
                        f"{spread:.5f}" if spread is not None else ""
                    ]
                )
                logger.info(f"{timestamp} | {symbol} | BID: {bid} | ASK: {ask} | SPREAD: {spread}")
                print("\033[2F", end="")
                clear_line()
                ts_short = datetime.now().strftime("%H:%M:%S")
                bid_txt = _flash(_fmt_price(bid), now < bid_flash_end)
                ask_txt = _flash(_fmt_price(ask), now < ask_flash_end)
                pips, unit = _pip_info(spread)
                spread_txt = "-" if spread is None else f"{spread:.5f}"
                print(f"{ts_short}, Bid: {bid_txt} | Ask: {ask_txt} → Spread: {spread_txt} ({pips} {unit})")
                clear_line()
                src = "Live" if (mode == "stream" and md_type == 1) else "Delayed Stream" if (mode == "stream") else "Snapshot"
                print(f"Drücke 'q' + Enter zum Beenden  • Quelle: {src}")

        print("\n🛑 Live-Dashboard beendet.")
    finally:
        try:
            if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                ib.cancelMktData(ticker)
        except Exception:
            pass
        ibkr.disconnect()

# ---- Einstiegspunkt --------------------------------------------------------
if __name__ == "__main__":
    all_symbols = load_or_search_symbols()
    if not all_symbols:
        print("❌ Keine Symbole verfügbar.")
        exit(1)

    print("\n📋 Verfügbare Symbole:")
    symbol_list = list(all_symbols.keys())
    for idx, sym in enumerate(symbol_list, 1):
        print(f"{idx}. {sym} ({all_symbols[sym]['type']})")

    while True:
        try:
            sel = int(input("\n🔢 Wähle ein Symbol durch Nummer: "))
            if 1 <= sel <= len(symbol_list):
                chosen = symbol_list[sel - 1]
                break
        except Exception:
            pass
        print("❌ Ungültige Eingabe.")

    display_live_feed(symbol=chosen, duration=120, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=1.5)
