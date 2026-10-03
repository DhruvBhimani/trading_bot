# Current wallet and live-discovery update

See [today’s saved checkpoint](../docs/today-handoff.md) for the current implementation,
validation and remaining work. **Live tokens** shows confirmed Pump.fun launch and
PumpSwap pool creation events over WebSocket. **Wallets & trading** supports
Phantom/watch-only wallets and encrypted bot wallets with explicit automatic-signing
sessions. Real submission defaults off. Automatic strategy decisions are not wired.

The earlier guide below describes the manual swap/paper paths; its statement that
every trade needs Phantom approval applies only to the Phantom path. Bot-wallet
queues sign automatically when enabled. Use a dedicated funded trading wallet,
export recovery before funding, and review the limits in the checkpoint.

# Local trading desk

Run `python3 app/server.py` from the repository root and open http://127.0.0.1:8765.
Python 3.9+ runs the paper lab. Wallet transaction validation also requires Node
and `npm install`. The checked-in browser bundle is ready to serve.

## Paper lab

Create a named demo run or replay an imported dataset, start/pause/step it,
reopen saved runs, compare results, export data and back up SQLite. Configuration
is fixed per run. Restarts restore the active run paused. Closing the browser does
not pause execution. Demo prices are fictional; demo profits prove no edge.
Charts offer 5-second, 10-second and one-minute aggregation.

Import JSON with `schema_version: "observations-v1"`, a `name`, and `observations` containing
`timestamp` (Unix seconds), `symbol`, `price`, `liquidity` (USD or null), and optional
`token` (mint) and `pool` addresses. Maximum 50,000 observations / 10 MB per import.
Export an existing run for a complete example. Replay pins the dataset cutoff.

## Phantom and actual pool swaps

The Wallet swaps tab requests Jupiter Swap V2 routes through actual liquidity
pools. It shows pool addresses, route venues, minimum output, impact and fees.
This is a manual mainnet execution path, separate from synthetic paper trades.
It does not use DEX Screener price snapshots to fill trades.

Connect Phantom in a browser with its extension installed. Private keys remain
in Phantom. Quotes expire after 20 seconds. The server defaults to submission
disabled; to intentionally enable manual mainnet swaps, start it with:

```
python3 app/server.py --enable-live-swaps
```

Each swap still needs a UI confirmation and Phantom signature. Current limits:
allowlisted SOL/USDC/BONK/WIF/POPCAT, $5 input value, maximum 1% slippage and 1%
price impact. The server verifies the signed message and signature, simulates the
transaction and rejects duplicate submissions. Unknown submission outcomes retain
the signature for reconciliation; never assume a timeout means no trade occurred.
Use Check confirmation to retrieve chain status and balance-change receipts.

Optional process environment variables: `SOLANA_RPC_URL`, `JUPITER_API_KEY`.
The Python app does not automatically load `.env` files. Public RPC and keyless
Jupiter quotes worked during verification; rate limits and availability can vary.
Network and swap fees require real SOL even though the local app is free.

No real wallet transaction was signed or submitted during development verification.
Continuous pool-event ingestion, wallet-wide holdings/cost-basis accounting,
automatic strategy-to-wallet execution and direct launch/bonding-curve support
are not implemented. A Phantom connection alone cannot run unattended trades.

## Code and storage

- `app/engine.py`: paper accounting, orders, immutable run configuration and replay.
- `app/strategy.py`: placeholder entry/exit rules; version changes require a new run.
- `app/feeds.py`: validated observation contract and synthetic adapter.
- `app/store.py`: structured local SQLite persistence and backup.
- `app/wallet.py`: real routes, simulation, submission and chain reconciliation.
- `app/wallet_guard.cjs`: transaction-message and signature validation.
- `frontend/wallet-entry.js`: Phantom browser integration.
- `data/local/paper-bot.sqlite3`: local runs/data/wallet order records, ignored by Git.

Legacy demo records are retained and imported as completed historical runs. SQLite
capacity depends on available disk and workload; it is not unlimited. Existing Java,
research and Neon tools remain separate. No hosted database is required by this UI.

## Verification

```
PYTHONPYCACHEPREFIX=/tmp/db-bot-pycache python3 -m unittest discover -s app -p 'test_*.py' -q
node app/test_wallet_guard.cjs
node --check frontend/app.js
npm run build:wallet
```

Tests cover accounting, next-observation fills, liquidity loss, order expiry,
transaction rollback, restart/replay, imports/backups, HTTP guards, quote limits,
failed simulation, uncertain submissions and signature/message tampering.
The SDK dependency tree currently reports four moderate npm audit advisories;
this prototype has not undergone a production security audit.

## On-chain activity collector

In Wallet swaps, paste a pool address from a quoted route into **Watch address**.
The collector follows up to five addresses using finalized Solana RPC transactions
at 15-second intervals. It stores signatures, address associations, raw receipts,
pagination checkpoints and receipt retry state in the same local SQLite database.
Pause/resume controls stop/start discovery; already queued receipts still download.

Initial coverage is the latest 20 transactions, not full historical coverage.
Catch-up paginates to the saved checkpoint; missing provider history is explicitly
shown as a gap. Receipt downloads are limited to two per cycle and retry with
backoff. Busy pools can outpace this free-RPC prototype. This is actual transaction
collection, not a low-latency WebSocket stream or a decoded swap/candle feed.
Transactions referencing a pool can include non-swap instructions; the UI does not
infer prices or trading signals from them. Raw events are retained for later decoding.

## Live trade candles (2026-09-30)

Open Live tokens → View live trades on a Pump.fun token card. The chart supports
1/5/10/60-second candles from observed SOL-quoted trade events, with recent fills
and transaction links. Missing intervals remain empty. The feed tracks at most 100
recent/selected mints; older records stay in SQLite. Opening a chart renews tracking.
Decimals are verified through RPC before displaying SOL/token prices. Displayed
reserves are those reported by the last received trade, not guaranteed current
liquidity. PumpSwap swaps, non-SOL quotes, downtime backfill and finalized-history
reconciliation are not included in this adapter.
