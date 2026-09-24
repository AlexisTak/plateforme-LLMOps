#!/usr/bin/env bash
# Lance Ollama (si disponible), l'API FastAPI et la console Next.js sous Linux.

set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT/.run"
NO_BROWSER=false

if [[ "${1:-}" == "--no-browser" ]]; then
  NO_BROWSER=true
elif [[ $# -gt 0 ]]; then
  echo "Usage: ./start.sh [--no-browser]" >&2
  exit 2
fi

PYTHON="$ROOT/.venv/bin/python"
mkdir -p "$RUN_DIR"

# .env (voir .env.example) — les variables déjà définies dans le shell gardent la priorité.
if [[ -f "$ROOT/.env" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)[[:space:]]*=[[:space:]]*(.*)$ ]] || continue
    name="${BASH_REMATCH[1]}"; value="${BASH_REMATCH[2]}"
    value="${value%\"}"; value="${value#\"}"; value="${value%\'}"; value="${value#\'}"
    [[ -z "${!name:-}" ]] && export "$name=$value"
  done < "$ROOT/.env"
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Environnement Python absent: $PYTHON" >&2
  echo "Lancez d'abord ./setup-linux.sh" >&2
  exit 1
fi

if [[ ! -d "$ROOT/web/node_modules" ]]; then
  command -v npm >/dev/null || { echo "npm est requis (Node.js 20+)." >&2; exit 1; }
  echo "Installation des dépendances web…"
  (cd "$ROOT/web" && npm install)
fi

port_is_open() {
  "$PYTHON" - "$1" <<'PY'
import socket, sys
with socket.socket() as sock:
    sock.settimeout(0.2)
    raise SystemExit(sock.connect_ex(("127.0.0.1", int(sys.argv[1]))) != 0)
PY
}

api_is_healthy() {
  "$PYTHON" - <<'PY'
import json, urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=2) as response:
        assert json.load(response).get("status") == "ok"
except Exception:
    raise SystemExit(1)
PY
}

start_service() {
  local name="$1" cwd="$2"
  shift 2
  echo "Démarrage de $name…"
  (cd "$cwd" && setsid "$@" >"$RUN_DIR/$name.log" 2>&1 & echo $! >"$RUN_DIR/$name.pid")
}

if port_is_open 11434; then
  echo "Ollama est déjà actif sur le port 11434."
elif command -v ollama >/dev/null; then
  start_service ollama "$ROOT" ollama serve
else
  echo "Ollama n'est pas installé; le reste de l'application sera lancé sans lui."
fi

if api_is_healthy; then
  echo "L'API est déjà active sur le port 8000."
elif port_is_open 8000; then
  echo "Le port 8000 est occupé par un autre service." >&2
  exit 1
else
  # Mode d'auth issu du .env ou du shell ; sans valeur, l'API démarre en "login"
  # (comptes obligatoires, l'écran de premier lancement crée l'administrateur).
  start_service api "$ROOT" "$PYTHON" -m uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
fi

echo -n "Attente de l'API"
for _ in {1..90}; do
  if api_is_healthy; then break; fi
  echo -n "."
  sleep 1
done
echo
if ! api_is_healthy; then
  echo "L'API n'a pas démarré. Consultez $RUN_DIR/api.log" >&2
  exit 1
fi

if port_is_open 3000; then
  echo "La console web est déjà active sur le port 3000."
else
  command -v npm >/dev/null || { echo "npm est requis (Node.js 20+)." >&2; exit 1; }
  start_service web "$ROOT/web" npm run dev
fi

if ! $NO_BROWSER && command -v xdg-open >/dev/null; then
  xdg-open http://localhost:3000 >/dev/null 2>&1 || true
fi

echo "Biscuits Focus est lancé."
echo "  Console : http://localhost:3000"
echo "  API     : http://localhost:8000"
echo "  Logs    : $RUN_DIR"
echo "Arrêt     : ./stop.sh"
