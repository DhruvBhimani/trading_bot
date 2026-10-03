"""Run the Java backtest API and print trade summary (requires backend running)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get("BACKEND_URL", "http://localhost:8080")


def post(path: str) -> dict:
    req = urllib.request.Request(f"{BASE}{path}", method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def get(path: str) -> dict | list:
    with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as resp:
        return json.loads(resp.read().decode())


def main() -> None:
    try:
        load = post("/api/admin/load-sample-data")
        print("load-sample-data:", json.dumps(load, indent=2))
        summary = post("/api/backtest/run")
        print("backtest:", json.dumps(summary, indent=2))
        run_id = summary.get("run_id")
        if run_id:
            trades = get(f"/api/backtest/{run_id}/trades")
            print(f"trades ({len(trades)}):")
            for trade in trades:
                print(
                    f"  {trade.get('mint_address')} pnl={trade.get('pnl_pct')}% exit={trade.get('exit_reason')}"
                )
    except urllib.error.URLError as exc:
        print(f"Backend not reachable at {BASE}: {exc}")
        print("Start backend: cd backend && ./gradlew bootRun")


if __name__ == "__main__":
    main()
