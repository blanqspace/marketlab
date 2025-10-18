# MarketLab tmux launcher hardening

- `tools/tmux_marketlab.sh` now derives `PROJECT_ROOT` via `git rev-parse` (fallback to script dir), builds `CMD_SETUP="cd "$ROOT" && source .venv/bin/activate && export PYTHONPATH=src"`, and uses it for every pane command (`python -m marketlab.supervisor`, `marketlab.daemon.worker`, `tools.tg_poller`, `marketlab.ui.dashboard`).
- Added `--health`, `--verbose`, `--reset`, `--detached` controls, pane spawn guards, and reuse logic that kills/re-creates stale sessions automatically. All actions are timestamped into `reports/tmux_launch.log` (created on demand).
- Health mode enumerates panes (titles + PIDs) and returns exit 0/2. Verbose mode mirrors every tmux invocation to stdout while logging.

## Usage snippets

- Fresh start in background:
  `bash tools/tmux_marketlab.sh --reset --detached --verbose`

- Attach later (if not inside tmux):
  `tmux attach -t marketlab`

- Health probe (CI/cron):
  `bash tools/tmux_marketlab.sh --health`

- Verbose interactive launch:
  `bash tools/tmux_marketlab.sh --verbose`

Log file: `reports/tmux_launch.log` keeps the chronological command trace (UTC timestamps).
