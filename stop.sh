#!/usr/bin/env bash
# Arrête uniquement les processus démarrés par start.sh.

set -u
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
INCLUDE_OLLAMA=false

if [[ "${1:-}" == "--include-ollama" ]]; then
  INCLUDE_OLLAMA=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: ./stop.sh [--include-ollama]" >&2
  exit 2
fi

stop_service() {
  local name="$1" pid_file="$RUN_DIR/$1.pid" pid
  if [[ ! -f "$pid_file" ]]; then
    echo "$name : aucun processus enregistré."
    return
  fi
  pid="$(<"$pid_file")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
    for _ in {1..30}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -KILL -- "-$pid" 2>/dev/null || true
    echo "$name arrêté."
  else
    echo "$name n'était plus actif."
  fi
  rm -f -- "$pid_file"
}

stop_service api
stop_service web
$INCLUDE_OLLAMA && stop_service ollama
