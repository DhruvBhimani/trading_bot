"""Offline, single-token teaching simulator. No network or trading credentials."""
import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Config:
    starting_cash: float = 10000
    allocation: float = 0.02
    fee_bps: float = 30
    slippage_bps: float = 50
    pullback: float = 0.30
    recovery: float = 0.05
    stop_loss: float = 0.25
    take_profit: float = 0.50
    max_hold_bars: int = 8

    def validate(self):
        for key, value in asdict(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError('Invalid numeric config: ' + key)
        if self.starting_cash <= 0 or not 0 < self.allocation <= 1:
            raise ValueError('Cash must be positive; allocation must be in (0, 1]')
        if not 0 <= self.fee_bps < 10000 or not 0 <= self.slippage_bps < 10000:
            raise ValueError('Costs must be in [0, 10000) basis points')
        if not 0 < self.pullback < 1 or not 0 < self.stop_loss < 1:
            raise ValueError('Pullback and stop loss must be in (0, 1)')
        if self.recovery <= 0 or self.take_profit <= 0:
            raise ValueError('Recovery and profit threshold must be positive')
        if self.max_hold_bars < 1 or int(self.max_hold_bars) != self.max_hold_bars:
            raise ValueError('max_hold_bars must be a positive integer')


def simulate(prices, config):
    config.validate()
    if not prices or any(isinstance(p, bool) or not isinstance(p, (int, float))
                         or not math.isfinite(p) or p <= 0 for p in prices):
        raise ValueError('Prices must be a nonempty list of finite positive numbers')
    cash = peak_equity = config.starting_cash
    fee, slip = config.fee_bps / 10000, config.slippage_bps / 10000
    high = low = prices[0]
    position = pending = None
    trades, curve, decisions = [], [], []
    max_drawdown = 0

    def close(bar, price, reason):
        nonlocal cash, position
        fill = price * (1 - slip)
        proceeds = position['quantity'] * fill * (1 - fee)
        cash += proceeds
        trades.append({**position, 'exit_bar': bar, 'exit_fill': fill,
                       'exit_reason': reason, 'net_pnl': proceeds - position['cost']})
        position = None

    for i, price in enumerate(prices):
        # A decision at bar t fills at t+1, never at the observed signal price.
        if pending is not None:
            action, reason = pending
            if action == 'BUY':
                cost = cash * config.allocation
                fill = price * (1 + slip)
                position = {'entry_bar': i, 'entry_fill': fill, 'cost': cost,
                            'quantity': cost / (fill * (1 + fee))}
                cash -= cost
            else:
                close(i, price, reason)
            pending = None

        # Recovery low must occur after the peak, not before it.
        if price >= high:
            high = low = price
        else:
            low = min(low, price)

        if position is not None:
            move = price / position['entry_fill'] - 1
            reason = ('STOP_LOSS' if move <= -config.stop_loss else
                      'TAKE_PROFIT' if move >= config.take_profit else
                      'MAX_HOLD' if i - position['entry_bar'] >= config.max_hold_bars else None)
            if reason:
                pending = ('SELL', reason)
        elif (high - low) / high >= config.pullback and price / low - 1 >= config.recovery:
            pending = ('BUY', 'PULLBACK_RECOVERY')

        if i == len(prices) - 1:
            # Explicit reporting convention, not a prediction of an executable exit.
            if position is not None:
                close(i, price, 'END_OF_DATA_MARK_LIQUIDATION')
            pending = None
        if pending:
            decisions.append({'signal_bar': i, 'action': pending[0], 'reason': pending[1]})
        equity = cash + (position['quantity'] * price * (1 - slip) * (1 - fee) if position else 0)
        peak_equity = max(peak_equity, equity)
        max_drawdown = max(max_drawdown, 1 - equity / peak_equity)
        curve.append({'bar': i, 'cash': cash, 'liquidation_equity': equity})

    return {'config': asdict(config), 'summary': {
        'trades': len(trades), 'ending_cash': cash,
        'net_pnl': cash - config.starting_cash,
        'return_pct': 100 * (cash / config.starting_cash - 1),
        'max_drawdown_pct': 100 * max_drawdown,
        'win_rate': sum(t['net_pnl'] > 0 for t in trades) / len(trades) if trades else None,
    }, 'trades': trades, 'decisions': decisions, 'equity_curve': curve}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=root / 'config/local-simulator.json')
    parser.add_argument('--data', type=Path, default=root / 'research/fixtures/demo-prices.json')
    parser.add_argument('--output', type=Path, default=root / 'research/output/local-simulation.json')
    args = parser.parse_args()
    try:
        dataset = json.loads(args.data.read_text())
        result = simulate(dataset['prices'], Config(**json.loads(args.config.read_text())))
        result['dataset'] = {k: v for k, v in dataset.items() if k != 'prices'}
        result['limitations'] = ['Single token; equally spaced observations.',
            'Fixed proportional costs; no liquidity, MEV, outages, or failed fills modeled.',
            'Final position marked liquidated at last observation; execution not guaranteed.',
            'Synthetic demo validates mechanics, not profitability.']
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result['summary'], indent=2))
    print('Report:', args.output)


if __name__ == '__main__':
    main()
