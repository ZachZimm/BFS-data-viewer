#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"

if [[ ! -x "${ROOT_DIR}/venv/bin/python" ]]; then
  echo "Missing Python virtualenv at ${ROOT_DIR}/venv"
  echo "Create it first, then install backend requirements."
  exit 1
fi

if [[ ! -d "${ROOT_DIR}/frontend/node_modules" ]]; then
  echo "Missing frontend dependencies in ${ROOT_DIR}/frontend/node_modules"
  echo "Run: cd frontend && npm install"
  exit 1
fi

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi

  if [[ -n "${FRONTEND_PID:-}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi

  wait "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

cd "${ROOT_DIR}"

./venv/bin/uvicorn backend.app.main:app --reload --host "${BACKEND_HOST}" --port "${BACKEND_PORT}" &
BACKEND_PID=$!

cd "${ROOT_DIR}/frontend"
npm run dev -- --host "${BACKEND_HOST}" --port "${FRONTEND_PORT}" &
FRONTEND_PID=$!

echo "Backend:  http://${BACKEND_HOST}:${BACKEND_PORT}"
echo "Frontend: http://${BACKEND_HOST}:${FRONTEND_PORT}"

wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
