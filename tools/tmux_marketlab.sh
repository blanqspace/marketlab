#!/usr/bin/env bash
set -euo pipefail
SESSION="marketlab"
cd "$(dirname "$0")/.."   # Projektroot
mkdir -p logs runtime

# venv + PYTHONPATH
[[ -f ".venv/bin/activate" ]] && source .venv/bin/activate
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"
PY=python3

tmux kill-session -t "$SESSION" 2>/dev/null || true

# ctl (start guard im Hintergrund, zeige dann Log)
tmux new-session -d -s "$SESSION" -n ctl \
  "bash -lc '$PY tools/proc_guard.py --name ctl -- $PY -m marketlab.supervisor --interval 2.0 & sleep 0.5; tail -F logs/ctl.log'"

# worker
tmux split-window -h \
  "bash -lc '$PY tools/proc_guard.py --keepalive --name worker -- $PY -m marketlab.worker --interval 0.2 & sleep 0.5; tail -F logs/worker.log'"

# poller (Platzhalter)
tmux select-pane -t 0
tmux split-window -v "echo '[info] Poller (marketlab.tools.tg_poller) fehlt'; sleep infinity"

# dashboard (Platzhalter)
tmux select-pane -t 1
tmux split-window -v "echo '[info] Dashboard (marketlab.ui.dashboard) fehlt'; sleep infinity"

tmux select-layout tiled
tmux attach -t "$SESSION"
