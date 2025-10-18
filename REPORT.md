# MarketLab Recovery Report

## Summary
- Restored Python package entry points under `marketlab.tools` and `marketlab.ui` so both legacy (`tools.*`) and package imports work again.
- Replaced the placeholder tmux launcher with a robust script that starts supervisor, worker, poller, and dashboard panes via `proc_guard` on WSL.
- Removed stray temporary files (`temp_cb.py`, `tmp_*.txt`, `tools/test_output.json`, empty `marketlab/` dir) and refreshed `.gitignore` to prevent reintroducing junk artifacts.
- Added a lightweight `scripts/env_check.py`, `.env.example`, and expanded Makefile targets (venv/install/env-check/run-*). This brings the WSL onboarding and runtime workflow back in line with documentation.

## Root-Cause Analysis
| Component | Finding | Evidence |
|-----------|---------|----------|
| Telegram Poller | `tmux_marketlab.sh` replaced the poller pane with `echo '[info] ... fehlt'`; poller never started. | Previous script contents under `tools/tmux_marketlab.sh`.
| Dashboard | Same script replaced dashboard pane with an infinite `sleep`; Textual dashboard never launched. | `tools/tmux_marketlab.sh` placeholder pane.
| Python Entry Points | `marketlab.tools.*` and `marketlab.ui.*` packages were empty, so `python -m marketlab.tools.tg_poller` failed. | Absence of modules under `src/marketlab/tools`/`ui`.
| Repo Hygiene | Temp scripts/logs checked into git confused developers and polluted releases. | Files `temp_cb.py`, `tmp_*.txt`, `tools/test_output.json`, empty `marketlab/` dir.

## Diff Overview (staged)
- `.gitignore` – add cache/log/temp patterns.
- `.env.example` – new placeholder configuration.
- `Makefile` – install/env-check/run-* targets + lint helpers.
- `scripts/env_check.py` – masked environment validator.
- `tools/tmux_marketlab.sh` – full tmux orchestrator with logging and session reuse.
- `src/marketlab/tools/{__init__,tg_poller}.py` – wrappers back to legacy poller.
- `src/marketlab/ui/{__init__,dashboard}.py` – wrappers to Textual dashboard.
- `src/marketlab.egg-info/{SOURCES.txt,top_level.txt}` – packaging metadata updated.
- Removed: `marketlab/`, `temp_cb.py`, `tmp_*.txt`, `tools/test_output.json`.

## WSL Runbook
```bash
# 1) bootstrap
python3 -m venv .venv
source .venv/bin/activate
make install

# 2) verify configuration (masked summary)
make env-check

# 3) start individual services (each in its own shell)
make run-supervisor
make run-worker
make run-poller
make run-dashboard

# 4) tmux orchestration (creates/attaches to session "marketlab")
make run-all-tmux  # requires TTY
```

## Acceptance Checklist
| Check | Result |
|-------|--------|
| `python -c "import tools.tg_poller, tools.tui_dashboard"` | ✅ |
| `python -c "import marketlab.tools.tg_poller, marketlab.ui.dashboard"` | ✅ |
| `python -m marketlab --help` | ✅ |
| `python -m marketlab ctl enqueue --cmd state.pause --args "{}"` | ✅ (cmd enqueued, worker processes once) |
| `python -m marketlab.worker --once` | ✅ (processes queue, updates runtime/ctl.db) |
| `make env-check` | ✅ |
| `bash tools/tmux_marketlab.sh --help` | ⚠️ requires TTY (script exits early by design) |
| `python -m marketlab.tools.tg_poller` | ⚠️ exits 3 with 401 guidance when token invalid (expected until valid token provided) |
| Lint (`ruff`) | ⚠️ repo-wide legacy violations remain (documented pre-existing debt) |

## Next Steps
1. Provide a valid `TELEGRAM_BOT_TOKEN` in `.env` and rerun `make run-poller` to confirm `getMe` succeeds (poller prints guidance when token invalid).
2. Consider refactoring legacy `tools/*.py` Rich dashboard in favour of the new Textual implementation, or remove it entirely to avoid confusion.
3. Address existing Ruff/Mypy issues in untouched modules (see `ruff check` output) or keep lint scoped to active modules.
4. Add optional pre-commit hooks (`ruff`, `black`, `mypy --strict`, `pytest -q`) for local safeguard.
5. Monitor `reports/tmux_launch.log` to ensure tmux launcher keeps panes alive on WSL boots.

## Open Items / To Investigate Later
- Telegram: verify `tg_diag.py sendtest` once credentials are available.
- Dashboard: evaluate Textual `DashboardApp` autosizing in tmux panes, adjust CSS if needed.
- Worker: integrate health metrics into tmux status to detect crashed panes.
