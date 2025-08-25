# live_fx_viewer.py
import os
import sys
import csv
import math
import time
import threading
import logging
import locale
from datetime import datetime

from ib_insync import Forex, Stock, util

from shared.ibkr.ibkr_client import IBKRClient
from shared.symbols.symbol_status_cache import load_cached_symbols
from shared.utils.logger import get_logger

# ── Logging & Konsole beruhigen ──────────────────────────────────────────────
logging.getLogger('ib_insync').setLevel(logging.ERROR)
logging.getLogger('ib_insync.wrapper').setLevel(logging.ERROR)
logging.getLogger('ibapi').setLevel(logging.ERROR)
util.logToConsole(False)  # IB/ib_insync Konsolen-Output stummschalten

# ── Deutsche Zeitdarstellung (failsafe) ─────────────────────────────────────
try:
    locale.setlocale(locale.LC_TIME, 'de_DE.UTF-8')
except Exception:
    pass

logger = get_logger("live_viewer", log_to_console=False)
stop_flag = {"value": False}


# ── Kleine Helfer ────────────────────────────────────────────────────────────
def _fmt_dt(ts: datetime) -> str:
    try:
        return ts.strftime("%d.%m.%Y %H:%M:%S")
    except Exception:
        return ts.isoformat(sep=' ', timespec='seconds')


def input_listener(flag):
    while True:
        if input().strip().lower() == "q":
            flag["value"] = True
            break


def clear_line():
    print("\r\033[2K", end="")


def export_to_csv(path, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path)
    with open(path, mode="a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if write_header:
            w.writerow(["timestamp", "bid", "ask", "spread"])
        w.writerow(row)


def _to_float(x):
    if x is None:
        return None
    try:
        if isinstance(x, float) and math.isnan(x):
            return None
        return float(x)
    except (ValueError, TypeError):
        return None


def _fmt_price(x):
    return f"{x:.5f}" if x is not None else "-"


def _pip_info(spread):
    if spread is None:
        return "-", "Pips"
    pips = round(spread * 10000, 1)
    unit = "Pip" if abs(pips) == 1 else "Pips"
    return pips, unit


def _stock_spread_info(spread):
    if spread is None:
        return "-", "Cent"
    cents = round(spread * 100, 2)  # USD -> Cent
    return cents, "Cent"


def _format_spread_text(spread, sym_type: str):
    if spread is None:
        return "-", "-"
    if (sym_type or "").lower() == "stock":
        cents, unit = _stock_spread_info(spread)
        return f"{spread:.5f} USD", f"{cents} {unit}"
    pips, unit = _pip_info(spread)
    return f"{spread:.5f}", f"{pips} {unit}"


def _has_quotes(ticker):
    return (ticker is not None) and (
        _to_float(getattr(ticker, "bid", None)) is not None
        or _to_float(getattr(ticker, "ask", None)) is not None
    )


def _snapshot_poll(ib, contract, timeout=2.0):
    try:
        t = ib.reqMktData(contract, "", True, False)
        ib.sleep(timeout)
        bid = _to_float(getattr(t, "bid", None))
        ask = _to_float(getattr(t, "ask", None))
        try:
            ib.cancelMktData(t)
        except Exception:
            pass
        return bid, ask
    except Exception:
        return None, None


def _subscribe_with_fallback(ib, contract, timeout=2.5):
    # 1) Live
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
    # 2) Delayed
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
    # 3) Frozen
    ib.reqMarketDataType(4)
    t = ib.reqMktData(contract, "", False, False)
    ib.sleep(timeout)
    if _has_quotes(t):
        return t, 4
    return t, 0


def _install_quiet_error_handler(ib):
    """
    Unterdrückt bekannte, laute, aber harmlose IB-Fehler:
    - 10089 (kein Live-Abo; delayed/frozen ok)
    - 'cancelMktData' / 'No reqId found' (Race beim Canceln)
    Andere Fehler werden kompakt gezeigt.
    """
    def on_error(reqId, code, msg, _):
        text = (msg or "")
        if code in (10089,):
            return
        if "cancelMktData" in text or "No reqId found" in text:
            return
        print(f"IB[{code}]: {text}")
    try:
        ib.errorEvent.clear()
    except Exception:
        pass
    ib.errorEvent += on_error


# ── Symbole (nicht-interaktiv) ──────────────────────────────────────────────
def _normalize_symbols(raw):
    """
    raw: dict[str, dict] ODER list[str]
    → dict[symbol] = {'type': 'forex'|'stock'|'future', ...}
    """
    if isinstance(raw, dict):
        return raw
    out = {}
    if isinstance(raw, list):
        for s in raw:
            st = "forex" if ("/" in s or "USD" in s or len(s) == 6) else "stock"
            out[s] = {"type": st}
    return out


def load_or_search_symbols():
    """
    Nicht-interaktive Symbolquelle:
    - Versucht Cache (data/available_symbols.json)
    - Fällt auf Default-Liste zurück
    """
    try:
        cached = load_cached_symbols()  # {"timestamp": "...", "symbols": {...}}
        if cached and isinstance(cached, dict):
            symbols = cached.get("symbols") or {}
            symbols = _normalize_symbols(symbols)
            if symbols:
                ts = cached.get("timestamp", "-")
                print(f"📦 Symbolliste aus Cache ({ts}):")
                for s, info in symbols.items():
                    typ = info.get("type", "?")
                    print(f"  - {s:<8} ({typ})")
                return symbols
    except Exception:
        pass

    # Fallback: kompakte Defaults
    defaults = {
        "EURUSD": {"type": "forex"},
        "USDJPY": {"type": "forex"},
        "AAPL":   {"type": "stock"},
        "SPY":    {"type": "stock"},
    }
    print("📦 Symbolliste (Default, kein Cache gefunden):")
    for s, info in defaults.items():
        print(f"  - {s:<8} ({info['type']})")
    return defaults


def make_contract(symbol: str, sym_type: str):
    t = (sym_type or "").lower()
    if t == "forex":
        return Forex(symbol)
    if t == "stock":
        return Stock(symbol, "SMART", "USD")
    raise ValueError(f"Typ '{sym_type}' wird im Live-Viewer derzeit nicht unterstützt (Futures).")


# ── Hauptfunktion ───────────────────────────────────────────────────────────
def display_live_feed(symbol="EURUSD", sym_type="forex", duration=60, flash_duration=1.0,
                      no_update_watchdog=5.0, snapshot_interval=2.0):
    stop_flag["value"] = False

    ibkr = IBKRClient(module="fx_live", task=f"live_{symbol}")
    ib = ibkr.connect()
    _install_quiet_error_handler(ib)

    try:
        contract = make_contract(symbol, sym_type)
        if not ib.reqContractDetails(contract):
            print(f"❌ Keine Marktdaten für {symbol} ({sym_type})")
            return

        # Abo versuchen
        ticker, md_type = _subscribe_with_fallback(ib, contract, timeout=2.5)
        header_note = "Live" if md_type == 1 else "Delayed" if md_type == 3 else "keine Daten"

        print("\n" + "─" * 64)
        print(f"📡 {symbol}  ·  Typ: {sym_type}  ·  Quelle: {header_note}  ·  Start: {_fmt_dt(datetime.now())}")
        print("   Drücke 'q' + Enter zum Beenden")
        print("─" * 64)

        if md_type in (3, 4):
            print("ℹ️  Hinweis: Kein Live-Abo verfügbar (IBKR 10089). Zeige verzögerte/frozen Marktdaten.")
        print("⏳ Warte auf erste Daten … (Drücke jederzeit 'q' + Enter zum Beenden)")
        print("Zeit       | Bid        | Ask        | Spread (absolut)  | Spread (einheit)")
        print("-----------+------------+------------+-------------------+-----------------")

        threading.Thread(target=input_listener, args=(stop_flag,), daemon=True).start()

        # Nur Live streamen; Delayed/Frozen sofort als Snapshot behandeln
        mode = "stream" if md_type == 1 else "snapshot"
        prev_bid = prev_ask = None
        bid_flash_end = ask_flash_end = 0.0
        log_path = os.path.join("logs", f"{symbol.lower()}_{datetime.now().date()}.csv")
        start_time = time.time()
        last_update_time = time.time()
        warned_stream_dead = False
        first_tick_deadline = time.time() + 8.0  # max. 8s auf erste Daten warten

        while not stop_flag["value"] and (time.time() - start_time < duration):
            now = time.time()

            if mode == "stream":
                ib.sleep(0.8)  # ruhiger
                bid = _to_float(getattr(ticker, "bid", None))
                ask = _to_float(getattr(ticker, "ask", None))
            else:
                bid, ask = _snapshot_poll(ib, contract, timeout=2.0)
                time.sleep(snapshot_interval)

            # Frühzeitiger Abbruch ohne Daten
            if (prev_bid is None and prev_ask is None) and (bid is None and ask is None) and (time.time() > first_tick_deadline):
                print("⚠️  Keine verwertbaren Daten erhalten. Mögliche Gründe:")
                print("   • Markt geschlossen (z. B. US-Aktie am Wochenende)")
                print("   • Kein Realtime-Abo (IBKR-Fehler 10089) – nur verzögerte/frozen Daten")
                print("   • Symbol erfordert genaueren Kontrakt (bei Futures)")
                print("👉 Tipp: Teste zuerst FX (EURUSD, USDJPY) oder starte zu Marktzeiten.")
                return

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

            # Watchdog: falls im Stream keine Updates → Snapshot
            if mode == "stream":
                if updated:
                    last_update_time = now
                if (now - last_update_time) > no_update_watchdog:
                    if not warned_stream_dead:
                        print("↪️  Keine Live-Updates → wechsle auf Snapshot-Modus (verzögert).")
                        warned_stream_dead = True
                    mode = "snapshot"
                    try:
                        if ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                            ib.cancelMktData(ticker)
                    except Exception:
                        pass
                    continue

            if updated:
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
                logger.info("%s | %s | BID: %s | ASK: %s | SPREAD: %s", timestamp, symbol, bid, ask, spread)

                ts_short = datetime.now().strftime("%H:%M:%S")
                bid_txt = _fmt_price(bid)
                ask_txt = _fmt_price(ask)
                spread_abs, spread_unit = _format_spread_text(spread, sym_type)
                line = f"{ts_short:>8} | {bid_txt:>10} | {ask_txt:>10} | {spread_abs:>17} | {spread_unit:>15}"
                print(line)
                clear_line()
                src = "Live" if (mode == "stream" and md_type == 1) else "Snapshot"
                print(f"⏱️  {_fmt_dt(datetime.now())}  ·  Quelle: {src}  ·  Abbruch: q")

        print("\n🛑 Live-Dashboard beendet.")
    finally:
        try:
            if 'ticker' in locals() and ticker is not None and getattr(ticker, 'tickerId', None) is not None:
                ib.cancelMktData(ticker)
        except Exception:
            pass
        ibkr.disconnect()


# ── Einstiegspunkt ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    symbols = load_or_search_symbols()
    if not symbols:
        print("❌ Keine Symbole verfügbar.")
        raise SystemExit(1)

    print("\n📋 Verfügbare Symbole:")
    symbol_list = list(symbols.keys())
    for idx, sym in enumerate(symbol_list, 1):
        typ = symbols[sym].get("type", "-")
        print(f"{idx}. {sym} ({typ})")

    while True:
        try:
            sel = int(input("\n🔢 Wähle ein Symbol durch Nummer: "))
            if 1 <= sel <= len(symbol_list):
                chosen = symbol_list[sel - 1]
                break
        except ValueError:
            pass
        except KeyboardInterrupt:
            print("\n❌ Abgebrochen.")
            raise SystemExit(0)
        print("❌ Ungültige Eingabe.")

    chosen_type = symbols[chosen].get("type", "forex")
    if chosen_type.lower() == "future":
        print("❌ Futures werden hier noch nicht unterstützt (benötigen konkreten Kontrakt).")
        raise SystemExit(2)

    display_live_feed(
        symbol=chosen,
        sym_type=chosen_type,
        duration=120,
        flash_duration=0.5,
        no_update_watchdog=5.0,
        snapshot_interval=2.5
    )
