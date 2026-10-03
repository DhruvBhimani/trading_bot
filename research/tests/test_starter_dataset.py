import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from io import BytesIO

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ingestion'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backtests'))
from market_database import connect,record_fetch,ingest_pools
from starter_dataset import fetch_window,save_run,load_run,stored_bars,collect_starter
from starter_backtest import replay,Config
from import_gecko import iso

POOL='58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2'
START=1767225600


class StarterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=connect(Path(self.temp.name)/'test.sqlite3')
        self.case=dict(symbol='TEST',token='TEST',pool=POOL,group='runner')
        payload={'data':[{'attributes':{'address':POOL},'relationships':{
            'base_token':{'data':{'id':'solana_TEST'}},'quote_token':{'data':{'id':'solana_SOL'}}}}]}
        fid=record_fetch(self.db,'test',iso(START),json.dumps(payload).encode())
        ingest_pools(self.db,payload,fid,iso(START))

    def tearDown(self):
        self.db.close();self.temp.cleanup()

    def window(self,prices=(100,60,65,70,80),token='TEST',skip=None):
        raw=json.dumps({'meta':{'base':{'address':token}},'data':{'attributes':{
            'ohlcv_list':[[START+i*3600,p,p,p,p,10] for i,p in enumerate(prices) if i!=skip]}}}).encode()
        fid=record_fetch(self.db,'test',iso(START+86400),raw)
        class Client:
            def get(self,url):return json.loads(raw),raw,iso(START+86400),fid
        return fetch_window(self.db,Client(),self.case,START,START+len(prices)*3600)

    def dataset(self,spec):
        return save_run(self.db,'starter_dataset_v1',{'cases':[{**self.case,'event':spec,'recent':spec}]})

    def test_http_limit_is_archived_and_not_zero_return(self):
        class Client:
            def get(self,url):raise HTTPError(url,401,'limit',{},BytesIO(b'{"errors":["180 days"]}'))
        spec=fetch_window(self.db,Client(),self.case,START,START+3600)
        self.assertEqual(spec['status'],'provider_unavailable')
        report=replay(self.db,self.dataset(spec),'event',Config())
        self.assertNotIn('result',report['cases'][0])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM raw_responses').fetchone()[0],2)

    def test_wrong_token_rejected(self):
        with self.assertRaises(ValueError):self.window(token='WRONG')

    def test_missing_bar_skips_window(self):
        spec=self.window(skip=2)
        self.assertEqual(spec['missing_intervals'],1)
        self.assertEqual(replay(self.db,self.dataset(spec),'recent',Config())['cases'][0]['status'],
                         'skipped_incomplete_window')

    def test_replay_pinned_to_original_fetch_and_persists(self):
        spec=self.window()
        identifier=self.dataset(spec)
        before=replay(self.db,identifier,'recent',Config())
        self.window(prices=(1,2,3,4,5))
        after=replay(self.db,identifier,'recent',Config())
        self.assertEqual(before,after)
        report_id=save_run(self.db,'starter_backtest_v1',after)
        self.assertEqual(load_run(self.db,report_id,'starter_backtest_v1'),after)
        self.assertGreater(after['cases'][0]['result']['summary']['trades'],0)

    def test_outcome_label_never_changes_trades(self):
        spec=self.window()
        before=replay(self.db,self.dataset(spec),'recent',Config())
        self.case['group']='rug'
        after=replay(self.db,self.dataset(spec),'recent',Config())
        self.assertEqual(before['cases'][0]['result'],after['cases'][0]['result'])

    def test_missing_snapshot_rows_fail(self):
        spec=self.window()
        self.db.execute('DELETE FROM candle_versions')
        with self.assertRaises(ValueError):stored_bars(self.db,{**self.case,'recent':spec},'recent')

    def test_wrong_run_type_rejected(self):
        identifier=save_run(self.db,'starter_backtest_v1',{})
        with self.assertRaises(ValueError):load_run(self.db,identifier,'starter_dataset_v1')

    def test_completed_resume_does_not_refetch_or_change_cutoff(self):
        cases=[{**self.case,'token':str(i)} for i in range(5)]
        manifest={'name':'test','selection':'test only','cases':cases}
        body={'name':'test','manifest':manifest,'recent_end':START,'recent_days':7,
              'cases':[{**c,'event':{'status':'provider_unavailable'}} for c in cases]}
        identifier=save_run(self.db,'starter_dataset_v1',body)
        class Client:
            def get(self,url):raise AssertionError('Unexpected refetch')
        result=collect_starter(self.db,Client(),manifest,START+86400,resume_id=identifier)
        self.assertEqual(result,identifier)
        self.assertEqual(load_run(self.db,result,'starter_dataset_v1')['recent_end'],START)


if __name__=='__main__':unittest.main()
