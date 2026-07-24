#!/usr/bin/env bash

set -Eeuo pipefail

ACTION="${1:-all}"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_ROOT="${PROJECT_ROOT}/src/frontend"
PYTHON_VERSION="${OPENXFLOW_PYTHON_VERSION:-3.12}"
BACKEND_PORT="${OPENXFLOW_BACKEND_PORT:-7860}"
FRONTEND_PORT="${OPENXFLOW_FRONTEND_PORT:-3000}"
LISTEN_HOST="${OPENXFLOW_HOST:-0.0.0.0}"
PROXY_TARGET="${OPENXFLOW_PROXY_TARGET:-http://127.0.0.1:${BACKEND_PORT}}"
SKIP_PRE_COMMIT="${OPENXFLOW_SKIP_PRE_COMMIT:-0}"
NO_BROWSER="${OPENXFLOW_NO_BROWSER:-0}"

BACKEND_PID=""
FRONTEND_PID=""

print_section() {
  printf '\n\033[36m==> %s\033[0m\n' "$1"
}

fail() {
  printf '\n\033[31mOpenXFlow development command failed: %s\033[0m\n' "$1" >&2
  exit 1
}

require_command() {
  local command_name="$1"
  local install_hint="$2"
  command -v "$command_name" >/dev/null 2>&1 || fail "Required command '${command_name}' was not found. ${install_hint}"
}

check_node_version() {
  node -e '
    const [major, minor] = process.versions.node.split(".").map(Number);
    if (major < 20 || (major === 20 && minor < 19)) {
      console.error(`Node.js 20.19 or newer is required. Current version: ${process.versions.node}`);
      process.exit(1);
    }
  '
}

ensure_environment_file() {
  if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
    if [[ -f "${PROJECT_ROOT}/.env.example" ]]; then
      cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
      printf '\033[33mCreated .env from .env.example\033[0m\n'
    else
      : > "${PROJECT_ROOT}/.env"
      printf '\033[33mCreated an empty .env file\033[0m\n'
    fi
  fi
}

install_dependencies() {
  print_section "Checking development prerequisites"
  require_command "uv" "Install uv from https://docs.astral.sh/uv/getting-started/installation/."
  require_command "node" "Install Node.js 20.19 or newer from https://nodejs.org/."
  require_command "npm" "npm is normally installed together with Node.js."
  check_node_version

  cd "${PROJECT_ROOT}"
  ensure_environment_file

  print_section "Preparing Python ${PYTHON_VERSION}"
  uv python install "${PYTHON_VERSION}"

  if [[ -d "${PROJECT_ROOT}/.venv" && ! -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    printf '\033[33mThe existing .venv is not a macOS/Linux virtual environment. Recreating it.\033[0m\n'
    rm -rf "${PROJECT_ROOT}/.venv"
  fi

  print_section "Installing backend dependencies"
  uv sync --python "${PYTHON_VERSION}" --frozen --extra postgresql

  print_section "Installing frontend dependencies"
  npm --prefix "${FRONTEND_ROOT}" ci

  if [[ "${SKIP_PRE_COMMIT}" != "1" ]] && command -v git >/dev/null 2>&1; then
    print_section "Installing pre-commit hooks"
    uvx pre-commit install
  fi

  printf '\n\033[32mOpenXFlow dependencies are ready.\033[0m\n'
}

dependencies_ready() {
  [[ -x "${PROJECT_ROOT}/.venv/bin/python" && -d "${FRONTEND_ROOT}/node_modules" ]]
}

start_backend() {
  require_command "uv" "Run 'bash ./dev.sh install' first."
  cd "${PROJECT_ROOT}"
  ensure_environment_file

  print_section "Starting backend on http://localhost:${BACKEND_PORT}"
  exec uv run uvicorn \
    --factory langflow.main:create_app \
    --host "${LISTEN_HOST}" \
    --port "${BACKEND_PORT}" \
    --reload \
    --env-file .env \
    --loop asyncio
}

start_frontend() {
  require_command "npm" "Run 'bash ./dev.sh install' first."
  cd "${FRONTEND_ROOT}"

  export VITE_HOST="${LISTEN_HOST}"
  export VITE_PORT="${FRONTEND_PORT}"
  export VITE_PROXY_TARGET="${PROXY_TARGET}"

  print_section "Starting frontend on http://localhost:${FRONTEND_PORT}"
  exec npm run start
}

cleanup() {
  trap - EXIT INT TERM

  if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" >/dev/null 2>&1; then
    kill "${BACKEND_PID}" >/dev/null 2>&1 || true
  fi
  if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; then
    kill "${FRONTEND_PID}" >/dev/null 2>&1 || true
  fi

  [[ -n "${BACKEND_PID}" ]] && wait "${BACKEND_PID}" >/dev/null 2>&1 || true
  [[ -n "${FRONTEND_PID}" ]] && wait "${FRONTEND_PID}" >/dev/null 2>&1 || true
}

open_browser_later() {
  [[ "${NO_BROWSER}" == "1" ]] && return 0

  (
    sleep 3
    if command -v open >/dev/null 2>&1; then
      open "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1 || true
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "http://localhost:${FRONTEND_PORT}" >/dev/null 2>&1 || true
    fi
  ) &
}

start_services() {
  if ! dependencies_ready; then
    printf '\033[33mProject dependencies are incomplete. Running the installer first.\033[0m\n'
    install_dependencies
  fi

  ensure_environment_file

  print_section "Starting OpenXFlow development services"
  bash "${PROJECT_ROOT}/dev.sh" backend &
  BACKEND_PID=$!
  sleep 1
  bash "${PROJECT_ROOT}/dev.sh" frontend &
  FRONTEND_PID=$!

  trap cleanup EXIT
  trap 'exit 130' INT TERM

  printf '\033[32mBackend:  http://localhost:%s\033[0m\n' "${BACKEND_PORT}"
  printf '\033[32mFrontend: http://localhost:%s\033[0m\n' "${FRONTEND_PORT}"
  printf '\033[32mLAN:      http://<your-computer-ip>:%s\033[0m\n' "${FRONTEND_PORT}"
  printf 'Press Ctrl+C to stop both services.\n'

  open_browser_later

  while kill -0 "${BACKEND_PID}" >/dev/null 2>&1 && kill -0 "${FRONTEND_PID}" >/dev/null 2>&1; do
    sleep 1
  done

  fail "One of the development services exited unexpectedly."
}

show_help() {
  cat <<'EOF'
OpenXFlow macOS/Linux development helper

Usage:
  bash ./dev.sh              Install dependencies and start backend + frontend
  bash ./dev.sh all          Same as the default action
  bash ./dev.sh install      Install project dependencies only
  bash ./dev.sh start        Start backend + frontend without reinstalling
  bash ./dev.sh help         Show this help

Optional environment variables:
  OPENXFLOW_PYTHON_VERSION=3.12
  OPENXFLOW_BACKEND_PORT=7860
  OPENXFLOW_FRONTEND_PORT=3000
  OPENXFLOW_HOST=0.0.0.0
  OPENXFLOW_PROXY_TARGET=http://127.0.0.1:7860
  OPENXFLOW_SKIP_PRE_COMMIT=1
  OPENXFLOW_NO_BROWSER=1

The existing commands such as 'make init', 'make backend', and 'make frontend'
remain supported and are not changed by this helper.
EOF
}

case "${ACTION}" in
  install)
    install_dependencies
    ;;
  start)
    start_services
    ;;
  all)
    install_dependencies
    start_services
    ;;
  backend)
    start_backend
    ;;
  frontend)
    start_frontend
    ;;
  help|-h|--help)
    show_help
    ;;
  *)
    show_help
    fail "Unknown action: ${ACTION}"
    ;;
esac
