
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
- Aktionen erfolgen via CLI oder Slack (Telegram ist archiviert); keine stdin-Menüs.

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
- `SLACK_ENABLED=0` plus `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_CHANNEL_CONTROL`, `SLACK_POST_AS_THREAD`

Hinweise:
- Dashboard ist read-only (keine Eingabe), alle Aktionen via CLI oder Telegram.
- Slack (primärer Control-Channel) und CLI sprechen ausschließlich über den Bus; Two-man-Rule und TTL gelten.
- Simulationsmodus umschalten: `python -m marketlab mode:set mock` (setzt `SLACK_SIMULATION=1`), zurück zu Echtbetrieb: `python -m marketlab mode:set real`.
- Status prüfen: `python -m marketlab mode:status` (liefert `{"SLACK_SIMULATION": "...", "mode": ...}`).

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
SLACK_ENABLED=0
SLACK_BOT_TOKEN=
SLACK_APP_TOKEN=
SLACK_SIGNING_SECRET=
SLACK_CHANNEL_CONTROL=#marketlab-control
SLACK_POST_AS_THREAD=1
IPC_DB=runtime/ctl.db
ORDERS_TWO_MAN_RULE=1
CONFIRM_STRICT=1
EVENTS_REFRESH_SEC=5
KPIS_REFRESH_SEC=15
DASHBOARD_WARN_ONLY=0
```

## Telegram (archived)

- Standardmäßig deaktiviert: `TELEGRAM_ENABLED=0`. Slack ist der primäre Control-Channel.
- Toggle via CLI: `python -m marketlab telegram:set off` (archiviert), `python -m marketlab telegram:set on` (reaktiviert). Status: `python -m marketlab telegram:status`.
- Bereinigen der `.env`: `make tg-clean-env` → verschiebt `TELEGRAM_*` Schlüssel nach `.env.archive` (mit Zeitstempel) und setzt `TELEGRAM_ENABLED=0`.
- Services nach der Bereinigung neu starten (Slack/Worker bleiben unverändert aktiv).
- Wiederherstellung: Schlüssel aus `.env.archive` zurück in `.env` verschieben, `TELEGRAM_ENABLED=1` setzen und Dienste neu starten.

### Troubleshooting (wenn reaktiviert)

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

### Reaktivierung / Quickstart

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

## Slack Control Channel

- Aktivierung über `.env`: `SLACK_ENABLED=1`, Bot-Token (`SLACK_BOT_TOKEN`), App-Level Token für Socket Mode (`SLACK_APP_TOKEN`), Signing Secret (`SLACK_SIGNING_SECRET`), Zielkanal (`SLACK_CHANNEL_CONTROL`, Name oder Channel-ID) und optional `SLACK_POST_AS_THREAD=1` für Thread-Updates.
- Start: `python -m marketlab slack` (CLI prüft Konfiguration und beendet sich mit Code 2 bei fehlenden Tokens).
- Events aus dem Command-Bus werden gespiegelt:
  - `orders.confirm.pending` → Nachricht mit Buttons (Bestätigen/Ablehnen/Pause/Resume/Paper/Live).
  - `orders.confirm.ok` → ursprüngliche Nachricht wird auf ✅ aktualisiert, zusätzlicher Thread-Eintrag mit Quelle.
  - `state.changed` → Info-Meldung im Kanal.
- Button-Aktionen enqueuen direkt auf den SQLite-Bus mit `source="slack"` und markieren den Slack-User (`actor_id=slack:<user>`); Rate-Limits und Netzwerkfehler werden automatisch mit Backoff behandelt.
