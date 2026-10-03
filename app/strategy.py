"""Placeholder paper rules, separate from execution. No profitability claim."""
VERSION = 'paper-momentum-placeholder-v2'


def entry_signal(current_price, past_price, config):
    return current_price / past_price - 1 >= config['momentum']


def exit_reason(row, position, config):
    move = row['price'] / position['entry'] - 1
    return ('Liquidity vanished' if not row['liquidity'] else
            'Stop loss' if move <= -config['stop_loss'] else
            'Take profit' if move >= config['take_profit'] else
            'Time exit' if row['timestamp'] - position['entry_time'] >= config['max_hold_seconds'] else None)
