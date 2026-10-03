import importlib.util,json,sqlite3,unittest
from pathlib import Path
from ml_model import predict,probability,validate,PROB_POLICY
from opportunities import Opportunities,LABEL_POLICY
from ml_research import ModelResearch
from train_opportunity_model import split

def examples(n=300):
 return [dict(id=i+1,mint='coin'+str(i),entry_time=i*10,exit_time=i*10+2,dataset='opportunity',label=i%2,
              features=dict(age_seconds=60,trade_count=20,volume_sol=2,buy_fraction=.8,pool_sol=50,momentum=.2 if i%2 else .02,fdv_sol=1000,stage='verified_migrated',cost_fraction=.04),
              **{'return':.21 if i%2 else -.16}) for i in range(n)]

class SplitTests(unittest.TestCase):
 def test_three_periods_have_no_overlapping_outcomes_or_coins(self):
  rows=examples();rows[0]['exit_time']=9999;rows[190]['mint']=rows[1]['mint'];rows[250]['mint']=rows[200]['mint']
  train,cal,test=split(rows)
  self.assertNotIn(1,[r['id'] for r in train]);self.assertNotIn(191,[r['id'] for r in cal]);self.assertNotIn(251,[r['id'] for r in test])
  self.assertLess(max(r['exit_time'] for r in train),min(r['entry_time'] for r in cal))
  self.assertLess(max(r['exit_time'] for r in cal),min(r['entry_time'] for r in test))
  for r in rows:r['validation_eligible']=r['id']>270
  self.assertTrue(all(r['id']>270 for r in split(rows)[2]))
 def test_actual_training_job_uses_skipped_opportunities_and_persists_model(self):
  if not Path('research/.venv-ml/bin/python').exists():self.skipTest('No native runtime')
  db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;Opportunities(db);m=ModelResearch(db)
  try:
   for r in examples():
    b=dict(features=r['features'],label=r['label'],ended=r['exit_time'],observed_return=r['return']+.04,cost_fraction=.04,policy=LABEL_POLICY)
    db.execute('INSERT INTO opportunities(mint,created,version,status,body) VALUES (?,?,?,?,?)',(r['mint'],r['entry_time'],'v','target_first' if r['label'] else 'stop_first',json.dumps(b)))
   m.schedule(5000,'v');self.assertIsNotNone(m.job);m.job['process'].wait(timeout=30);m.poll(5010)
   candidate=m.candidate('v',set());self.assertIsNotNone(candidate);self.assertEqual(candidate['strategy'],'momentum');self.assertEqual(candidate['model']['policy'],PROB_POLICY)
   self.assertEqual(m.status('v')['unit'],'observed outcomes')
   m.schedule(10000,'v');self.assertIsNone(m.job)
  finally:m.close();db.close()

@unittest.skipUnless(importlib.util.find_spec('xgboost'),'Use ML environment for native tests')
class ClassifierTests(unittest.TestCase):
 def test_calibration_parity_and_repeated_holdout_gate(self):
  from train_opportunity_model import train
  result=train(examples());self.assertEqual(result['status'],'paper_candidate');m=result['model'];validate(m)
  self.assertLess(result['report']['brier'],result['report']['baseline_brier'])
  self.assertLess(result['report']['inference_max_error'],1e-6)
  self.assertTrue(all(x>.01 for x in result['report']['period_means']))
  hi=examples(2)[1]['features'];lo=examples(1)[0]['features']
  self.assertGreater(probability(m,hi),probability(m,lo));self.assertGreater(predict(m,hi),.02)
  self.assertEqual(predict(m,{}),-1)
  self.assertAlmostEqual(predict(m,{**hi,'cost_fraction':.14}),predict(m,hi)-.1)
 def test_later_regime_failure_cannot_be_promoted(self):
  from train_opportunity_model import train
  rows=examples()
  for r in rows[240:]:r['label']=1-r['label'];r['return']=.21 if r['label'] else -.16
  self.assertEqual(train(rows)['status'],'validation_rejected')
