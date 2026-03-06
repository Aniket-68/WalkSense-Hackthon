#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
VENV_DIR="${BACKEND_DIR}/venv"

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "Missing virtual environment at ${VENV_DIR}"
  echo "Create it with: python3 -m venv Backend/venv && pip install -r Backend/requirements.txt"
  exit 1
fi

cd "${BACKEND_DIR}"
source "${VENV_DIR}/bin/activate"

exec python3 -m uvicorn API.server:app --host 0.0.0.0 --port "${PORT:-8080}" --workers 1
