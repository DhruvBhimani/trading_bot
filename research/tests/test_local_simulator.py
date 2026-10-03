import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backtests'))
from local_simulator import Config, simulate


class SimulatorTests(unittest.TestCase):
    def test_no_signal_preserves_cash(self):
        result = simulate([100, 110, 120], Config())
        self.assertEqual(result['summary']['ending_cash'], 10000)
        self.assertEqual(result['trades'], [])

    def test_next_bar_fill_and_cost_accounting(self):
        result = simulate([100, 60, 64, 80, 80], Config())
        trade = result['trades'][0]
        self.assertEqual(trade['entry_bar'], 3)
        self.assertAlmostEqual(trade['entry_fill'], 80 * 1.005)
        expected = 200 / (80 * 1.005 * 1.003) * 80 * .995 * .997
        self.assertAlmostEqual(result['summary']['ending_cash'], 9800 + expected)
        self.assertLess(trade['net_pnl'], 0)

    def test_gap_does_not_fill_at_stop(self):
        result = simulate([100, 60, 64, 64, 40, 10], Config(fee_bps=0, slippage_bps=0))
        self.assertEqual(result['trades'][0]['exit_fill'], 10)
        self.assertEqual(result['trades'][0]['exit_reason'], 'STOP_LOSS')

    def test_low_before_peak_does_not_trigger_recovery(self):
        self.assertEqual(simulate([10, 100, 60], Config())['decisions'], [])

    def test_future_prices_do_not_change_past_decisions(self):
        prefix = [100, 60, 64, 70, 80]
        a = simulate(prefix + [200, 300], Config())
        b = simulate(prefix + [10, 5], Config())
        self.assertEqual([d for d in a['decisions'] if d['signal_bar'] < 5],
                         [d for d in b['decisions'] if d['signal_bar'] < 5])

    def test_equity_reconciles_and_marks_open_losses(self):
        result = simulate([100, 60, 64, 64, 50, 80], Config(stop_loss=.9))
        self.assertAlmostEqual(sum(t['net_pnl'] for t in result['trades']), result['summary']['net_pnl'])
        self.assertGreater(result['summary']['max_drawdown_pct'], 0)

    def test_bad_inputs_rejected(self):
        for prices in ([], [0], [-1], [float('nan')], [True]):
            with self.assertRaises(ValueError):
                simulate(prices, Config())
        with self.assertRaises(ValueError):
            simulate([100], Config(allocation=2))


if __name__ == '__main__':
    unittest.main()
