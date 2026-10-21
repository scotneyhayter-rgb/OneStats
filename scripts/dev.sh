#!/usr/bin/env bash
# OneStats development helper. Usage: scripts/dev.sh <command>
# Works in Git Bash on Windows. Run from the repo root.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API="$ROOT/services/api"
DESKTOP="$ROOT/apps/desktop"
PY="$API/.venv/Scripts/python"   # Windows venv layout

usage() {
  cat <<'EOF'
OneStats dev commands:
  backend-install   Create the Python venv and install backend deps
  backend           Start the FastAPI backend (dev, auto-reload) on :8000
  desktop-install   Install desktop (npm) dependencies
  desktop           Start the desktop app (Tauri dev, native window)
  desktop-web       Start only the web frontend (Vite) on :1420
  test              Run backend (pytest) and frontend (vitest) tests
  lint              Lint backend (ruff) and type-check frontend (tsc)
  build             Build the Windows desktop application (Tauri)
  migrate           Apply database migrations (requires DB credential in .env)
  stop              Stop dev servers (ports 8000 and 1420)
EOF
}

case "${1:-}" in
  backend-install)
    cd "$API"; python -m venv .venv; "$PY" -m pip install -U pip; "$PY" -m pip install -e ".[dev]" ;;
  backend)
    cd "$API"; "$PY" -m uvicorn onestats.main:app --reload --host 127.0.0.1 --port 8000 ;;
  desktop-install)
    cd "$DESKTOP"; npm install ;;
  desktop)
    cd "$DESKTOP"; npm run tauri dev ;;
  desktop-web)
    cd "$DESKTOP"; npm run dev ;;
  test)
    echo "== backend =="; cd "$API"; "$PY" -m pytest -q
    echo "== frontend =="; cd "$DESKTOP"; npm run test ;;
  lint)
    echo "== backend =="; cd "$API"; "$PY" -m ruff check onestats tests
    echo "== frontend =="; cd "$DESKTOP"; npm run lint ;;
  build)
    cd "$DESKTOP"; npm run tauri build ;;
  migrate)
    cd "$API"; "$PY" -m alembic upgrade head ;;
  stop)
    for PORT in 8000 1420; do
      PID=$(netstat -ano 2>/dev/null | grep ":$PORT " | grep LISTENING | awk '{print $NF}' | head -1)
      [ -n "${PID:-}" ] && taskkill //F //PID "$PID" >/dev/null 2>&1 && echo "stopped :$PORT" || true
    done ;;
  *)
    usage; exit 1 ;;
esac
