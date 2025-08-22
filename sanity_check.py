# sanity_check.py
import sys, json
from pathlib import Path
from shared.logger import get_logger
from shared.file_utils import load_json_file, write_json_file

log = get_logger("sanity", log_to_console=True)

def main(fix=False):
    cfg = Path("config")
    active = set(load_json_file(cfg/"active_symbols.json").get("symbols", []))
    tasks = load_json_file(cfg/"symbol_tasks.json", expected_type=list)
    avail = load_json_file(cfg/"symbol_availability.json")
    ids = load_json_file(cfg/"client_ids.json")
    startup = load_json_file(cfg/"startup.json").get("modules", {})
    # 1) Symbole: tasks ⊆ active
    unknown = [t for t in tasks if t.get("symbol") not in active]
    if unknown:
        log.warning(f"symbol_tasks enthält unbekannte Symbole: {[t['symbol'] for t in unknown]}")
        if fix:
            tasks = [t for t in tasks if t.get("symbol") in active]
            write_json_file(cfg/"symbol_tasks.json", tasks)
            log.info("symbol_tasks.json bereinigt.")
    # 2) Verfügbarkeit: für alle active Symbole muss Eintrag existieren
    missing = [s for s in active if s not in avail]
    if missing:
        log.warning(f"symbol_availability fehlt für: {missing}")
        if fix:
            for s in missing: avail[s] = {"live": False, "historical": False}
            write_json_file(cfg/"symbol_availability.json", avail)
            log.info("symbol_availability.json ergänzt.")
    # 3) Client-ID Eindeutigkeit
    flat_ids = []
    for k,v in ids.items():
        flat_ids += (v if isinstance(v, list) else [v])
    dups = [i for i in set(flat_ids) if flat_ids.count(i) > 1]
    if dups:
        log.error(f"client_ids enthält doppelte IDs: {dups} (manuell korrigieren)")
    # 4) Modulexistenz
    mod_dir = Path("modules")
    requested = [m for m,a in startup.items() if a]
    missing_mods = [m for m in requested if not (mod_dir/m).exists()]
    if missing_mods:
        log.error(f"startup.json aktiviert nicht vorhandene Module: {missing_mods}")
    # Ergebnis
    if not (unknown or missing or dups or missing_mods):
        log.info("✅ Sanity-Check: alles konsistent.")
    return 0

if __name__ == "__main__":
    sys.exit(main("--fix" in sys.argv))
