from shared.symbols.symbol_status_cache import load_cached_symbols, save_available_symbols
from shared.ibkr.ibkr_symbol_status import check_symbol_availability
import pprint

def choose_symbol_source():
    """
    Fragt Nutzer: Alte Liste verwenden oder neue suchen?
    Gibt die gültige Symbol-Liste zurück.
    """
    cached = load_cached_symbols()
    use_cache = False

    if cached:
        print("📦 Gefundene Symbol-Liste vom", cached["timestamp"])
        pprint.pprint(cached["symbols"])
        print("\n💡 Möchtest du diese Liste verwenden oder neue Verfügbarkeit prüfen?")
        print("[1] Alte Liste verwenden")
        print("[2] Neue Symbolverfügbarkeit testen")

        while True:
            choice = input("Auswahl (1 oder 2): ").strip()
            if choice == "1":
                use_cache = True
                break
            elif choice == "2":
                break

    if use_cache:
        print("✅ Verwende gespeicherte Symbol-Liste.")
        return cached["symbols"]
    
    # Neue Suche
    print("🔍 Starte neue Verfügbarkeitsprüfung...")
    new_results = check_symbol_availability()
    print("💾 Speichere neue Ergebnisse...")
    save_available_symbols(new_results)
    return new_results
