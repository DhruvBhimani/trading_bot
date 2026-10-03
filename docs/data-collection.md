# Collection design and legacy local storage

**Updated:** hosted PostgreSQL is now the default. Follow [hosted setup](hosted-database.md).
The local commands below document the preserved legacy store and explicitly select it.

Legacy database: `data/processed/market.sqlite3` (SQLite, stored on this Mac).
The research collector uses Python 3.9+ and no third-party packages. Docker was not
running during setup, so this database is independent of the Java application's
PostgreSQL database. Java does not yet query this research store.

The existing download was imported: 20 pools, 14 distinct base tokens, and 999
15-minute SOL/USDC candles. These are different coverage measures. The bulk
collector has been implemented but its network permission was declined; it was
not launched. No 1,000-token dataset is claimed.

## Inspect what is actually stored

From the project root:

```bash
python3 research/ingestion/collect_market.py --database data/processed/market.sqlite3 status
python3 research/ingestion/collect_market.py --database data/processed/market.sqlite3 coverage
```

Status reports discovered tokens, tokens with prices, unique candles, current
liquidity snapshots, job states, and the last run. Coverage reports candle counts
and first/last timestamps per pool. Token counts use distinct base mint addresses,
not symbols or pool counts. Quote-token metadata is retained separately.

## Start or resume collection

```bash
python3 research/ingestion/collect_market.py --database data/processed/market.sqlite3 run --target-tokens 1000 --days 7
```

This targets 1,000 distinct Solana base tokens, 15-minute prices, and the seven days
ending at a frozen cutoff. It requires internet access. Data availability may be
shorter, particularly for young pools. It does not guarantee 1,000 tokens with
seven complete days. The free API may not provide enough discoverable tokens or
history. The entire run may take over an hour; leave the terminal open. Closing it
or pressing Ctrl+C can stop the run. The same command resumes saved pending jobs.
No automatic schedule or background service has been installed.

The collector:

1. Discovers new, top, and per-DEX pools in round-robin pages, up to ten pages per
   source. This broadens discovery but is neither all Solana tokens nor an unbiased
   historical universe. Coins are stored as `unclassified`, not assumed meme coins.
2. Stops discovery when the database reaches the target distinct-base-token count,
   or available listing pages are exhausted. Batch boundaries may exceed the target.
3. Queues one deterministic representative pool per token (lexicographic pool
   address). This is reproducible but is not guaranteed to be the best execution pool.
4. Fetches historical candles backward, preserving raw responses and pagination
   checkpoints. Empty responses remain visible as source exhaustion, not zero prices.
5. Waits at least three seconds between requests, retries transient failures up to
   three attempts, and stops on a rate limit instead of hammering the provider.

A database-specific OS lock prevents simultaneous collector writers. Checkpoints
and price inserts commit together; interrupted pages can be fetched again safely.
A later fresh run can use `--cutoff 2026-10-01T00:00:00Z` (replace with your desired
past/current UTC end time). Without `--cutoff`, the latest run's end time is reused
so an ordinary restart does not continually create new jobs.

`range_fetched` means pagination reached the requested lower boundary, not that
every expected interval exists. `source_exhausted` means the provider returned no
older candles; it does not prove the token had no activity. `error` jobs preserve
an error for inspection and are not silently treated as success. A run status of
`finished` means its available queue was processed, not that data is execution-ready.

## Stored evidence and queries

- `tokens`, `pools`, `discoveries`: identities, first discovery, source fetch.
- `raw_responses`, `fetches`: original JSON bytes, SHA-256, URL, retrieval time.
- `pool_snapshots`: current liquidity/price when a listing was retrieved. Source
  cache/observation latency is unknown. Never join these backward into historical bars.
- `candle_versions`: immutable versions tied to provider fetches. `latest_candles`
  selects the most recently retrieved version per pool/interval/start timestamp.
- `jobs`, `collection_runs`: pagination, run window, progress and failures.

Example SQL for any SQLite client:

```sql
SELECT token, COUNT(*) AS candles, MIN(start) AS first_time, MAX(end) AS last_time
FROM latest_candles
GROUP BY token;
```

Export saved price data without contacting the provider:

```bash
python3 research/ingestion/collect_market.py --database data/processed/market.sqlite3 export --pool 58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2 --output research/output/sol-prices.json
```

The export is price-research data, not the simulator's execution observation schema.
No download is needed to reuse it. The original provider bytes and version history
allow later inspection or a corrected normalizer. For a consistent backup even
while collection is running:

```bash
python3 research/ingestion/collect_market.py --database data/processed/market.sqlite3 backup --output data/processed/market-backup.sqlite3
```

Choose a new filename for each backup. The backup uses SQLite's backup API; copying
only the main file while writes are active may omit its WAL transactions. Data is
ignored by Git and not automatically backed up off this Mac.

## Still missing for credible strategy tests

Historical liquidity, historical sellability, wallet trades, and token safety
history are not yet collected. Provider access is not configured for Birdeye.
The current liquidity snapshots cannot supply these missing historical fields.
Status explicitly reports zero execution-ready tokens until those inputs are
implemented and verified. We also need failed-token coverage and untouched test
periods; new/top pool listings alone cannot establish those.

Provider references and access caveats are in [real-data notes](real-data.md).
No paid API access, wallet connection, or real-money trading is configured.
