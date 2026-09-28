"""
Minimal backtest skeleton — replace synthetic data with DB/CSV historical snapshots.

Strategy v0: buy when drawdown from local high >= 30% and recovery from low >= 5%.
Exit: stop -25%, take profit +50%, or max hold 24h (synthetic bars).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class StrategyParams:
    min_drawdown_pct: float = 30.0
    min_recovery_pct: float = 5.0
    stop_loss_pct: float = 25.0
    take_profit_pct: float = 50.0
    max_bars: int = 96  # e.g. 15m bars → 24h


@dataclass
class BacktestResult:
    trades: int
    win_rate: float
    avg_pnl_pct: float
    median_pnl_pct: float
    max_drawdown_pct: float
    total_return_pct: float


def synthetic_token_series(seed: int, bars: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    returns = rng.normal(0.002, 0.04, size=bars)
    price = 100 * np.exp(np.cumsum(returns))
    return pd.DataFrame({"close": price})


def run_backtest(prices: pd.Series, params: StrategyParams) -> list[float]:
    pnls: list[float] = []
    i = 20
    while i < len(prices) - 1:
        window = prices.iloc[: i + 1]
        local_high = window.max()
        local_low = window.min()
        drawdown = (local_high - prices.iloc[i]) / local_high * 100
        recovery = (prices.iloc[i] - local_low) / local_low * 100 if local_low > 0 else 0

        if drawdown >= params.min_drawdown_pct and recovery >= params.min_recovery_pct:
            entry = prices.iloc[i]
            exit_price = entry
            exit_idx = i
            for j in range(i + 1, min(i + 1 + params.max_bars, len(prices))):
                move = (prices.iloc[j] - entry) / entry * 100
                exit_price = prices.iloc[j]
                exit_idx = j
                if move <= -params.stop_loss_pct or move >= params.take_profit_pct:
                    break
            pnl = (exit_price - entry) / entry * 100
            pnls.append(float(pnl))
            i = exit_idx + 1
            continue
        i += 1
    return pnls


def summarize(pnls: list[float], starting_equity: float = 10_000.0) -> BacktestResult:
    if not pnls:
        return BacktestResult(0, 0.0, 0.0, 0.0, 0.0, 0.0)

    equity = starting_equity
    peak = equity
    max_dd = 0.0
    for p in pnls:
        equity *= 1 + p / 100
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)

    arr = np.array(pnls)
    wins = (arr > 0).sum()
    return BacktestResult(
        trades=len(pnls),
        win_rate=float(wins / len(pnls)),
        avg_pnl_pct=float(arr.mean()),
        median_pnl_pct=float(np.median(arr)),
        max_drawdown_pct=float(max_dd),
        total_return_pct=float((equity - starting_equity) / starting_equity * 100),
    )


def main() -> None:
    params = StrategyParams()
    all_pnls: list[float] = []
    for seed in range(50):
        df = synthetic_token_series(seed)
        all_pnls.extend(run_backtest(df["close"], params))

    result = summarize(all_pnls)
    out_dir = Path(__file__).resolve().parents[1] / "output"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / "simple_backtest_summary.json"
    payload = {"params": asdict(params), "result": asdict(result)}
    out_path.write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
