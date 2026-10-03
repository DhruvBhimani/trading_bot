import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ingestion'))
from market_database import connect,record_fetch,ingest_pools,ingest_candles,status,export_prices,coverage
from import_gecko import normalize
from collect_market import queue_jobs,collect

POOL='58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2'
TIME='2026-01-01T01:00:00+00:00'
START=1767225600


def pools():
    return {'data':[{'attributes':{'address':POOL,'name':'TEST / SOL','reserve_in_usd':'10000','base_token_price_usd':'2'},
                     'relationships':{'base_token':{'data':{'id':'solana_TEST'}},'quote_token':{'data':{'id':'solana_SOL'}}}}]}


def candles(close=2):
    return json.dumps({'data':{'attributes':{'ohlcv_list':[[START,2,4,1,close,10]]}},'meta':{'base':{'address':'TEST'}}}).encode()


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.temp.name)/'data.sqlite3')
        self.fetch=record_fetch(self.db,'https://example.test',TIME,json.dumps(pools()).encode())
        ingest_pools(self.db,pools(),self.fetch,TIME)

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def test_repeated_discovery_does_not_double_count_tokens(self):
        ingest_pools(self.db,pools(),self.fetch,TIME)
        result=status(self.db)
        self.assertEqual(result['discovered_base_tokens'],1)
        self.assertEqual(result['discovered_pools'],1)
        self.assertEqual(result['liquidity_snapshots'],1)

    def test_revisions_preserve_raw_and_export_latest(self):
        for close in [2,3]:
            raw=candles(close)
            fid=record_fetch(self.db,'https://example.test/candles',TIME,raw)
            ingest_candles(self.db,normalize(raw,POOL,'minute',15,TIME),fid)
        self.assertEqual(status(self.db)['unique_candles'],1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM candle_versions').fetchone()[0],2)
        exported=export_prices(self.db,POOL,900)
        self.assertEqual(exported['bars'][0]['close_usd'],3)
        self.assertIsNone(exported['bars'][0]['liquidity_usd'])
        self.assertFalse(exported['quality']['execution_backtest_ready'])

    def test_persistence_and_coverage_after_reopen(self):
        path=Path(self.temp.name)/'data.sqlite3'
        self.db.close()
        self.db=connect(path)
        self.assertEqual(status(self.db)['discovered_base_tokens'],1)
        self.assertEqual(coverage(self.db)[0]['candles'],0)
        self.assertIsNone(coverage(self.db)[0]['first_candle'])

    def test_queue_resume_is_idempotent(self):
        queue_jobs(self.db,1000,7,START+3600)
        queue_jobs(self.db,1000,7,START+3600)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],1)

    def test_token_mismatch_rejected(self):
        normalized=normalize(candles(),POOL,'minute',15,TIME)
        normalized['token']='OTHER'
        with self.assertRaises(ValueError):ingest_candles(self.db,normalized,self.fetch)

    def test_page_and_checkpoint_roll_back_together(self):
        with self.assertRaises(RuntimeError):
            with self.db:
                ingest_candles(self.db,normalize(candles(),POOL,'minute',15,TIME),self.fetch,commit=False)
                raise RuntimeError('simulated failure')
        self.assertEqual(status(self.db)['unique_candles'],0)

    def test_resumable_pagination(self):
        start,end=queue_jobs(self.db,1,1,START+3600)
        owner=self
        class Client:
            calls=0
            def get(self,url):
                self.calls+=1
                raw=candles() if self.calls==1 else b'{"data":{"attributes":{"ohlcv_list":[]}},"meta":{"base":{"address":"TEST"}}}'
                fid=record_fetch(owner.db,url,TIME,raw)
                return json.loads(raw),raw,TIME,fid
        client=Client()
        collect(self.db,client,start,end)
        self.assertEqual(client.calls,2)
        self.assertEqual(status(self.db)['jobs'],{'source_exhausted':1})
        collect(self.db,client,start,end)
        self.assertEqual(client.calls,2)


if __name__=='__main__':unittest.main()
