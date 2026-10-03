import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ingestion'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backtests'))
from import_gecko import normalize, request_url
from portfolio_simulator import validate_dataset
POOL='58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2'


def raw(candles):
    return json.dumps({'data':{'attributes':{'ohlcv_list':candles}},'meta':{'base':{'address':'TEST_TOKEN'}}}).encode()


class ImportTests(unittest.TestCase):
    def normalize(self, candles):
        return normalize(raw(candles),POOL,'minute',1,'2026-01-01T00:10:30Z')

    def test_sort_gaps_and_no_fabricated_liquidity(self):
        result=self.normalize([[1767225720,2,3,1,2,10],[1767225600,2,3,1,2,10]])
        self.assertEqual(result['quality']['gaps'][0]['missing_intervals'],1)
        self.assertEqual(result['bars'][0]['interval_end'],'2026-01-01T00:01:00+00:00')
        self.assertIsNone(result['bars'][0]['liquidity_usd'])
        self.assertIsNone(result['bars'][0]['historical_available_at'])
        self.assertFalse(result['quality']['execution_backtest_ready'])
        with self.assertRaises(ValueError):validate_dataset(result)

    def test_unfinished_candles_removed(self):
        result=self.normalize([[1767226200,2,3,1,2,10]])
        self.assertEqual(result['bars'],[])
        self.assertEqual(result['quality']['incomplete_candles_excluded'],1)

    def test_invalid_candles(self):
        for candle in ([1767225600,2,1,3,2,10],[1767225600,2,3,1,2,-1],
                       [1767225600,2,3,1,float('nan'),10], [1,2]):
            with self.assertRaises(ValueError):self.normalize([candle])
        candle=[1767225600,2,3,1,2,10]
        with self.assertRaises(ValueError):self.normalize([candle,candle])

    def test_url_validation_and_explicit_usd_base(self):
        url=request_url(POOL,'minute',15)
        self.assertIn('currency=usd',url)
        self.assertIn('token=base',url)
        with self.assertRaises(ValueError):request_url('../foo','minute',15)
        with self.assertRaises(ValueError):request_url(POOL,'hour',15)


if __name__=='__main__':unittest.main()
