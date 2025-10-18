#!/usr/bin/env bash
# Manage the MarketLab tmux workspace (supervisor, worker, poller, dashboard).
set -Eeuo pipefail
IFS=$'\n\t'

readonly SESSION="marketlab"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || (cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd))"
readonly ROOT
readonly LOG_FILE="${ROOT}/reports/tmux_launch.log"
readonly CMD_SETUP="cd \"${ROOT}\" && source .venv/bin/activate && export PYTHONPATH=src"

RESET=false
DETACHED=false
HEALTH=false
VERBOSE=false

usage() {
  cat <<'EOF'
Usage: tools/tmux_marketlab.sh [--reset] [--detached] [--health] [--verbose] [-h]

  --reset      Kill an existing session before creating a new one.
  --detached   Do not attach to the session after launch (no TTY required).
  --health     Check session health (pane titles + pids) and exit 0/2 accordingly.
  --verbose    Echo each tmux command to stdout and log it.
  -h, --help   Show this help message.
EOF
}

log() {
  local ts msg
  msg=$1
  ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  mkdir -p "${ROOT}/reports"
  printf '[%s] %s\n' "$ts" "$msg" >>"$LOG_FILE"
}

log_verbose() {
  if "$VERBOSE"; then
    printf '%s\n' "$1"
  fi
  log "$1"
}

ensure_tty() {
  if [[ ! -t 1 ]]; then
    printf 'error: tmux launcher requires a TTY (use --detached otherwise)\n' >&2
    exit 1
  fi
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

run_tmux() {
  local label=$1
  shift
  local -a cmd=("$@")
  local rendered="$(printf '%q ' "${cmd[@]}")"
  log_verbose "tmux ${label}: ${rendered% }"
  if "${cmd[@]}"; then
    return 0
  fi
  local rc=$?
  log "tmux ${label} failed rc=${rc}"
  return "$rc"
}

run_tmux_capture() {
  local label=$1 var_name=$2
  shift 2
  local -a cmd=("$@")
  local rendered="$(printf '%q ' "${cmd[@]}")"
  log_verbose "tmux ${label}: ${rendered% }"
  local output
  if ! output=$("${cmd[@]}"); then
    local rc=$?
    log "tmux ${label} failed rc=${rc}"
    return "$rc"
  fi
  output=${output%$'\n'}
  printf -v "$var_name" '%s' "$output"
  return 0
}

pane_command() {
  local label=$1 keepalive=$2 module=$3
  shift 3
  local -a module_args=("$@")
  local -a guard_cmd=("python" "-m" "tools.proc_guard" "--name" "$label")
  if [[ "$keepalive" == true ]]; then
    guard_cmd+=("--keepalive")
  fi
  guard_cmd+=("--")
  guard_cmd+=("python" "-m" "$module")
  guard_cmd+=("${module_args[@]}")
  local formatted
  printf -v formatted '%q ' "${guard_cmd[@]}"
  formatted=${formatted% }
  local inner="${CMD_SETUP} && exec ${formatted}"
  printf 'bash -lc %q' "$inner"
}

set_pane_title() {
  local pane_id=$1 title=$2
  run_tmux "set-title ${title}" tmux select-pane -t "$pane_id" -T "$title"
}

pane_guard() {
  local pane_id=$1 label=$2
  sleep 0.5
  local pid
  pid=$(tmux display-message -p -t "$pane_id" "#{pane_pid}") || true
  if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
    printf 'error: pane %s failed to start\n' "$label" >&2
    log "pane ${label} failed"
    exit 2
  fi
  log "pane ${label} pid=${pid}"
}

session_exists() {
  tmux has-session -t "$SESSION" 2>/dev/null
}

list_panes() {
  tmux list-panes -t "$SESSION" -F '#{pane_index} #{pane_title} #{pane_pid}' 2>/dev/null || true
}

session_is_healthy() {
  if ! session_exists; then
    return 1
  fi
  local expected=(supervisor worker poller dashboard)
  local panes
  mapfile -t panes < <(list_panes)
  if ((${#panes[@]} != ${#expected[@]})); then
    return 1
  fi
  local seen=0
  declare -A seen_map=()
  local pane index title pid
  for pane in "${panes[@]}"; do
    read -r index title pid <<<"$pane"
    if [[ -z "$title" || -z "$pid" ]]; then
      return 1
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      return 1
    fi
    local match=false
    local t
    for t in "${expected[@]}"; do
      if [[ "$title" == "$t" ]]; then
        match=true
        if [[ -n ${seen_map[$title]:-} ]]; then
          return 1
        fi
        seen_map[$title]=1
        ((seen++))
        break
      fi
    done
    if [[ "$match" == false ]]; then
      return 1
    fi
  done
  ((seen == ${#expected[@]}))
}

print_health() {
  if ! session_exists; then
    printf 'marketlab session: missing\n'
    return 1
  fi
  printf 'marketlab session panes:\n'
  list_panes
  if session_is_healthy; then
    return 0
  fi
  return 1
}

kill_session() {
  if session_exists; then
    log "killing existing session"
    run_tmux "kill-session" tmux kill-session -t "$SESSION" || true
  fi
}

create_session() {
  log "creating session"
  mkdir -p "${ROOT}/logs" "${ROOT}/runtime"
  local supervisor_id worker_id poller_id dashboard_id
  local cmd

  cmd=$(pane_command supervisor false marketlab.supervisor --interval 2.0)
  run_tmux "new-session supervisor" tmux new-session -d -s "$SESSION" -n supervisor "$cmd"
  run_tmux_capture "pane-id supervisor" supervisor_id tmux display-message -p -t "$SESSION:0.0" '#{pane_id}'
  set_pane_title "$supervisor_id" supervisor
  pane_guard "$supervisor_id" supervisor

  cmd=$(pane_command worker true marketlab.daemon.worker)
  run_tmux_capture "split worker" worker_id tmux split-window -h -t "$supervisor_id" -P -F '#{pane_id}' "$cmd"
  set_pane_title "$worker_id" worker
  pane_guard "$worker_id" worker

  run_tmux "focus supervisor" tmux select-pane -t "$supervisor_id"
  cmd=$(pane_command poller true tools.tg_poller)
  run_tmux_capture "split poller" poller_id tmux split-window -v -t "$supervisor_id" -P -F '#{pane_id}' "$cmd"
  set_pane_title "$poller_id" poller
  pane_guard "$poller_id" poller

  run_tmux "focus worker" tmux select-pane -t "$worker_id"
  cmd=$(pane_command dashboard true marketlab.ui.dashboard)
  run_tmux_capture "split dashboard" dashboard_id tmux split-window -v -t "$worker_id" -P -F '#{pane_id}' "$cmd"
  set_pane_title "$dashboard_id" dashboard
  pane_guard "$dashboard_id" dashboard

  run_tmux "layout tiled" tmux select-layout -t "$SESSION:0" tiled
  log "session ready"
}

attach_session() {
  if "$DETACHED"; then
    log "launch completed in detached mode"
    return
  fi
  if [[ -n ${TMUX:-} ]]; then
    run_tmux "switch-client" tmux switch-client -t "$SESSION"
  else
    run_tmux "attach" tmux attach -t "$SESSION"
  fi
}

while (($#)); do
  case "$1" in
    --reset) RESET=true ;;
    --detached) DETACHED=true ;;
    --health) HEALTH=true ;;
    --verbose) VERBOSE=true ;;
    -h|--help) usage; exit 0 ;;
    *)
      printf 'error: unknown option %s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

command_exists tmux || { printf 'error: tmux not found in PATH\n' >&2; exit 1; }

trap 'log "launcher exit code $?"' EXIT

if "$HEALTH"; then
  if print_health; then
    exit 0
  fi
  exit 2
fi

if ! "$DETACHED"; then
  ensure_tty
fi

if session_exists; then
  if "$RESET"; then
    kill_session
  elif session_is_healthy; then
    log "reusing healthy session"
    attach_session
    exit 0
  else
    log "existing session unhealthy; restarting"
    kill_session
  fi
fi

create_session
if session_is_healthy; then
  attach_session
  exit 0
fi

printf 'error: failed to create healthy session\n' >&2
log 'session failed health check after creation'
exit 2
