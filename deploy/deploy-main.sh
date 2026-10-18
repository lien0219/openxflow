#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
command -v python3 >/dev/null 2>&1 || {
  printf '[openxflow-deploy] ERROR: Python 3.10+ is required\n' >&2
  exit 1
}
python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' || {
  printf '[openxflow-deploy] ERROR: Python 3.10+ is required\n' >&2
  exit 1
}
exec python3 "$SCRIPT_DIR/deploy_main.py" "$@"
