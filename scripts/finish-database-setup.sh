#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
PYTHON="$PROJECT_ROOT/research/.venv/bin/python"
"$PYTHON" research/ingestion/collect_market.py status
if [[ -f data/processed/market.sqlite3 ]]; then
  "$PYTHON" research/ingestion/migrate_local.py
fi
"$PYTHON" research/ingestion/collect_market.py status
