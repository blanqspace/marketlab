# Private Summary – marketlab

_Erzeugt am 2025-10-05 15:07:40 UTC_

## ENV
**Datei:** `.env`

| Key | Typ | Länge | Flags | Maske |
|-----|-----|-------|-------|-------|
| `API_KEY` | string | 17 |  | `*************here` |
| `CLIENT_ID_ALERTS` | int-like | 3 |  | `***` |
| `CLIENT_ID_BACKTEST` | int-like | 3 |  | `***` |
| `CLIENT_ID_DATA_MAINT` | int-like | 3 |  | `***` |
| `CLIENT_ID_DISPATCHER` | int-like | 3 |  | `***` |
| `CLIENT_ID_FETCHER` | int-like | 3 |  | `***` |
| `CLIENT_ID_HEALTH` | int-like | 3 |  | `***` |
| `CLIENT_ID_HEATMAP` | int-like | 3 |  | `***` |
| `CLIENT_ID_IMPORT` | int-like | 3 |  | `***` |
| `CLIENT_ID_LIVE` | int-like | 3 |  | `***` |
| `CLIENT_ID_MAIN` | int-like | 3 |  | `***` |
| `CLIENT_ID_MONITOR` | int-like | 3 |  | `***` |
| `CLIENT_ID_ORDER` | int-like | 3 |  | `***` |
| `CLIENT_ID_PAPER` | int-like | 3 |  | `***` |
| `CLIENT_ID_REPLAY` | int-like | 3 |  | `***` |
| `CLIENT_ID_REPORTS` | int-like | 3 |  | `***` |
| `CLIENT_ID_STRAT1` | int-like | 3 |  | `***` |
| `CLIENT_ID_STRAT2` | int-like | 3 |  | `***` |
| `CLIENT_ID_STRAT3` | int-like | 3 |  | `***` |
| `CLIENT_ID_SYMBOL_SCAN` | int-like | 3 |  | `***` |
| `ENV_MODE` | string | 3 |  | `***` |
| `TELEGRAM_AUTOSTART` | bool-like | 1 |  | `*` |
| `TELEGRAM_BOT_TOKEN` | string | 46 | token-like,has-colon | `******************************************AbOo` |
| `TELEGRAM_ENABLED` | bool-like | 1 |  | `*` |
| `TELEGRAM_MOCK` | bool-like | 1 |  | `*` |
| `TG_ALLOWLIST` | int-like | 10 |  | `******8842` |
| `TG_CHAT_ALERTS` | string | 35 | token-like | `*******************************ERTS` |
| `TG_CHAT_CONTROL` | string | 59 | token-like | `*******************************************************te")` |
| `TG_CHAT_LOGS` | string | 35 | token-like | `*******************************LOGS` |
| `TG_CHAT_ORDERS` | string | 35 | token-like | `*******************************DERS` |
| `TWS_HOST` | string | 9 |  | `*****.0.1` |
| `TWS_PORT` | int-like | 4 |  | `****` |

## .gitignore
**Regeln:**
- `__pycache__/`
- `*.pyc`
- `*.pyo`
- `*.pyd`
- `env/`
- `venv/`
- `.venv/`
- `.env`
- `*.env`
- `.vscode/`
- `.idea/`
- `*.zip`
- `*.bak`
- `*.log`
- `logs/`
- `runtime/locks/`
- `*.lock`
- `.DS_Store`
- `Thumbs.db`
- `data/`

**Gefundene ignorierte Dateien (vereinfachte Erkennung): 31**

| Datei | Größe |
|-------|-------|
| `.env` | 2 KB |
| `logs\ask_flow.log` | 4 KB |
| `logs\automation.log` | 0 B |
| `logs\bot.log` | 0 B |
| `logs\client_registry.log` | 24 KB |
| `logs\config_loader.log` | 6 KB |
| `logs\data_ingest\2025-09-21.log` | 0 B |
| `logs\file_utils\2025-09-21.log` | 0 B |
| `logs\file_utils\2025-09-23.log` | 0 B |
| `logs\file_utils\2025-09-24.log` | 0 B |
| `logs\file_utils\2025-09-26.log` | 0 B |
| `logs\file_utils\2025-09-27.log` | 0 B |
| `logs\file_utils.log` | 0 B |
| `logs\ibkr_client\2025-09-21.log` | 3 KB |
| `logs\ibkr_client\2025-09-23.log` | 83 B |
| `logs\ibkr_client\2025-09-24.log` | 1 KB |
| `logs\ibkr_client\2025-09-26.log` | 0 B |
| `logs\ibkr_client\2025-09-27.log` | 0 B |
| `logs\ibkr_client.log` | 68 KB |
| `logs\lock_tools\2025-09-21.log` | 0 B |
| `logs\main.log` | 0 B |
| `logs\orders_viewer.log` | 0 B |
| `logs\smoke_test.log` | 61 B |
| `logs\symbol_loader\2025-09-21.log` | 0 B |
| `logs\symbol_loader\2025-09-23.log` | 0 B |
| `logs\symbol_loader\2025-09-24.log` | 0 B |
| `logs\symbol_loader\2025-09-26.log` | 0 B |
| `logs\symbol_loader\2025-09-27.log` | 0 B |
| `logs\symbol_loader.log` | 0 B |
| `logs\telegram_notifier.log` | 195 KB |
| `logs\thread_tools\2025-09-23.log` | 0 B |