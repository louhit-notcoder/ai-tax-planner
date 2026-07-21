#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHONPATH=backend python -m compileall -q backend/app backend/main.py
node scripts/check_frontend_syntax.js
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=backend pytest -q backend/tests_v3
python scripts/verify_no_embedded_secrets.py
