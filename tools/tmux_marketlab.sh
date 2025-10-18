#!/usr/bin/env bash
# Launch or reuse the MarketLab tmux workspace (supervisor, worker, poller, dashboard).
set -Eeuo pipefail
IFS=$'\n\t'

readonly SESSION="marketlab"
readonly LOG_FILE="reports/tmux_launch.log"
PYTHON=${PYTHON:-python3}

usage() {
  cat <<'EOF'
Usage: tools/tmux_marketlab.sh [--reset] [--detached] [-h]

  --reset      Kill existing session before launch.
  --detached   Do not attach after launch.
  -h, --help   Show this help text.
EOF
}

log() {
  local ts
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  printf '[%s] %s\n' "$ts" "$1" >> "$LOG_FILE"
}

ensure_tty() {
  if [[ ! -t 1 ]]; then
    printf 'error: tmux launcher requires a TTY\n' >&2
    exit 1
  fi
}

command -v tmux >/dev/null || { printf 'error: tmux not found in PATH\n' >&2; exit 1; }
ensure_tty

RESET=false
DETACHED=false
while (($#)); do
  case "$1" in
    --reset) RESET=true ;;
    --detached) DETACHED=true ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'error: unknown option %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

trap 'log "launcher exit code $?"' EXIT

cd "$(dirname "$0")/.."
mkdir -p logs runtime reports
log "launcher start reset=${RESET} detached=${DETACHED}"

[[ -f ".venv/bin/activate" ]] && source .venv/bin/activate
export PYTHONPATH="$PWD/src:${PYTHONPATH:-}"

build_exec() {
  local parts=()
  for arg in "$@"; do
    parts+=("$(printf '%q' "$arg")")
  done
  printf "bash -lc 'exec %s'" "${parts[*]}"
}

session_is_stale() {
  local -a pids
  mapfile -t pids < <(tmux list-panes -t "$SESSION" -F "#{pane_pid}" 2>/dev/null || true)
  if ((${#pids[@]} == 0)); then
    return 0
  fi
  local pid
  for pid in "${pids[@]}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
  done
  return 0
}

attach_session() {
  if "$DETACHED"; then
    return
  fi
  if [[ -n ${TMUX:-} ]]; then
    tmux switch-client -t "$SESSION"
  else
    tmux attach -t "$SESSION"
  fi
}

if tmux has-session -t "$SESSION" 2>/dev/null; then
  if "$RESET" || session_is_stale; then
    log "killing previous session"
    tmux kill-session -t "$SESSION"
  else
    log "reusing session"
    attach_session
    exit 0
  fi
fi

start_pane() {
  local target="$1" label="$2" cmd="$3"
  sleep 0.5
  local pid
  pid=$(tmux display-message -p -t "$target" "#{pane_pid}")
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    printf 'error: pane "%s" failed to start\n' "$label" >&2
    log "pane ${label} failed"
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    exit 2
  fi
  log "pane ${label} pid=${pid}"
}

ctl_cmd=$(build_exec "$PYTHON" "tools/proc_guard.py" "--name" "ctl" "--" "$PYTHON" "-m" "marketlab.supervisor" "--interval" "2.0")
tmux new-session -d -s "$SESSION" -n ctl "$ctl_cmd"
start_pane "$SESSION:0.0" "ctl" "$ctl_cmd"

worker_cmd=$(build_exec "$PYTHON" "tools/proc_guard.py" "--keepalive" "--name" "worker" "--" "$PYTHON" "-m" "marketlab.worker" "--interval" "0.2")
tmux split-window -h -t "$SESSION:0" "$worker_cmd"
start_pane "$SESSION:0.1" "worker" "$worker_cmd"

poller_cmd=$(build_exec "$PYTHON" "tools/proc_guard.py" "--keepalive" "--name" "poller" "--" "$PYTHON" "-m" "marketlab.tools.tg_poller")
tmux select-pane -t "$SESSION:0.0"
tmux split-window -v -t "$SESSION:0" "$poller_cmd"
start_pane "$SESSION:0.2" "poller" "$poller_cmd"

dashboard_cmd=$(build_exec "$PYTHON" "tools/proc_guard.py" "--keepalive" "--name" "dashboard" "--" "$PYTHON" "-m" "marketlab.ui.dashboard")
tmux select-pane -t "$SESSION:0.1"
tmux split-window -v -t "$SESSION:0" "$dashboard_cmd"
start_pane "$SESSION:0.3" "dashboard" "$dashboard_cmd"

tmux select-layout -t "$SESSION:0" tiled
log "session ready"
attach_session
