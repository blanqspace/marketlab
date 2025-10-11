
# MarketLab

Kurzüberblick
- Zweck: modulare Umgebung zum Analysieren, Testen und Simulieren von Marktdaten.
- Kernideen: klare Modi, einheitliche CLI, zentrale Settings, austauschbare Datenadapter.

## Quickstart
```bash
pip install -e .[dev]
marketlab --help
marketlab backtest --profile default --symbols AAPL,MSFT --timeframe 15m
```

## Steuerung und Dashboard

- Fenster A: Control CLI
  - Alle Aktionen laufen über den Command-Bus (SQLite)
  - Beispiel: `python -m marketlab ctl enqueue --cmd state.pause --args "{}"`
  - Drain (DEV-Test): `python -m marketlab ctl drain --apply`

- Fenster B: Read-only TUI Dashboard
  - Kein Input, kein screen=True, 1–2 s Aktualisierung
  - Start: `python -m tools.tui_dashboard`
  - Zeigt Kopf (State, Heartbeat, UTC), links Orders Top-20, rechts Events (tail)

- Worker Daemon
  - Startet den Hintergrund-Worker, der NEW-Kommandos verarbeitet
  - Start: `python -c "from src.marketlab.daemon.worker import run_forever; run_forever()"`

- Control-Menu (Nummern)
  - Start: `python -m marketlab control-menu`
  - Optionen: 1 Pause, 2 Resume, 3 Stop, 4 Confirm(ID), 5 Reject(ID), 6 Mode: Paper, 7 Mode: Live, 9 Exit
  - Sicherheitsabfrage mit y/n; Ausgabe zeigt erzeugte Command-ID

## Environment / Settings

Neue relevante Variablen:
- `IPC_DB=runtime/ctl.db`
- `ORDERS_TWO_MAN_RULE=1`
- `CONFIRM_STRICT=1`

Hinweise:
- Dashboard ist read-only (keine Eingabe), alle Aktionen via CLI oder Telegram.
- Telegram und CLI sprechen ausschließlich über den Bus; Two-man-Rule und TTL gelten.

## Telegram-Buttons und Befehle

- Hauptmenü-Buttons (Inline): Pause, Resume, Stop, Confirm(ID), Reject(ID), Mode Paper, Mode Live
- Callback-Mapping: erzeugt Bus-Kommandos (`state.*`, `orders.*`, `mode.switch`)
- Textbefehle:
  - `/confirm <ID>` bestätigt die angegebene Order (Two-man-Rule gilt weiterhin)
  - Bei Confirm/Reject ohne ID fordert der Bot die ID an

## Ordnerstruktur (neu)
```
src/
  marketlab/
    __init__.py
    __main__.py
    cli.py
    settings.py
    utils/
      logging.py
    data/
      __init__.py
      adapters.py
    modes/
      backtest.py
      replay.py
      paper.py
      live.py
```

## .env (Beispiele)
```
ENV_MODE=DEV
TWS_HOST=127.0.0.1
TWS_PORT=7497
TELEGRAM_ENABLED=false
TELEGRAM_BOT_TOKEN=ignored
IPC_DB=runtime/ctl.db
ORDERS_TWO_MAN_RULE=1
CONFIRM_STRICT=1
```
