# Inventory Snapshot (WSL/Linux)

## Primary Entry Points
- `python -m marketlab.supervisor` – tmux pane `ctl` via `tools/tmux_marketlab.sh`.
- `python -m marketlab.worker` – tmux pane `worker` via proc_guard (keepalive).
- `python tools/proc_guard.py` – wrapper invoked by tmux for supervisor/worker/dashboard.
- `./tools/tmux_marketlab.sh` – orchestrates panes, loads venv, sets `PYTHONPATH`.
- `python -m marketlab.tui.dashboard` – Textual dashboard (read-only, q=quit, r=refresh).

## Referenced Modules
- `marketlab.ipc.bus` – imported by supervisor, worker, telegram utilities.
- `marketlab.orders.store` – used by worker/order pipelines.
- `marketlab.daemon.worker` – consumed by `marketlab.worker` shim.
- `marketlab.bootstrap.env` – imported by supervisor/worker/TUI for env mirroring.
- `marketlab.control_menu` – legacy CLI menu (deprecated, still referenced by tests/CLI).
- `tools/tg_*.py` – referenced by docs and tmux placeholders; remain for Telegram flows.

## Low-Usage / Legacy Items (Keep under review)
- `tools/tui_dashboard.py` – superseded by Textual dashboard; emits `DeprecationWarning`.
- PowerShell launchers under `tools/*.ps1` – unused on Linux/WSL; documented in `DEPRECATED.md`.
- `tmp_*.txt` files – ad-hoc debug artefacts (not imported); safe to delete once confirmed unused.
- `control_menu` tests – still executed; remove only after CLI migration completes.

## Observations
- No FastAPI/Uvicorn usage detected; dependencies not added.
- SQLite bus located at `runtime/ctl.db`; WAL + read-only access configured in `marketlab.tui.db`.
- Logs under `logs/` rotated by `tools/proc_guard.py` (UTF-8, ISO-8601 UTC).

_Last refreshed: 2025-10-13T20:13Z_
