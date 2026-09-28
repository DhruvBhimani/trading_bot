# Solana Meme-Coin Quant Engine

Research-first stack: historical data → backtests → paper trading → live execution (disabled until validated).

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
# Database
docker compose up -d

# Backend
cd backend && ./gradlew bootRun

# Research (after venv + deps)
cd research && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python backtests/run_simple_backtest.py
```

Copy `.env.example` to `.env` and adjust credentials before connecting services.

## Build order (do not skip)

1. Database schema + sample/historical data pipeline  
2. Backtesting framework + one trivial strategy  
3. Wallet stats + token safety filters  
4. Real-time ingestion + paper trading  
5. Dashboard  
6. Small live capital only after paper matches backtest expectations  

**There is no foolproof strategy.** The goal is measurable edge, strict risk caps, and honest out-of-sample testing.
