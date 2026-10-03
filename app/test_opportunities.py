import json,sqlite3,unittest
from opportunities import Opportunities,LABEL_POLICY
from ml_research import ModelResearch

class OpportunityTests(unittest.TestCase):
 def setUp(self):
  self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;self.o=Opportunities(self.db)
  self.ctx={'coin':dict(pool='p',name='Skipped coin',stage='verified_migrated',samples=[])}
  self.f=dict(price=1.,age_seconds=60,trade_count=10,volume_sol=1,buy_fraction=.7,pool_sol=100,momentum=.1,fdv_sol=1000,stage='verified_migrated')
 def tearDown(self):self.db.close()
 def event(self,t,price):self.ctx['coin']['samples'].append(dict(received=t,slot=int(t),event_index=0,price=price))
 def tick(self,t,healthy=True):self.o.tick(self.ctx,t,'v',lambda ctx,now:self.f,lambda e:.04,healthy)
 def rows(self):return self.db.execute('SELECT * FROM opportunities ORDER BY id').fetchall()
 def test_skipped_coin_gets_target_label_and_can_train_without_any_trade(self):
  self.event(0,1);self.tick(0);self.event(2,1.3);self.tick(2)
  self.assertEqual(self.rows()[0]['status'],'target_first')
  model=ModelResearch(self.db);rows=model.dataset('opportunity','v');self.assertEqual(len(rows),1)
  self.assertAlmostEqual(rows[0]['return'],.26);self.assertEqual(rows[0]['label'],1)
 def test_first_barrier_wins_in_observed_order(self):
  self.event(0,1);self.tick(0);self.event(1,.8);self.event(2,1.4);self.tick(2)
  self.assertEqual(self.rows()[0]['status'],'stop_first')
 def test_gap_does_not_fabricate_rug_or_profit_label(self):
  self.event(0,1);self.tick(0);self.event(20,2);self.tick(20)
  self.assertEqual(self.rows()[0]['status'],'censored_gap')
  self.assertEqual(ModelResearch(self.db).dataset('opportunity','v'),[])
 def test_already_known_late_block_event_cannot_be_a_future_target(self):
  self.event(9.5,1.5);self.event(9,1);self.tick(10)
  self.event(11,1.01);self.tick(11)
  self.assertEqual(self.rows()[0]['status'],'pending')
 def test_gap_after_deadline_does_not_change_covered_timeout(self):
  self.event(0,1);self.tick(0)
  for t in range(5,60,5):self.event(t,1.05);self.tick(t)
  self.event(75,2);self.tick(75)
  self.assertEqual(self.rows()[0]['status'],'timeout')
 def test_covered_timeout_is_non_target_not_a_trade_exit(self):
  self.event(0,1);self.tick(0)
  for t in range(5,61,5):self.event(t,1.05);self.tick(t)
  first=self.rows()[0];self.assertEqual(first['status'],'timeout');b=json.loads(first['body']);self.assertEqual(b['label'],0)
  self.assertEqual(len(self.rows()),3)
  self.event(90,1);self.tick(90);self.assertEqual(len(self.rows()),3)
 def test_restart_and_eviction_censor_pending_records(self):
  self.event(0,1);self.tick(0);Opportunities(self.db)
  self.assertEqual(self.rows()[0]['status'],'censored_restart')
  self.event(30,1);self.tick(30);self.ctx={};self.tick(31)
  self.assertEqual(self.rows()[1]['status'],'censored_evicted')
 def test_every_seen_creation_is_logged_even_without_pool_data_and_bounded(self):
  self.o.seen([dict(mint='m'+str(i),received=i,kind='token') for i in range(10005)])
  self.o.prune();self.assertEqual(self.o.status()['retained_tokens'],10000);self.assertEqual(self.o.status()['frames'],0)
