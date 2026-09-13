#!/usr/bin/env bash
# Prépare l'environnement local Linux. Utiliser --cpu pour une machine sans GPU NVIDIA.

set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
TORCH_INDEX="https://download.pytorch.org/whl/cu124"

if [[ "${1:-}" == "--cpu" ]]; then
  TORCH_INDEX="https://download.pytorch.org/whl/cpu"
elif [[ $# -gt 0 ]]; then
  echo "Usage: PYTHON_BIN=python3.11 ./setup-linux.sh [--cpu]" >&2
  exit 2
fi

command -v "$PYTHON_BIN" >/dev/null || {
  echo "$PYTHON_BIN est introuvable. Installez Python 3.11 et python3.11-venv," >&2
  echo "ou indiquez un interpréteur compatible avec PYTHON_BIN=/chemin/python." >&2
  exit 1
}
command -v npm >/dev/null || { echo "Node.js/npm est requis pour la console web." >&2; exit 1; }

"$PYTHON_BIN" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install torch --index-url "$TORCH_INDEX"
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
(cd "$ROOT/web" && npm install)

echo "Installation terminée. Lancez ./start.sh"
