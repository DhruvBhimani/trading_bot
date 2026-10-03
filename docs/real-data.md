# Real market data ingestion

The first provider adapter imports GeckoTerminal public pool OHLCV using Python's
standard library. No API key is required for this public endpoint. Network access
is required when fetching, but saved responses can be normalized offline.

```bash
python3 research/ingestion/import_gecko.py --pool 58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2 --timeframe minute --aggregate 15
```

The example pool is SOL/USDC, selected from the public Solana pool listing solely
for an integration check. It is not a selected trading opportunity or a meme-coin
research universe. The initial real download yielded 999 completed 15-minute
candles, with one unfinished candle excluded. No strategy was run on this data.

The importer saves the original bytes in `data/raw/<sha256>.json` and writes a
normalized report to `data/processed/<pool>-<retrieval-time>.json`. Reports include
request URL, retrieval time, raw hash, base-token address, interval boundaries,
missing-interval findings, and explicit research blockers. Data files are ignored
by Git. The existing synthetic fixtures are unchanged.

## Commands and scope

- `--timeframe`: minute, hour, or day; choose a matching `--aggregate`.
- Minute aggregates: 1, 5, 15. Hour: 1, 4, 12. Day: 1.
- `--before`: request an older page using an epoch timestamp.
- `--raw-input <file> --retrieved-at <ISO timestamp>`: import saved response bytes.
  Record the actual retrieval timestamp; do not use a historical candle time.
- `--archive-dir` and `--output-dir`: override local destinations.

One invocation downloads at most one page (up to 1000 rows). It does not claim full
history or paginate automatically. If a request fails or is rate-limited, it exits
with an error instead of silently substituting sample data. Unknown schemas,
invalid OHLC bounds, duplicate timestamps, and nonfinite values are rejected.

Price is explicitly requested in USD for the pool's base token. The importer treats
provider timestamps as interval starts and excludes any interval that has not ended
by retrieval. Historical publication times remain unknown. Missing intervals are
reported, never forward-filled. Before research, verify timestamp conventions and
selected candles against provider records and underlying swaps.

## Why these bars cannot yet produce a portfolio backtest

OHLCV provides prices and volume, not historical liquidity, sellability evidence,
or historical information availability. Current pool liquidity must not be copied
backwards into past candles. Download time is not historical availability time.
A nonzero price or volume does not prove that our order could have sold.

Normalized output therefore uses `market-bars-v1`, not the portfolio observation
schema. Its `execution_backtest_ready` flag is false and missing fields remain
null. The existing simulator rejects this schema. There is no switch that fabricates
liquidity or treats these candles as validated execution data.

The next integration needs historical pool liquidity and tradability evidence,
plus an explicit availability/latency model. It also needs a universe selected
without hindsight, including failed and disappeared tokens. Provider snapshots
must be joined by information available at each decision time, with bounded age;
no backward filling from future records. Keep missing evidence explicit.

## Provider research, checked 2026-09-28

- [GeckoTerminal public API overview](https://apiguide.geckoterminal.com/)
  describes public pool market data and historical OHLCV.
- [CoinGecko pool OHLCV reference](https://docs.coingecko.com/reference/pool-ohlcv-contract-address)
  documents the OHLCV array, token/currency selection, interval aggregation, and
  missing-trade intervals. This is the related CoinGecko API documentation; do not
  assume its paid-plan history entitlements apply to the public endpoint.
- [Birdeye token liquidity history announcement](https://birdeye.so/data-api/blog/detail/new-apis-token-liquidity-history-track-solana-token-liquidity-over-time)
  describes historical Solana liquidity products. Account access, endpoint schema,
  coverage, pool-versus-token aggregation, and cost must be checked before integration.

No paid service has been purchased or configured. A Birdeye API key may be useful
for the next adapter, but must be stored locally in an ignored environment file,
not pasted into chat or committed. Price data alone does not resolve the blockers.
