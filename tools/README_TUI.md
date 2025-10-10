# TUI + CLI + Telegram – Schnellstart

## TUI starten
```powershell
python tools/tui_dashboard.py

Status per CLI
python -m marketlab status --json
python -m marketlab health
python -m marketlab orders-confirm --all-pending

Two-Man-Rule (optional)
$env:ORDERS_TWO_MAN_RULE="1"  # TG-Click -> CONFIRMED_TG; TUI/CLI bestätigt final -> CONFIRMED

Telegram-Poller (Real)
$env:TELEGRAM_ENABLED="1"; $env:TELEGRAM_MOCK="0"
python tools/tg_poller.py


---

### 10) Smoke-Checks (ausführen, nicht committen)


python -m marketlab status --json
python tools/tui_dashboard.py
python -m marketlab orders new --symbol AAPL --side BUY --qty 1 --type MARKET --ttl 300

TUI: Taste 'c' → Order wird CONFIRMED

python -m marketlab replay --profile default --symbols AAPL --timeframe 1m

oder Paper (IBG/TWS aktiv): python -m marketlab paper --profile default --symbols AAPL --timeframe 1m
