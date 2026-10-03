"""Point-in-time multi-token replay; offline and standard-library only."""
import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path


@dataclass
class Config:
    starting_cash: float = 10000
    position_budget: float = 200
    max_positions: int = 3
    fee_bps: float = 30
    slippage_bps: float = 50
    max_liquidity_fraction: float = .01
    min_liquidity: float = 10000
    pullback: float = .30
    recovery: float = .05
    stop_loss: float = .25
    take_profit: float = .50
    max_hold_seconds: int = 7200
    max_data_age_seconds: int = 120
    order_ttl_seconds: int = 1800

    def validate(self):
        for name, value in asdict(self).items():
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value <= 0:
                if name in ('fee_bps', 'slippage_bps', 'min_liquidity') and value == 0 and not isinstance(value, bool):
                    continue
                raise ValueError('Invalid configuration value: ' + name)
        if not 0 < self.max_liquidity_fraction <= 1 or not 0 < self.pullback < 1 or not 0 < self.stop_loss < 1:
            raise ValueError('Invalid fractional threshold')
        if self.max_positions != int(self.max_positions) or max(self.fee_bps, self.slippage_bps) >= 10000:
            raise ValueError('Invalid position count or costs')


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError('Timestamp must be an ISO-8601 string')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must include a timezone')
    return dt.timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def validate_dataset(dataset):
    if not isinstance(dataset, dict) or dataset.get('schema_version') != 1 or type(dataset.get('synthetic')) is not bool:
        raise ValueError('Dataset requires schema_version=1 and a boolean synthetic flag')
    rows = dataset.get('observations')
    if not isinstance(rows, list) or not rows:
        raise ValueError('observations must be a nonempty list')
    parsed, seen = [], set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('token'), str) or not row['token'].strip():
            raise ValueError('Every observation requires a token identifier')
        observed, available = timestamp(row['observed_at']), timestamp(row['available_at'])
        if available < observed:
            raise ValueError('available_at cannot precede observed_at')
        for name in ('price_usd', 'liquidity_usd'):
            value = row[name]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError('Invalid ' + name)
        if type(row.get('tradable')) is not bool:
            raise ValueError('tradable must be a boolean')
        if row['tradable'] and row['price_usd'] == 0:
            raise ValueError('Tradable observations need a positive price')
        key = (row['token'], observed)
        if key in seen:
            raise ValueError('Duplicate token observation timestamp')
        seen.add(key)
        parsed.append({**row, '_observed': observed, '_available': available})
    return sorted(parsed, key=lambda r: (r['_available'], r['token'], r['_observed']))


def simulate(dataset, config):
    config.validate()
    rows = validate_dataset(dataset)
    cash = peak = config.starting_cash
    max_dd = 0
    positions, orders, latest, extrema = {}, {}, {}, {}
    ledger, decisions, curve, rejected = [], [], [], []
    fee, slip = config.fee_bps / 10000, config.slippage_bps / 10000

    def mark(token, position, now):
        row = latest[token]
        # Stale or explicitly untradeable holdings have zero conservative marks.
        if now - row['_observed'] > config.max_data_age_seconds or not row['tradable']:
            return 0
        notional = position['quantity'] * row['price_usd']
        if notional > row['liquidity_usd'] * config.max_liquidity_fraction:
            return 0
        return notional * (1 - slip) * (1 - fee)

    for now, grouped in groupby(rows, key=lambda r: r['_available']):
        batch = {}
        for row in grouped:
            token = row['token']
            previous = latest.get(token)
            if previous and row['_observed'] <= previous['_observed']:
                rejected.append({'time': iso(now), 'token': token, 'reason': 'OUT_OF_ORDER'})
                continue
            latest[token] = row
            batch[token] = row
        for token, order in list(orders.items()):
            if now - order['created'] > config.order_ttl_seconds:
                rejected.append({'time': iso(now), 'token': token, 'reason': 'ORDER_EXPIRED'})
                del orders[token]
        # Sell before buy; token identifier breaks ties deterministically.
        for token in sorted(batch, key=lambda t: (orders.get(t, {}).get('side') != 'SELL', t)):
            row, order = batch[token], orders.get(token)
            if not order or row['_observed'] <= order['created']:
                continue
            reason = None
            fresh = now - row['_observed'] <= config.max_data_age_seconds
            if not fresh or not row['tradable']:
                reason = 'STALE_OR_UNTRADABLE'
            elif order['side'] == 'BUY':
                budget = order['budget']
                if len(positions) >= config.max_positions:
                    reason = 'POSITION_LIMIT'
                elif cash < budget:
                    reason = 'INSUFFICIENT_CASH'
                elif row['liquidity_usd'] < config.min_liquidity or budget > row['liquidity_usd'] * config.max_liquidity_fraction:
                    reason = 'LIQUIDITY_LIMIT'
                else:
                    fill = row['price_usd'] * (1 + slip)
                    positions[token] = {'quantity': budget / (fill * (1 + fee)), 'cost': budget,
                                        'entry_fill': fill, 'entry_time': iso(now), '_entry': now}
                    cash -= budget
                    ledger.append({'time': iso(now), 'token': token, 'side': 'BUY', 'fill': fill, 'cash_delta': -budget})
            else:
                position = positions[token]
                notional = position['quantity'] * row['price_usd']
                if notional > row['liquidity_usd'] * config.max_liquidity_fraction:
                    reason = 'LIQUIDITY_LIMIT'
                else:
                    fill = row['price_usd'] * (1 - slip)
                    proceeds = position['quantity'] * fill * (1 - fee)
                    cash += proceeds
                    ledger.append({'time': iso(now), 'token': token, 'side': 'SELL', 'fill': fill,
                                   'cash_delta': proceeds, 'net_pnl': proceeds - position['cost'], 'reason': order['reason']})
                    del positions[token]
            if reason:
                rejected.append({'time': iso(now), 'token': token, 'side': order['side'], 'reason': reason})
            # Failed exits stay pending until expiry; entries are cancelled on failure.
            if not reason or order['side'] == 'BUY':
                del orders[token]

        for token, row in sorted(batch.items()):
            if now - row['_observed'] > config.max_data_age_seconds or not row['tradable']:
                continue
            price = row['price_usd']
            high, low = extrema.get(token, (price, price))
            high, low = (price, price) if price >= high else (high, min(low, price))
            extrema[token] = high, low
            if token in orders:
                continue
            reason, side = None, None
            if token in positions:
                position = positions[token]
                move = price / position['entry_fill'] - 1
                reason = ('STOP_LOSS' if move <= -config.stop_loss else
                          'TAKE_PROFIT' if move >= config.take_profit else
                          'MAX_HOLD' if now - position['_entry'] >= config.max_hold_seconds else None)
                side = 'SELL'
            elif row['liquidity_usd'] >= config.min_liquidity and (high-low)/high >= config.pullback and price/low-1 >= config.recovery:
                side, reason = 'BUY', 'PULLBACK_RECOVERY'
            if reason:
                orders[token] = {'created': now, 'side': side, 'reason': reason, 'budget': config.position_budget}
                decisions.append({'time': iso(now), 'token': token, 'side': side, 'reason': reason})
        equity = cash + sum(mark(t, p, now) for t, p in positions.items())
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
        curve.append({'time': iso(now), 'cash': cash, 'conservative_equity': equity, 'open_positions': len(positions)})

    now = rows[-1]['_available']
    open_positions = {t: {k: v for k, v in p.items() if not k.startswith('_')} for t, p in positions.items()}
    for t, p in open_positions.items():
        p['conservative_value'] = mark(t, positions[t], now)
    equity = curve[-1]['conservative_equity']
    return {'config': asdict(config), 'dataset': {k: v for k, v in dataset.items() if k != 'observations'},
            'summary': {'ending_cash': cash, 'ending_conservative_equity': equity,
                        'net_pnl_including_marks': equity-config.starting_cash,
                        'return_pct': 100*(equity/config.starting_cash-1), 'max_drawdown_pct': 100*max_dd,
                        'closed_trades': sum(r['side'] == 'SELL' for r in ledger),
                        'realized_pnl': sum(r.get('net_pnl', 0) for r in ledger),
                        'open_positions': len(positions)},
            'open_positions': open_positions,
            'pending_orders': {t: {**o, 'created': iso(o['created'])} for t, o in orders.items()},
            'ledger': ledger, 'decisions': decisions, 'rejections': rejected, 'equity_curve': curve}


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=root/'research/fixtures/portfolio-demo.json')
    parser.add_argument('--config', type=Path, default=root/'config/portfolio-simulator.json')
    parser.add_argument('--output', type=Path, default=root/'research/output/portfolio-simulation.json')
    args = parser.parse_args()
    try:
        raw = args.data.read_bytes()
        result = simulate(json.loads(raw), Config(**json.loads(args.config.read_text())))
        result['data_sha256'] = hashlib.sha256(raw).hexdigest()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result['summary'], indent=2))
    print('Report:', args.output)


if __name__ == '__main__':
    main()
