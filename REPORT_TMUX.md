# tmux Launcher Update

## Changes
- Replaced `tools/tmux_marketlab.sh` with a robust launcher: option parsing (`--reset`, `--detached`, `-h`), session reuse/stale detection, PID health checks, and logging to `reports/tmux_launch.log`.
- Added local smoke test `tests/test_tmux_script.py` (marked `@pytest.mark.local`) for the help/usage output.

## How to Run
```bash
bash tools/tmux_marketlab.sh --reset      # recreate session and attach/switch
bash tools/tmux_marketlab.sh --detached   # start without attaching
pytest -q -m local tests/test_tmux_script.py
```

## Verification Steps
- Ensure tmux is installed and run with a TTY.
- Confirm `reports/tmux_launch.log` records start/exit information.
- Execute the local pytest marker to verify the script remains shellcheck-clean and responds to `--help`.
