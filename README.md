
# MarketLab

Kurzüberblick
- Zweck: modulare Umgebung zum Analysieren, Testen und Simulieren von Marktdaten.
- Kernideen: klare Modi, einheitliche CLI, zentrale Settings, austauschbare Datenadapter.

## Quickstart
Hinweis: Architektur-Übersicht und Laufzeit-Flows siehe `ARCHITEKTUR.md`.
```bash
pip install -e .[dev]
marketlab --help
marketlab backtest --profile default --symbols AAPL,MSFT --timeframe 15m
```

## Runtime via tmux
- Start: `./tools/tmux_marketlab.sh`
- Stop (sauber, behält Session): `./tools/stop_all.sh`
- Neu verbinden: `tmux attach -t marketlab`
- Logs: `logs/*.log` (Rotation durch `tools/proc_guard.py`)
- Aktionen erfolgen via CLI/Telegram; keine stdin-Menüs.

## Steuerung und Dashboard

- Fenster A: Control CLI
  - Alle Aktionen laufen über den Command-Bus (SQLite)
  - Beispiel: `python -m marketlab ctl enqueue --cmd state.pause --args "{}"`
  - Drain (DEV-Test): `python -m marketlab ctl drain --apply`

- Fenster B: Read-only TUI Dashboard
  - Keine Eingabe, pollt alle 1 s, `q` beendet, `r` lädt Snapshot neu
  - Start: `python -m marketlab.tui.dashboard`
  - Zeigt Kopf (Mode/State/Uptime, Queue, Events/min), links Orders Top-20, rechts Event-Stream

- Worker Daemon
  - Startet den Hintergrund-Worker, der NEW-Kommandos verarbeitet
  - Start: `python -c "from marketlab.daemon.worker import run_forever; run_forever()"`

## Environment / Settings

Neue relevante Variablen:
- `IPC_DB=runtime/ctl.db`
- `ORDERS_TWO_MAN_RULE=1`
- `CONFIRM_STRICT=1`

Hinweise:
- Dashboard ist read-only (keine Eingabe), alle Aktionen via CLI oder Telegram.
- Telegram und CLI sprechen ausschließlich über den Bus; Two-man-Rule und TTL gelten.

### .env laden

- Alle Entry-Points (Supervisor, Worker, Dashboard, Telegram-Poller) laden `.env` zentral über Pydantic-Settings (`marketlab.settings`).
- Optionaler Helfer: `marketlab.bootstrap.env::load_env(mirror=True)` lädt `Settings()` und spiegelt relevante Keys in `os.environ` zurück (z. B. `IPC_DB`, `TELEGRAM_*`, `TG_*`, `EVENTS_REFRESH_SEC`, `KPIS_REFRESH_SEC`, `DASHBOARD_WARN_ONLY`).
- Beim Start wird eine kompakte Zusammenfassung ausgegeben: `config.summary ...` inkl. maskiertem Bot-Token (`123:****`).

Hinweise zur .env-Datei:
- Ablage im Projekt-Root, Kodierung UTF-8.
- Keine Inline-Kommentare in derselben Zeile (nur `KEY=VALUE`).
- Telegram-Gruppen-IDs sind negativ (`-100...`).

Diagnose-Beispiele:
```
python -c "from marketlab.settings import get_settings as gs; print(gs().model_dump())"
python -m tools.tg_poller  # sollte getMe ok und Startbanner senden
```

Beispiel-Start ohne vorheriges Setzen von Umgebungsvariablen:
```
python -m tools.tg_poller
```
Voraussetzung: `.env` enthält korrekte Einträge (siehe unten), dann wird der Poller korrekt initialisiert.

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
EVENTS_REFRESH_SEC=5
KPIS_REFRESH_SEC=15
DASHBOARD_WARN_ONLY=0
```

## Telegram Troubleshooting

- Symptom: HTTP 401 unauthorized
  - Ursache: Falscher Token
  - Fix: `TELEGRAM_BOT_TOKEN` prüfen (Format `123456:...`), Bot neu generieren
- Symptom: HTTP 400 chat not found
  - Ursache: `TG_CHAT_CONTROL` falsch oder Bot nicht im Chat
  - Fix: Chat-ID (negativ für Gruppen) prüfen, Bot zum Chat hinzufügen
- Symptom: HTTP 403 bot was blocked by the user
  - Ursache: Benutzer/Gruppe blockiert den Bot
  - Fix: Bot in Telegram entblocken bzw. neu hinzufügen
- Symptom: missing rights / not enough rights
  - Ursache: Bot ohne Admin-Rechte in Gruppe
  - Fix: Bot in Gruppe zu Admin machen (Nachrichten senden, Links, etc.)
- Symptom: Keine Updates empfangen
  - Ursache: Privacy Mode aktiv oder Webhook aktiv
  - Fix: Privacy Mode in BotFather prüfen (für Gruppenbefehle deaktivieren), `deleteWebhook` ausführen
- Symptom: IDs passen nicht
  - Ursache: Falsches Vorzeichen bei Gruppen-ID, Allowlist falsch
  - Fix: Gruppen verwenden negative IDs; `TG_ALLOWLIST` als CSV von User-IDs pflegen

## Telegram Quickstart

- Bot anlegen (BotFather) und Token kopieren.
- Privacy Mode in BotFather für Gruppen ausschalten.
- Bot in die Ziel-Gruppe einladen (als Admin, falls nötig).
- `.env` setzen:
  - `TELEGRAM_ENABLED=1`
  - `TELEGRAM_BOT_TOKEN=123456789:...`
  - `TG_CHAT_CONTROL=-100<GRUPPEN_ID>` (negativ für Gruppen)
  - `TG_ALLOWLIST=<deine_user_id>`
  - optional: `TELEGRAM_TIMEOUT_SEC=25`, `TELEGRAM_DEBUG=0`
- Diagnose:
  - `python tools/tg_diag.py getme`
  - `python tools/tg_diag.py send --chat <CTRL_ID> --text "ping"`
  - `python tools/tg_diag.py updates`
- Poller starten:
  - `python -m tools.tg_poller`
  - Startbanner erscheint im Control-Chat; Kommandos `/pause`, `/resume`, `/paper`, `/live`, `/confirm <TOKEN>`, `/reject <TOKEN>` werden angenommen und als Bus-Events enqueued (source="telegram").
