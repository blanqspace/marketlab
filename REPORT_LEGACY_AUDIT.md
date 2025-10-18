# Legacy Audit - 2025-10-18

## Überblick
- Gesuchte Bereiche: `modules/`, `shared/`, `telegram/`, `control/`, `data_clean/`
- Analyse fokussiert auf aktive Quellen (`src/`, Root-Skripte, Tools/Tests) und ignorierte `legacy/`-/Report-Inhalte
- Ergebnis: Nur `main.py` nutzt noch alte Paketnamen; alle historischen Ordner liegen bereits unter `legacy/`

## Fundstellen
| Ordner | Datei | Zeile | Import-Typ | Kontext |
| --- | --- | --- | --- | --- |
| shared | main.py | 10 | import | from shared.core.config_loader import load_env |
| shared | main.py | 11 | import | from shared.system.telegram_notifier import TelegramNotifier |
| shared | main.py | 12 | import | from shared.utils.logger import get_logger |
| shared | main.py | 125 | import | from shared.utils.orders import load_orders, add_order, cancel_order |
| modules | main.py | 13 | import | from modules.bot.automation import Automation |
| telegram | - | - | - | keine Treffer |
| control | - | - | - | keine Treffer |
| data_clean | - | - | - | keine Treffer |

## Klassifikation
- `modules/` → **migratable**: einziges Vorkommen in `main.py`, das bereits als Legacy-Entry-Point gilt (via `pyproject.toml` ausgeschlossen). Funktionaler Ersatz existiert unter `legacy/modules`.
- `shared/` → **migratable**: nur `main.py` referenziert es. Produktive Pfade nutzen inzwischen `marketlab.services.*`.
- `telegram/` → **unbenutzt**: keine aktiven Code-Referenzen; vollständiger Altbestand liegt in `legacy/telegram`.
- `control/` → **unbenutzt**: alle Exporte unter `legacy/control`, moderne Steuerung via `marketlab.control_menu`/Textual-Dashboard.
- `data_clean/` → **unbenutzt**: nur historische Backtests/Reports; aktueller Datenpfad läuft über Services im Paket.

## Quarantäne-Status
- Bereits vorhanden: `legacy/{modules,shared,telegram,control,data_clean}` (keine neuen Moves nötig).
- `legacy/README.md` bestätigt Archivierung am 2025-10-18 („Keine Laufzeitabhängigkeiten laut Scan.“).
- Prozess-Notizen ergänzt in `reports/cleanup_log.txt`.

## Testlauf / Kompatibilität
- `pytest -q` -> mehrfacher Timeout (>600 s). Engpass: `tests/test_poller_guard.py::test_poller_starts_with_complete_env` blockiert, weil `tools/tg_poller.main(once=True)` bei `mock=False` nicht terminiert; zusätzlich hängt `tests/test_proc_guard_signals.py` durch Signal-Handler-Aufruf im Neben-Thread.
- Teil-Testläufe: alle übrigen Test-Module bestanden (`pytest -q` in Batches, dokumentiert im Cleanup-Log).
- `python -m marketlab.daemon.worker --dry-run` -> OK (sofortiger Exit).
- `python -m marketlab.ui.dashboard --dry-run` -> Timeout; CLI ignoriert Flag und startet interaktive Textual-App, die manuell beendet werden muss.

## Empfehlung
- Legacy-Ordner für mindestens 14 Tage beobachtet halten; finale Löschung erst nach weiterer Verifikation (insb. Fix für `tg_poller.main`-Once-Exit und ProcGuard-Signaltests).
- Prüfen, ob `main.py` komplett nach `legacy/` verschoben oder entfernt werden kann, da einzige Quelle für alte Imports.
- Nach Stabilitätszeitraum: gezielte Entfernung der Altordner + Aktualisierung der Ausschlüsse in `pyproject.toml`.
