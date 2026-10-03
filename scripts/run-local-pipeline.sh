#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "Starting PostgreSQL..."
docker compose up -d

echo "Waiting for database..."
until docker compose exec -T postgres pg_isready -U solana_quant -d solana_quant >/dev/null 2>&1; do
  sleep 1
done

echo "Loading sample data + backtest + paper tick..."
curl -s -X POST http://localhost:8080/api/admin/load-sample-data | python3 -m json.tool
curl -s -X POST http://localhost:8080/api/backtest/run | python3 -m json.tool
curl -s -X POST http://localhost:8080/api/paper/tick | python3 -m json.tool
curl -s http://localhost:8080/api/paper/status | python3 -m json.tool
