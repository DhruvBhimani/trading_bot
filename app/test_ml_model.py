import importlib.util
import json
import math
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from ml_model import FEATURES, POLICY, predict, split_rows, validate, vector
from ml_research import ModelResearch

def fixture(count=300):
    return [dict(id=i+1,mint='coin'+str(i),entry_time=i*10,exit_time=i*10+2,
                 features=dict(age_seconds=60,trade_count=20,volume_sol=2,buy_fraction=.8,
                               pool_sol=50,momentum=.2 if i%2 else .02,fdv_sol=1000,stage='verified_migrated'),
                 **{'return':.2 if i%2 else -.18}) for i in range(count)]

class ModelTests(unittest.TestCase):
    def test_features_cannot_include_future_outcome_and_missing_is_not_zero(self):
        a=fixture(1)[0]['features'];b={**a,'pnl_sol':1000,'exit_price':99999}
        self.assertEqual(vector(a),vector(b));self.assertIsNone(vector({})[0])
        self.assertIsNone(vector(dict(age_seconds=float('inf')))[0])
        self.assertIsNone(vector(dict(age_seconds=-1))[0])
    def test_split_purges_overlapping_outcomes_and_shared_coins(self):
        rows=fixture(300);rows[0]['exit_time']=999999;rows[230]['mint']=rows[1]['mint']
        train,test=split_rows(rows)
        self.assertNotIn(1,[r['id'] for r in train]);self.assertNotIn(231,[r['id'] for r in test])
        self.assertLess(max(r['exit_time'] for r in train),min(r['entry_time'] for r in test))
        self.assertFalse({r['mint'] for r in train}&{r['mint'] for r in test})
        for r in rows:r['validation_eligible']=r['id']>260
        _,fresh=split_rows(rows)
        self.assertEqual(len(fresh),40);self.assertTrue(all(r['id']>260 for r in fresh))
    def test_portable_prediction_missing_direction_and_budget_validation(self):
        m=dict(policy=POLICY,features=list(FEATURES),base=0,trees=[[1,10,True,[.1],[-.2]]])
        validate(m);self.assertEqual(predict(m,{}),.1);self.assertEqual(predict(m,dict(trade_count=20)),-.2)
        m['trees']*=65
        with self.assertRaises(ValueError):validate(m)

@unittest.skipUnless(importlib.util.find_spec('xgboost'),'Run with research/.venv-ml/bin/python for native training tests')
class NativeTrainingTests(unittest.TestCase):
    def test_learns_signal_and_exports_matching_portable_predictions(self):
        from train_paper_model import train
        result=train(fixture())
        self.assertEqual(result['status'],'paper_candidate');self.assertLess(result['report']['inference_max_error'],1e-6)
        self.assertGreater(result['report']['stressed_mean_return'],0)
        model=json.loads(json.dumps(result['model']))
        self.assertGreater(predict(model,fixture(2)[1]['features']),predict(model,fixture(1)[0]['features']))
    def test_does_not_accept_holdout_losses_or_same_coin_leakage(self):
        from train_paper_model import train
        rows=fixture()
        for r in rows[210:]:r['return']=-.2
        self.assertEqual(train(rows)['status'],'validation_rejected')
        for r in rows:r['mint']='same-coin'
        self.assertEqual(train(rows)['status'],'insufficient_split')

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE trades(id INTEGER PRIMARY KEY,strategy TEXT,body TEXT)')
        self.models=ModelResearch(self.db)
    def tearDown(self):self.models.close();self.db.close()
    def test_minimum_data_does_not_spawn_and_restart_marks_interrupted_job(self):
        self.models.schedule(100,'v');self.assertIsNone(self.models.job)
        self.db.execute("INSERT INTO ml_attempts VALUES ('momentum',0,1,'training','{}')")
        ModelResearch(self.db)
        self.assertEqual(self.models.status('v')['progress'][0]['status'],'interrupted')
    def test_training_data_is_bounded_and_baseline_only(self):
        for i,r in enumerate(fixture(520)):
            t=dict(mint=r['mint'],version='v',execution_policy='signal-ceiling-v1-10pct',entry_features=r['features'],signal_features=r['features'],entry_time=r['entry_time'],exit_time=r['exit_time'],cost_sol=.1,pnl_sol=r['return']*.1)
            self.db.execute('INSERT INTO trades VALUES (?,?,?)',(i+1,'momentum',json.dumps(t)))
        self.assertEqual(len(self.models.dataset('momentum','v')),500)
        self.assertEqual(self.models.dataset('momentum','different-version'),[])
    def test_watchdog_kills_oversized_trainer_and_preserves_research(self):
        self.db.execute("INSERT INTO ml_attempts VALUES ('momentum',0,300,'training','{}')")
        temp=tempfile.TemporaryDirectory();location=Path(temp.name)
        process=Mock();process.poll.return_value=None;process.pid=123;process.returncode=-9
        self.models.job=dict(process=process,temp=temp,started=time.monotonic(),strategy='momentum',version='v',cutoff=300,validation_after=0)
        with patch('ml_research.subprocess.check_output',return_value=b'600000'):
            self.models.poll(100)
        process.kill.assert_called_once();self.assertIsNone(self.models.job);self.assertFalse(location.exists())
        self.assertEqual(self.models.status('v')['progress'][0]['status'],'trainer_memory_limit')
    def test_subprocess_training_save_reload_and_no_duplicate_fit(self):
        if not Path('research/.venv-ml/bin/python').exists():self.skipTest('ML runtime not installed')
        for r in fixture():
            t=dict(mint=r['mint'],version='v',execution_policy='signal-ceiling-v1-10pct',entry_features=r['features'],signal_features=r['features'],entry_time=r['entry_time'],exit_time=r['exit_time'],cost_sol=.1,pnl_sol=r['return']*.1)
            self.db.execute('INSERT INTO trades VALUES (?,?,?)',(r['id'],'momentum',json.dumps(t)))
        self.models.schedule(5000,'v');self.assertIsNotNone(self.models.job)
        self.models.job['process'].wait(timeout=30);self.models.poll(5010)
        self.assertIsNone(self.models.job)
        c=self.models.candidate('v',set());self.assertIsNotNone(c)
        self.assertIsNone(self.models.candidate('different-version',set()))
        self.assertIsNone(self.models.candidate('v',{c['id']}))
        self.models.schedule(9000,'v');self.assertIsNone(self.models.job)
        restarted=ModelResearch(self.db);self.assertEqual(restarted.candidate('v',set())['id'],c['id'])
