import copy
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'backtests'))
from portfolio_simulator import Config, simulate


def dataset(tokens=None):
    rows=[]
    for token, prices in (tokens or {'A':[100,60,64,65,100,110]}).items():
        for i, price in enumerate(prices):
            t=(datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(minutes=i)).isoformat()
            rows.append(dict(token=token,observed_at=t,available_at=t,price_usd=price,liquidity_usd=100000,tradable=True))
    return dict(schema_version=1,synthetic=True,observations=rows)


class PortfolioTests(unittest.TestCase):
    def test_shared_cash_and_deterministic_order(self):
        data=dataset({'B':[100,60,64,65], 'A':[100,60,64,65]})
        cfg=Config(starting_cash=300,position_budget=200)
        result=simulate(data,cfg)
        self.assertEqual(result['summary']['ending_cash'],100)
        self.assertEqual(list(result['open_positions']),['A'])
        self.assertTrue(any(r['reason']=='INSUFFICIENT_CASH' for r in result['rejections']))
        data['observations'].reverse()
        self.assertEqual(result,simulate(data,cfg))

    def test_position_cap(self):
        result=simulate(dataset({'A':[100,60,64,65],'B':[100,60,64,65]}),Config(max_positions=1))
        self.assertEqual(len(result['open_positions']),1)
        self.assertTrue(any(r['reason']=='POSITION_LIMIT' for r in result['rejections']))

    def test_delayed_signal_cannot_fill_in_its_past(self):
        data=dataset({'A':[100,60,64,65,66]})
        data['observations'][2]['available_at']=data['observations'][3]['available_at']
        result=simulate(data,Config())
        self.assertEqual(result['ledger'][0]['time'],data['observations'][4]['available_at'])

    def test_stale_data_cannot_create_signal(self):
        data=dataset({'A':[100,60,64]})
        data['observations'][-1]['available_at']='2026-01-01T00:10:00+00:00'
        self.assertEqual(simulate(data,Config())['decisions'],[])

    def test_missing_token_marked_zero_without_forced_sale(self):
        result=simulate(dataset({'A':[100,60,64,65],'B':[100]*8}),Config())
        self.assertEqual(result['open_positions']['A']['conservative_value'],0)
        self.assertEqual(result['summary']['ending_cash'],9800)
        self.assertEqual(result['summary']['closed_trades'],0)

    def test_untradeable_token_no_fictional_exit(self):
        data=dataset({'A':[100,60,64,65,40,0]})
        data['observations'][-1].update(tradable=False,liquidity_usd=0)
        result=simulate(data,Config())
        self.assertEqual(result['summary']['closed_trades'],0)
        self.assertEqual(result['open_positions']['A']['conservative_value'],0)
        self.assertIn('A',result['pending_orders'])

    def test_liquidity_blocks_purchase(self):
        data=dataset({'A':[100,60,64,65]})
        data['observations'][-1]['liquidity_usd']=10000
        result=simulate(data,Config())
        self.assertEqual(result['ledger'],[])
        self.assertTrue(any(r['reason']=='LIQUIDITY_LIMIT' for r in result['rejections']))

    def test_gap_execution_and_cash_reconciliation(self):
        result=simulate(dataset({'A':[100,60,64,65,40,10]}),Config(fee_bps=0,slippage_bps=0))
        self.assertEqual(result['ledger'][-1]['fill'],10)
        self.assertAlmostEqual(10000+sum(r['cash_delta'] for r in result['ledger']),result['summary']['ending_cash'])
        self.assertAlmostEqual(result['summary']['realized_pnl'],result['summary']['ending_cash']-10000)

    def test_future_changes_do_not_change_past(self):
        a=dataset(); b=copy.deepcopy(a)
        b['observations'][-1]['price_usd']=1
        ra,rb=simulate(a,Config()),simulate(b,Config())
        self.assertEqual(ra['equity_curve'][:-1],rb['equity_curve'][:-1])
        self.assertEqual(ra['decisions'][:-1],rb['decisions'][:-1])

    def test_expired_order_not_filled(self):
        result=simulate(dataset({'A':[100,60,64,65]}),Config(order_ttl_seconds=30))
        self.assertEqual(result['ledger'],[])
        self.assertTrue(any(r['reason']=='ORDER_EXPIRED' for r in result['rejections']))

    def test_invalid_data(self):
        for field,value in [('price_usd',float('nan')),('liquidity_usd',-1),('tradable',1),('observed_at','2026-01-01')]:
            data=dataset();data['observations'][0][field]=value
            with self.assertRaises(ValueError):simulate(data,Config())
        data=dataset(); data['observations'].append(data['observations'][0])
        with self.assertRaises(ValueError):simulate(data,Config())


if __name__=='__main__':unittest.main()
