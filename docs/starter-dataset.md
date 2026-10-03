# Five-token starter dataset

The curated manifest is `config/starter-cohort.json`: BONK, WIF and POPCAT
(historical runners), SHAR (documented rug case), LIBRA (alleged rug / liquidity
withdrawal case). Full mint and pool addresses, source links and requested event
windows are recorded. These are retrospectively selected engineering cases, not
an unbiased universe or investment recommendations. The strategy cannot see labels.

## Free-source limitation

GeckoTerminal Public API returned HTTP 401 stating historical access is restricted
to the past 180 days. The March 2024 rally, October 2024 SHAR collapse and February
2025 LIBRA event are older. Their error responses and unavailable status are stored;
they are **not** treated as successful tests or zero-return outcomes.

The collector separately requests seven recent days of hourly OHLCV for all five
tokens. Those prices test storage and replay, **not the original events**. Sparse
windows remain sparse: no fabricated candles, liquidity or tradability. There is
no paid API, plan upgrade, background job, wallet signing or live order placement.

## Verified first collection (2026-09-29)

Neon dataset **1** contains **542 hourly candles** for the recent seven-day window:
BONK 168, WIF 168, POPCAT 168, SHAR 4, LIBRA 34. All five event-window requests
returned provider-unavailable errors. Raw responses and metadata are saved remotely.

Saved report **2** records the blocked event replay. Saved report **3** replays
the three complete recent windows; the configured pullback/recovery rules generated
**zero trades**. SHAR and LIBRA are explicitly skipped for incomplete coverage.
Neither zero trades nor skipped cases constitute evidence of strategy profitability.
Both reports were replayed twice with identical results and read back from Neon.
All 42 offline regression tests passed. No database schema changes were made.

## Commands (from the repository root)

```bash
# Save a new bounded cohort in configured Neon PostgreSQL.
research/.venv/bin/python research/ingestion/starter_dataset.py collect

# Inspect the dataset ID printed by collection (replace 1 if needed).
research/.venv/bin/python research/ingestion/starter_dataset.py show 1

# Resume an interrupted collection, preserving completed coins and window dates.
research/.venv/bin/python research/ingestion/starter_dataset.py collect --resume 1

# Default event replay refuses unavailable windows.
research/.venv/bin/python research/backtests/starter_backtest.py 1 --window event

# Explicitly run the recent-price diagnostic with the existing baseline rules.
research/.venv/bin/python research/backtests/starter_backtest.py 1 --window recent

# Read a report using its printed saved_report_id.
research/.venv/bin/python research/ingestion/starter_dataset.py report REPORT_ID

# Verify determinism and save both reports again (requires the existing Neon connection).
research/.venv/bin/python scripts/verify-starter-dataset.py 1

# Offline regression tests; their temporary SQLite databases are test fixtures only.
research/.venv/bin/python -m unittest discover -s research/tests -q
```

Production storage uses existing `market_research` tables: raw responses/fetches,
pool metadata, versioned candles, and `collection_runs.config_json` envelopes
(`starter_dataset_v1` / `starter_backtest_v1`). No schema migration is needed.
Provider failures are retained as raw evidence; fatal failures leave a checkpoint.
Collection paces requests 12 seconds apart and stops on a rate limit. Rerun with
`--resume` later. The 300 MB application storage guard remains active.

Reports pin fetch IDs rather than querying latest prices, and store parameters,
strategy source hash, candle snapshot hash, trades and coverage. Replays do not
fetch market data. Existing reports retain their results even after new collection.

## What the baseline means

This reuses the educational pullback/recovery simulator, not a new profitable
strategy. Each coin has an independent $10,000 virtual account, 2% allocation,
30 bps fees and 50 bps slippage per side (configurable in
`config/local-simulator.json`). Signals use hourly closes and fills use the next
hourly close. Complete consecutive windows only; incomplete ones are skipped.
There is no combined portfolio return. The final mark-liquidation convention
is hypothetical, not an executable exit. Fee/slippage assumptions cannot replace
historical liquidity, tradability, transaction costs or failed-fill evidence.

Next data milestone: source verified free event-period archives or capture future
events prospectively. Until then we cannot claim to have tested rug survival.
Live paper ingestion and a user dashboard remain separate unfinished milestones.
