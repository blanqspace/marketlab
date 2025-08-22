import time
import threading
import os
import csv
import math
from datetime import datetime
from ib_insync import Forex
from shared.ibkr_client import IBKRClient
from shared.logger import get_logger

# ---- Optionale Farben sicher behandeln -------------------------------------
HAS_COLOR = False
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    HAS_COLOR = True
except Exception:
    class _S:
        RESET_ALL = ""
    Fore = Style = _S()

logger = get_logger("live_fx_dashboard", log_to_console=False)
stop_flag = False

# ---- Utils ------------------------------------------------------------------
def input_listener():
    global stop_flag
    while True:
        if input().strip().lower() == "q":
            stop_flag = True
            break

def clear_line():
    print("\r\033[2K", end="")

def export_to_csv(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, mode="a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(["timestamp", "bid", "ask", "spread"])
        writer.writerow(row)

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

# ---- Marktdaten-Strategien --------------------------------------------------
def _subscribe_with_fallback(ib, contract, timeout=2.5):
    """
    Versucht nacheinander: Live(1) → Delayed(3) → Delayed-Frozen(4).
    Gibt (ticker, md_type) zurück; md_type ∈ {0,1,3,4}.
    """
    # Live
    try:
        ib.reqMarketDataType(1)
    except Exception:
        pass
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 1

    # Aufräumen + Delayed
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

    # Aufräumen + Delayed-Frozen (einige Konten liefern so eher Werte)
    try:
        ib.cancelMktData(t)
    except Exception:
        pass
    ib.sleep(0.1)

    ib.reqMarketDataType(4)  # Delayed-Frozen
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 4

    return t, 0

# ---- Hauptanzeige -----------------------------------------------------------
def _snapshot_poll(ib, contract, timeout=2.0):
    """
    Holt einmalig Bid/Ask per Snapshot (Polling).
    """
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

def display_live_feed(symbol="EURUSD", duration=60, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=1.5):
    """
    Falls weder Live noch Delayed Updates liefern, wird automatisch auf Snapshot-Polling umgestellt.
    """
    global stop_flag
    stop_flag = False  # Reset bei erneutem Aufruf

    # Vorab-Check: Contract existiert?
    ibkr_probe = IBKRClient(module="fx_probe", task=f"check_{symbol}")
    ib_probe = ibkr_probe.connect()
    try:
        if not ib_probe.reqContractDetails(Forex(symbol)):
            print(f"❌ Keine Marktdaten für {symbol}")
            return
    finally:
        ibkr_probe.disconnect()

    print(f"🌐 Starte Live-Dashboard für {symbol} (Dauer: {duration}s, Abbruch: 'q')")
    threading.Thread(target=input_listener, daemon=True).start()

    ibkr = IBKRClient(module="fx_live", task=f"dashboard_{symbol}")
    ib = ibkr.connect()

    ticker = None
    mode = "stream"   # 'stream' oder 'snapshot'
    md_type = 0       # 1=Live, 3=Delayed

    try:
        contract = Forex(symbol)
        ticker, md_type = _subscribe_with_fallback(ib, contract, timeout=2.5)

        header_note = "(Live)" if md_type == 1 else "(Delayed)" if md_type == 3 else "(keine Daten)"
        print(f"\n📡 FX Live Dashboard – klassisch  {header_note}")
        print("-" * 60)
        print("Zeit     , Bid         | Ask         → Spread")
        print("-" * 60)
        print("Drücke 'q' + Enter zum Beenden")
        print("")
        print("Drücke 'q' + Enter zum Beenden")

        prev_bid = prev_ask = None
        bid_flash_end = ask_flash_end = 0.0
        log_path = os.path.join("logs", f"{symbol.lower()}_{datetime.now().date()}.csv")
        start_time = time.time()
        last_update_time = time.time()
        warned_stream_dead = False

        # Falls Stream komplett leer bleibt, direkt in Snapshot-Modus wechseln
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
                # Snapshot-Polling
                bid, ask = _snapshot_poll(ib, contract, timeout=2.0)
                if mode == "snapshot":
                    # Begrenze Polling-Frequenz
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

            # Stream-Watchdog → Snapshot-Fallback
            if mode == "stream" and (now - last_update_time) > no_update_watchdog:
                if not warned_stream_dead:
                    print("\n⚠️  Keine Stream-Updates. Ursache: konkurrierende Live-Sitzung (10197) "
                          "oder kein Abo. Schalte auf Snapshot-Modus um.")
                    warned_stream_dead = True
                mode = "snapshot"
                # Stream sauber abbestellen
                try:
                    if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                        ib.cancelMktData(ticker)
                except Exception:
                    pass
                # Hinweis in Kopfzeile aktualisieren
                print("ℹ️  Datenquelle: verzögerte Snapshots.")
                continue

            if updated:
                last_update_time = now
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # CSV: leere Felder statt 'nan'
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

                # Cursor 2 Zeilen hoch (Datenzeile + Hinweiszeile)
                print("\033[2F", end="")
                clear_line()
                ts_short = datetime.now().strftime("%H:%M:%S")
                bid_txt = _flash(_fmt_price(bid), now < bid_flash_end)
                ask_txt = _flash(_fmt_price(ask), now < ask_flash_end)
                pips, unit = _pip_info(spread)
                spread_txt = "-" if spread is None else f"{spread:.5f}"
                print(f"{ts_short}, Bid: {bid_txt} | Ask: {ask_txt} → Spread: {spread_txt} ({pips} {unit})")
                clear_line()
                src = "Live" if (mode == "stream" and md_type == 1) else "Delayed Stream" if (mode == "stream" and md_type == 3) else "Snapshot (Delayed)"
                print(f"Drücke 'q' + Enter zum Beenden  • Quelle: {src}")

        print("\n🛑 Live-Dashboard beendet.")
    finally:
        try:
            if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                ib.cancelMktData(ticker)
        except Exception:
            pass
        ibkr.disconnect()

if __name__ == "__main__":
    # Hinweis: Schließe andere TWS/Gateway-Sitzungen, wenn du Live erwartest.
    display_live_feed(symbol="EURUSD", duration=120, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=1.5)
