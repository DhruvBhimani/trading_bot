# Solana Meme-Coin Quant Engine

Research-first stack: historical data → backtests → paper trading → live execution (disabled until validated).

## Open the working local paper-bot UI

```bash
python3 app/server.py
```

Open **http://127.0.0.1:8765**. The paper lab supports named runs, imported-data
replay, comparisons, short-interval charts and local SQLite backups. The Wallet
swaps tab supports Phantom signing and Jupiter routes through real liquidity
pools. Submission is disabled by default; no real-money trade has been verified.
See [the UI guide](frontend/README.md) for setup, controls and current limitations.

The **Live paper trading** page now compares momentum and verified migration
recovery using observed PumpSwap SOL trades and separate virtual accounts.
See [live paper setup, storage and simulation limits](docs/live-paper.md).

## Research direction

See [the saved strategy hypotheses and live-first learning plan](docs/strategy-direction.md). These are research priorities, not validated rug rules.

## Five-token database test

The [starter cohort workflow](docs/starter-dataset.md) collects BONK, WIF, POPCAT,
SHAR and LIBRA into Neon and saves repeatable price-only baseline reports.
Original rally/rug windows exceed the free provider's 180-day limit; recent
samples are tracked separately and do not validate rug survival. No live trading.

## Run the offline simulator first

No installation, database, API key, or wallet is needed. Works with Python 3.9+.
From this project folder:

```bash
python3 research/backtests/local_simulator.py
python3 -m unittest discover -s research/tests -v
```

Edit `config/local-simulator.json` to change the virtual balance, position allocation,
trading costs, and entry/exit thresholds. The report is saved to
`research/output/local-simulation.json`, including trades, decisions, and equity history.
See [simulator assumptions](docs/local-simulator.md) before interpreting results.

This is a standalone Python research milestone. It is not yet integrated with the
Java API. The older Python prototype and Java backtest use different accounting;
their results should not be compared as equivalent portfolio returns.

## Timestamped multi-token simulator

The next research milestone is available without Docker or extra packages:

```bash
python3 research/backtests/portfolio_simulator.py
```

It replays timestamped observations with shared cash, position limits, delayed fills,
liquidity limits, and explicit open positions. Edit `config/portfolio-simulator.json`.
Read [the input contract and execution assumptions](docs/portfolio-simulator.md).
The bundled replay dataset is synthetic. A real OHLCV importer is now available,
but its price-only output is not yet sufficient for portfolio backtesting.
See [real-data ingestion](docs/real-data.md) for the command and remaining data gaps.

## Hosted market-data storage

The collector now defaults to the linked Neon Free project through `.env.local`.
It uses `DATABASE_URL_UNPOOLED` for schema work and session locking. There is no
automatic local fallback. The original SQLite download is preserved as a migration source.

```bash
research/.venv/bin/python research/ingestion/collect_market.py status
research/.venv/bin/python research/ingestion/migrate_local.py
research/.venv/bin/python research/ingestion/collect_market.py run --target-tokens 1000 --days 7
```

The production migration is verified: 999 candles for one token, with discovery
metadata for 14 base tokens across 20 pools. See [setup summary](docs/neon-setup-summary.md).
Bulk collection has not started. Historical execution inputs remain incomplete.

## Layout

| Path | Role |
|------|------|
| `backend/` | Java — ingestion, features, signals, risk, execution |
| `research/` | Python — backtests, analysis, parameter sweeps |
| `database/` | PostgreSQL schemas and migrations |
| `frontend/` | React dashboard (later) |
| `data/` | Local datasets (`raw/`, `processed/`) |
| `config/` | Shared configuration |

## Prerequisites

- Java 21+ (you have a newer JDK; target bytecode is 21)
- Python 3.10+
- Docker (for PostgreSQL)
- Node.js (when you add the dashboard)

## Quick start

```bash
# 1) Database (Flyway migrations run when the backend starts)
docker compose up -d

# 2) Backend API
cd backend && ./gradlew bootRun

# 3) Load sample data → backtest → paper trade (new terminal)
curl -X POST http://localhost:8080/api/admin/load-sample-data
curl -X POST http://localhost:8080/api/backtest/run
curl -X POST http://localhost:8080/api/paper/tick
curl http://localhost:8080/api/paper/status
curl http://localhost:8080/api/signals/recent
```

Optional auto-load on startup:

```bash
BOOTSTRAP_SAMPLE_DATA=true ./gradlew bootRun
```

Python helper (backend must be running):

```bash
cd research && source .venv/bin/activate
python backtests/run_db_backtest.py
```

If Postgres was created before Flyway was added, reset the volume once:

```bash
docker compose down -v && docker compose up -d
```

Copy `.env.example` to `.env` and adjust credentials before connecting services.

## Current bot pipeline (v0.2)

1. **Token safety filter** — mint/freeze authority, LP lock, holder concentration, bundled launch
2. **Market quality** — minimum liquidity
3. **Smart-wallet signal** — tracked wallets with historical win rate (point-in-time in backtests)
4. **Price action** — drawdown + recovery confirmation
5. **Risk engine** — stop loss, take profit, max hold, emergency liquidity/safety exits
6. **Paper trading** — virtual portfolio (`live-enabled: false` always for now)

## Build order (do not skip)

1. Database schema + sample/historical data pipeline
2. Backtesting framework + one trivial strategy
3. Wallet stats + token safety filters
4. Real-time ingestion + paper trading
5. Dashboard
6. Small live capital only after paper matches backtest expectations

**There is no foolproof strategy.** The goal is measurable edge, strict risk caps, and honest out-of-sample testing.
