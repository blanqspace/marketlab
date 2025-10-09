# MarketLab – Kurzüberblick

- Zweck: Modulare Forschungs-/Steuerungsumgebung für Markt-/Handels-Workflows (Backtest, Replay, Paper, Live, Control).
- Primäre Nutzer: Quant/Algo-Entwickler, Ops/Runbook-Nutzer (Windows), Tester.
- Kernfunktionen: Typer-CLI (`python -m marketlab`), zentrale Settings (pydantic-settings), Telegram-Integration (Real/Mock), einfache Datenadapter, globaler Zustandsmanager, Signal-Handling.

## TL;DR Quickstart (Windows, DEV)

- Voraussetzungen
  - Python ≥ 3.11 (pyproject.toml), Pip, VS Code
  - Optional: TWS/IBKR lokal (für spätere Live/Paper-Funktionen)

- Installation (Entwicklermodus)
  - `pip install -e .[dev]`

- Smoke-Test CLI
  - `python -m marketlab --help`

- Minimaler Backtest (lädt CSV/Parquet aus `data/` falls vorhanden)
  - `python -m marketlab backtest --profile default --symbols AAPL,MSFT --timeframe 15m`

## Projektstatus: Produktionsreif vs. POC

- Reif: CLI-Struktur mit Typer, globaler State-Manager, JSON-Logging auf stdout, Signal-Handling.
- Reif: Telegram-Service inkl. Mock-Poller und Mock-Werkzeuge (`runtime/telegram_mock/*`, `tools/tg_cli.py`, `tools/tg_dashboard.py`).
- POC: Datenadapter `IBKRAdapter` (Stub, keine echte Verbindung/Streams).
- POC: Modi `paper`/`live` (nur Stub-Aufrufe der Adapter, kein Orderflow).
- POC/Legacy-Shim: `main.py` (argparse-Menü), nutzt `shared/*`-Layer getrennt von der Typer-CLI.

## Ordnerstruktur (Auszug)

```
src/marketlab/
  __main__.py        # `python -m marketlab` Einstieg → Typer-CLI
  cli.py             # Typer-App, Kommandos: control, backtest, replay, paper, live
  settings.py        # pydantic-settings, ENV → Settings
  core/state_manager.py
  services/telegram_service.py
  modes/{backtest,replay,paper,live,control}.py
  data/{adapters.py, paths.py}
  utils/{logging.py, signal_handlers.py}
tools/
  tg_cli.py, tg_dashboard.py, tg_diag.py, verify_* (Env/Mock/Bootstrap)
runtime/
  telegram_mock/     # Mock-Ausgaben (sendMessage*.json)
reports/
  events/startup.json (Legacy-Notifier)
```

## CLI – Übersicht (Typer)

- Hilfe: `python -m marketlab --help`
- Control (Schleife, Telemetrie minimal): `python -m marketlab control`
- Backtest: `python -m marketlab backtest --profile default --symbols AAPL,MSFT --timeframe 15m`
- Replay: `python -m marketlab replay --profile default --symbols AAPL --timeframe 1h`
- Paper: `python -m marketlab paper --profile default --symbols AAPL --timeframe 1m`
- Live: `python -m marketlab live --profile default --symbols AAPL --timeframe 1m`

Parameter (gemeinsam): `--profile`, `--symbols` (CSV), `--timeframe`. Backtest optional: `--start`, `--end`, `--work-units`.

## Telegram-Integration (Real/Mock)

- Service: `src/marketlab/services/telegram_service.py`
  - Poller (`start_poller`) via CLI-Callback automatisch aktiv.
  - Nachrichten: `notify_start|notify_end|notify_error`, Status-/Menübefehle via Inline-Callbacks im Control-Chat.
  - Mock-Modus (`TELEGRAM_MOCK=1`): schreibt JSON-Artefakte nach `runtime/telegram_mock/` statt API-Calls.
- Control-Mode Start-Ping: einmalig beim Start: „🟢 TradeOps: Control-Loop gestartet“ (kein Spam).
- Tools
  - `python tools/tg_cli.py` (Mock-CLI, Befehle: menu/status/pause/resume/stop/follow)
  - `python tools/tg_dashboard.py` (Mock-Dashboard, Tastatursteuerung)
  - `python tools/tg_diag.py` (Diagnose Real/Mock, `getMe` u.a.)

## Environment & Secrets

- Quelle: `.env` (UTF-8), OS-ENV hat Vorrang; pydantic-settings in `settings.py`.
- Wichtige Variablen
  - `ENV_MODE`, `APP_BRAND`
  - `TWS_HOST`, `TWS_PORT`
  - `TELEGRAM_ENABLED` (`true/1`), `TELEGRAM_BOT_TOKEN`, `TG_CHAT_CONTROL`, `TG_ALLOWLIST`, `TELEGRAM_MOCK`, `TELEGRAM_AUTOSTART`, `TELEGRAM_DEBUG`
- Schnelle Checks
  - Mock/Env: `python tools/verify_mock_env.py`
  - Telegram-Env: `python tools/verify_telegram_env.py`
  - Bootstrap: `python tools/verify_bootstrap.py`

### ENV-Referenz (Auszug)

| Variable | Typ | Default | Beispiel | Beschreibung |
|---|---|---:|---|---|
| `ENV_MODE` | string | `DEV` | `DEV` | Betriebsmodus App |
| `APP_BRAND` | string | `MarketLab` | `TradeOps` | Branding für Notifications |
| `TWS_HOST` | string | – | `127.0.0.1` | IBKR/TWS Host (Stub in aktueller Version) |
| `TWS_PORT` | int | – | `4002` | IBKR/TWS Port (Stub) |
| `TELEGRAM_ENABLED` | bool-like | `false` | `true` | Aktiviert Telegram-Service/Poller |
| `TELEGRAM_BOT_TOKEN` | secret | – | `123456:ABCDEF...` | Bot-Token (nur Real) |
| `TG_CHAT_CONTROL` | int | – | `6758578842` | Control-Chat (User/Gruppe) |
| `TG_CHAT_LOGS` | int | – | `-4694894412` | Log-Channel (optional) |
| `TG_CHAT_ORDERS` | int | – | `-4901396200` | Orders-Channel (optional) |
| `TG_CHAT_ALERTS` | int | – | `-4843522558` | Alerts-Channel (optional) |
| `TG_ALLOWLIST` | csv<int> | – | `6758578842,1234567` | Whitelist erlaubter User-IDs |
| `TELEGRAM_MOCK` | bool-like | `0` | `1` | Mock-Ausgaben in `runtime/telegram_mock/` |
| `TELEGRAM_AUTOSTART` | bool-like | `0` | `1` | Legacy-Notifier Startup-Probe |
| `TELEGRAM_DEBUG` | bool-like | `0` | `1` | Verbose Mock/Requests im Service |

Hinweis: Für Mock-Interaktion muss `TELEGRAM_ENABLED=1` UND `TELEGRAM_MOCK=1` gesetzt sein (Poller startet nur, wenn enabled).

## Logs & Artefakte

- Logs: JSON auf stdout (Formatter in `utils/logging.py`).
- Mock-Ausgaben: `runtime/telegram_mock/sendMessage*.json`.
- Legacy-Events: `reports/events/startup.json` (vom `shared/system/telegram_notifier.py`).
- Verzeichnisse `logs/`, `data/`, `reports/` vorhanden – projektabhängige Nutzung (TODO: detaillierte Logrotation/Artefakte definieren).

## HOWTO: Getting Started mit Mock

Ziel: Telegram-Interaktion lokal testen, ohne echte API.

1) PowerShell-ENV für aktuelle Session setzen

```
$env:TELEGRAM_ENABLED = "1"
$env:TELEGRAM_MOCK    = "1"
```

2) Control-Mode starten (Poller wird initialisiert)

```
python -m marketlab control
```

3) In zweitem Terminal Mock-CLI nutzen

```
python tools/tg_cli.py
# Eingaben: menu | status | pause | resume | stop | follow
```

4) Mock-Ausgaben prüfen

```
Get-ChildItem runtime/telegram_mock
Get-Content runtime/telegram_mock/sendMessage.json
```

Alternative Visualisierung: Dashboard

```
python tools/tg_dashboard.py
# Tasten: m=/menu, s=/status, p=/pause, r=/resume, x=/stop, q=quit
```

## Betrieb (Windows)

- PowerShell als Standard. Beispiele oben direkt ausführbar.
- Start ohne Installation: `python -m marketlab ...`
- Optionales Script: `tools/start_marketlab.ps1` (setzt Telegram Disabled für Offlineszenarien).

## Tests

- Schnelltest: `pytest -q`
- Enthalten: `tests/test_cli_smoke.py` (CLI-Hilfe, Backtest-Smoke).

## Troubleshooting

- „CLI startet nicht“: Python ≥ 3.11? `python -m marketlab --help` statt `marketlab` (kein Console-Script definiert).
- „Telegram ohne Effekt“: `TELEGRAM_ENABLED=1` und Token/Chat-ID gesetzt? Für Mock `TELEGRAM_MOCK=1` verwenden.
- „Mock zeigt nichts“: Läuft der Poller? `python tools/tg_cli.py` und `/menu` senden; Dateien unter `runtime/telegram_mock/` prüfen.
- „Backtest findet keine Daten“: CSV/Parquet unter `data/` mit Schema `SYMBOL_TIMEFRAME.{csv,parquet}` und Spalten `time,open,high,low,close,volume`.

## Roadmap

- TODO: IBKR-Connectivity in `IBKRAdapter` (connect, Streams, Fehlerpfade).
- TODO: Paper/Live Orderflow (Orders, Fills, Persistenz, Telegram-Buttons).
- TODO: Dateningest/ETL-Tools und Validierung.
- TODO: Logging in Dateien + strukturierte Reports.
- TODO: Konsolidierung `main.py` (Legacy-Shim) in die Typer-CLI.
