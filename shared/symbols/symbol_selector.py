from typing import Dict, Tuple, List
import pprint

from shared.symbols.symbol_status_cache import load_cached_symbols, save_available_symbols
from shared.ibkr.ibkr_symbol_status import check_symbol_availability, DEFAULT_SYMBOLS
from shared.ibkr.ibkr_client import IBKRClient


def _probe_symbols(pairs: List[Tuple[str, str]]) -> Dict[str, Dict]:
    """
    pairs: Liste von (symbol, type) mit type in {"forex","stock","future"}
    Rückgabeformat:
      { "EURUSD": {"type":"forex","live":True},
        "AAPL":   {"type":"stock","historical":True,"delayed":True}, ... }
    """
    results: Dict[str, Dict] = {}
    ibkr = IBKRClient(module="availability", task="scan_symbols")
    ib = ibkr.connect()
    try:
        for sym, typ in pairs:
            status = check_symbol_availability(ib, sym, typ)  # "✅ Live" | "🟡 Delayed" | "❌ Kein Zugriff"
            info = {"type": typ}
            if "Live" in status:
                info["live"] = True
            elif "Delayed" in status:
                info["historical"] = True
                info["delayed"] = True
            results[sym] = info
    finally:
        ibkr.disconnect()
    return results


def choose_symbol_source() -> Dict[str, Dict]:
    """
    Interaktiv:
    - Wenn Cache vorhanden: Nutzer fragt, ob alte Liste genutzt werden soll.
    - Sonst: DEFAULT_SYMBOLS testen und Ergebnis speichern.
    Rückgabe: dict[symbol] -> {"type": "...", ("live"| "historical"/"delayed")}
    """
    cached = load_cached_symbols()
    if cached and isinstance(cached, dict) and "symbols" in cached:
        print("📦 Gefundene Symbol-Liste vom", cached.get("timestamp", "-"))
        pprint.pprint(cached["symbols"])
        print("\n💡 Möchtest du diese Liste verwenden oder neue Verfügbarkeit prüfen?")
        print("[1] Alte Liste verwenden")
        print("[2] Neue Symbolverfügbarkeit testen")

        while True:
            choice = input("Auswahl (1 oder 2): ").strip()
            if choice == "1":
                print("✅ Verwende gespeicherte Symbol-Liste.")
                return cached["symbols"]
            if choice == "2":
                break
            print("❌ Ungültige Eingabe. Bitte 1 oder 2.")

    print("🔍 Starte neue Verfügbarkeitsprüfung...")
    results = _probe_symbols(DEFAULT_SYMBOLS)
    print("💾 Speichere neue Ergebnisse...")
    save_available_symbols(results)
    return results
