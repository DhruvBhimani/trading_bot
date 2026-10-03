# Timestamped portfolio replay

Run from the project folder, using Python 3.9+ with no additional packages:

```bash
python3 research/backtests/portfolio_simulator.py
python3 -m unittest discover -s research/tests -v
```

Configuration: `config/portfolio-simulator.json`. Results:
`research/output/portfolio-simulation.json`. You can pass `--data`, `--config`,
and `--output` paths. The report saves the configuration and SHA-256 of the input.
The single-token simulator remains available as the simpler teaching example.

## Historical input contract

JSON format (the bundled fixture is synthetic):

```json
{
  "schema_version": 1,
  "synthetic": false,
  "source": "Record the actual provider and collection method here",
  "observations": [
    {
      "token": "Use the full mint address for real data",
      "observed_at": "2026-01-01T00:00:00Z",
      "available_at": "2026-01-01T00:00:01Z",
      "price_usd": 0.001,
      "liquidity_usd": 50000,
      "tradable": true
    }
  ]
}
```

`observed_at` is the source observation time; `available_at` is the first time the
system could have known the observation. Do not substitute historical event time
for availability time without documenting that assumption. Actual historical
availability often cannot be recovered from a price API. Both require explicit
timezones; availability cannot precede observation. Duplicate token/observation
times are rejected. Nonfinite numbers, negative prices/liquidity, and zero prices
for tradable observations are rejected. Zero price is allowed for untradeable assets.

Rows are sorted by availability time. Older observations arriving after newer ones
are logged and ignored. Multiple updates at the same availability time are coalesced
to the newest observation per token. Future rows do not affect earlier decisions.

## Execution and portfolio rules

- One shared cash balance; fixed dollar budget per entry, including fees.
- Maximum open positions; one position and at most one pending order per token.
- A signal can fill only on an observation timestamp strictly after its creation.
- At simultaneous updates, sell orders execute first, then buys; token identifier
  breaks ties. This is deterministic, not an optimized allocation policy.
- No cash reservation for pending buys. Cash and position limits are checked on fill.
- Orders expire after the configured elapsed seconds. Failed buys are cancelled;
  failed sells remain pending until expiration and can be signaled again later.
- Minimum liquidity applies to buys. Both sides must fit within the configured
  fraction of liquidity. Orders are all-or-nothing; there are no partial fills.
- Stale or untradeable observations cannot fill orders or generate new signals.
- Stop/target/holding rules are evaluated when fresh token data arrives. Missing
  data does not invent an executable quote or guarantee an exit at the deadline.
- Entry uses the running peak, subsequent low, and recovery. Repeated entries are
  allowed while conditions persist. There is no wallet or safety filter yet.

The flat fee and slippage assumptions are approximations, not a pool execution
model. Liquidity is not consumed across tokens or pools. No network fees, failed
transaction fees, MEV, routing, or transaction confirmation model is implemented.

## Reporting and failure handling

There is **no automatic final sale**. Remaining positions and orders are reported
explicitly. Net P&L includes conservative marks, while realized P&L includes only
closed trades. Cash changes reconcile to the execution ledger.

For conservative equity, a position gets zero value when its last observation is
stale, untradeable, or insufficiently liquid under the configured participation cap.
Otherwise the mark deducts hypothetical exit costs. This zero is an accounting
assumption, not proof of permanent loss; marks may recover with fresh information.
Drawdown uses these marks at each dataset availability timestamp. No additional
clock ticks are generated after the final observation, and gaps between events
are not sampled. This is not a continuous-time risk monitor.

The demo includes multiple tokens, a disappearing data stream, and an explicitly
untradeable observation. Synthetic returns do not validate a trading strategy.

## Real-data work still required

A real OHLCV import path now exists; see [real-data ingestion](real-data.md).
It does not yet supply execution-ready historical observations. Before performance research, select
a source that provides historical token/pool coverage (including failed tokens),
liquidity and tradability evidence, timestamps, and documented missing-data behavior.
Do not select only today's surviving tokens or relabel synthetic fixtures as real.
The `tradable` field is supplied by the dataset; the simulator does not independently
verify token sellability. Preserve raw source records for audit and normalization.

Next, build and validate a provider adapter, reconcile selected observations with
raw transactions, and define chronological research/evaluation periods before
searching strategy parameters. Java integration remains a separate milestone;
its existing backtest is not equivalent to this portfolio engine.
