#!/usr/bin/env bash
set -euo pipefail

# Pfade anpassen, falls nötig:
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SESSION="marketlab"
PANE_NAME="slack"

# venv auto-detect
if [[ -f "${REPO_ROOT}/.venv/bin/activate" ]]; then
  VENV_ACTIVATE="${REPO_ROOT}/.venv/bin/activate"
else
  VENV_ACTIVATE=""
fi

tmux has-session -t "$SESSION" 2>/dev/null || tmux new-session -d -s "$SESSION" -n "$PANE_NAME"

tmux kill-pane -t "${SESSION}:0.0" 2>/dev/null || true
tmux new-window -t "$SESSION" -n "$PANE_NAME"
tmux send-keys -t "${SESSION}:${PANE_NAME}" "cd '${REPO_ROOT}'" C-m
[[ -n "$VENV_ACTIVATE" ]] && tmux send-keys -t "${SESSION}:${PANE_NAME}" "source '${VENV_ACTIVATE}'" C-m
tmux send-keys -t "${SESSION}:${PANE_NAME}" "python -m marketlab slack" C-m

echo "tmux session '${SESSION}' running. Attach with: tmux attach -t ${SESSION}"
