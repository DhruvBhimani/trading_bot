# Local simulator milestone

The simulator runs entirely offline using the Python standard library. The existing
Java backend remains the foundation for future services; this research tool is independent.

## What it does

- Tracks one token, cash, and at most one open position.
- Tracks a running peak and the subsequent low. A new peak resets the low.
- Signals entry after the peak-to-low pullback and subsequent recovery meet the configuration.
- Fills signals at the next observation, with adverse slippage and fees on both sides.
- Allocates a fraction of available cash, including entry fees, to each purchase.
- Signals exits for stop loss, take profit, or elapsed holding bars. Stops are triggers,
  not guaranteed fill prices: a gap can produce a much larger loss.
- Reports net cash profit, liquidation-value equity, drawdown, trades, and decisions.

All percentages in configuration are fractions except costs, which use basis points
(100 basis points = 1%). The default 2% allocation is an illustrative test setting,
not a calibrated recommendation. Prices are positive, equally spaced observations.
The sample interval is 15 minutes. Hold duration counts observations, not wall time.

## Deliberate limitations

This is synthetic data, not Solana history. Results are not evidence of an edge.
No wallet ranking, token safety, liquidity checks, market impact curve, network costs,
MEV, failed transactions, or inability to sell are modeled. Fixed slippage cannot
represent a collapsing pool. A final open position is marked liquidated at the last
price with costs; this reporting convention does not guarantee an executable sale.
A pending buy on the last observation is discarded. A prior buy may fill on that
last observation and be immediately marked liquidated, paying both sides' costs.
Repeated entries can occur while the same pullback condition remains valid.

Only the configured strategy and observed prices inform decisions; no optimization
or claim of out-of-sample validation is included. The simulator currently supports
one token, not a shared multi-token portfolio.

## Custom runs

```bash
python3 research/backtests/local_simulator.py --config config/local-simulator.json --data research/fixtures/demo-prices.json --output research/output/my-run.json
```

Input JSON contains a `prices` list and optional descriptive metadata. Keep the
`synthetic` flag accurate. Reports include their configuration and dataset metadata.

## Next implementation milestone

Define timestamped, point-in-time historical observations, including data availability
time, missing intervals, liquidity, and dead tokens. Then implement chronological
multi-token replay with shared cash and execution constraints. Align Java and Python
on shared test fixtures before treating their results as interchangeable. Only then
use untouched evaluation periods and forward paper trading to assess a strategy.

## Local version control

This folder already has a Git repository. No remote connection is needed to use Git.
Existing uncommitted work has been preserved; this milestone makes no commits or pushes.
After reviewing files with `git status` and `git diff`, stage selected source files
with `git add <paths>` and save a snapshot with `git commit -m "Add offline simulator"`.
Do not stage credentials or private datasets. A hosted remote is optional and can
be connected later for backup.
