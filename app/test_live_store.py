import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from live_store import LiveStore,remove_legacy_cache
from discovery import Discovery
from market import Market,ZERO
from chain import Chain

A='So11111111111111111111111111111111111111112'
B='11111111111111111111111111111111'
def launch(mint=A,n=1,generation=0):return dict(type='event',kind='token',mint=mint,signature='launch'+str(n),event_index=0,slot=n,received=n,token_total_supply='1000000000',generation=generation)
def trade(mint=A,n=2,generation=0):return dict(type='event',kind='trade',mint=mint,signature='trade'+str(n),event_index=1,slot=n,received=n,timestamp=str(n),sol_amount='2000000000',token_amount='1000000',is_buy=True,real_sol_reserves='3000000000',real_token_reserves='2000000',quote_mint=ZERO,generation=generation)
class LiveTests(unittest.TestCase):
 def setUp(self):
  self.store=LiveStore();self.rpc=Mock();self.market=Market(self.store,self.rpc);self.d=Discovery(self.store,self.market)
 def tearDown(self):self.store.close()
 def count(self,t):return self.store.db.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]
 def test_clear_preserves_pins_and_rejects_old_events(self):
  self.d.ingest(launch());self.d.ingest(launch(B,2));self.d.ingest(trade());self.d.ingest(trade(B,3));self.d.pin({'mint':A,'pinned':True})
  result=self.d.clear();self.assertEqual(result['pins'],[A]);self.assertEqual(result['count'],1);self.assertEqual(self.count('market_trades'),1)
  self.d.ingest(trade(A,4));self.d.ingest(trade(B,5,1));self.d.ingest(launch(B,6))
  self.assertEqual(self.count('market_trades'),1);self.assertEqual(self.count('launch_events'),1)
  self.d.ingest(trade(A,7,1));self.assertEqual(self.count('market_trades'),2)
  self.d.pin({'mint':A,'pinned':False});self.d.clear();self.assertEqual(self.count('launch_events'),0);self.assertEqual(self.count('market_trades'),0)
 def test_pinned_token_survives_retention_and_duplicate_launches(self):
  self.d.ingest(launch());self.d.pin({'mint':A,'pinned':True})
  for n in range(2,215):self.d.ingest(launch('mint'+str(n),n))
  self.assertLessEqual(self.count('launch_events'),201);self.assertIn(A,[e['mint'] for e in self.d.status()['events']]);self.assertEqual(self.count('launch_supply'),self.count('launch_events'))
  for n in range(215,225):self.d.ingest(launch(A,n))
  self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM launch_events WHERE mint=?',(A,)).fetchone()[0],1)
 def test_enrichment_batches_verified_supply_and_decimals(self):
  e=launch();del e['token_total_supply'];self.d.ingest(e);self.d.ingest(trade())
  self.rpc.return_value={'value':[{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'type':'mint','info':{'supply':'1000000000','decimals':6}}}}]}
  self.market.enrich();m=self.market.metrics([A])[A];self.assertEqual(m['price_sol'],'2');self.assertEqual(m['fdv_sol'],'2000');self.assertEqual(self.count('feature_memory'),0)
 def test_real_name_and_verified_supply_reach_paper_context(self):
  fixture=json.loads(Path(__file__).with_name('fixtures').joinpath('token-2022-name.json').read_text());mint=fixture['mint']
  self.d.ingest(launch(mint));self.rpc.return_value={'value':[fixture['account']]};self.market.enrich()
  ctx=self.market.paper_snapshot(10)[mint]
  self.assertEqual(ctx['name'],'Super Accelerationism');self.assertEqual(ctx['symbol'],'s/acc')
  self.assertAlmostEqual(ctx['supply_tokens'],983689477.206370)
  self.assertNotEqual(ctx['supply_tokens'],1000)  # Current verified supply replaces launch fallback.
 def test_launch_burst_preserves_pool_and_prioritizes_metadata(self):
  self.d.ingest({**launch(A),'kind':'pool','base_mint':A,'pool':'pool','quote_mint':A})
  for n in range(2,302):self.d.ingest(launch('mint'+str(n),n))
  self.assertEqual(self.count('launch_events'),200)
  self.assertIsNotNone(self.store.db.execute('SELECT 1 FROM launch_events WHERE mint=?',(A,)).fetchone())
  self.rpc.return_value={'value':[None]*20};self.market.enrich()
  self.assertEqual(self.rpc.call_args.args[1][0][0],A)
 def test_migration_promotes_launch_without_overwriting_other_pool(self):
  self.d.ingest({**launch(A),'name':'Original name'})
  self.d.ingest(dict(type='event',kind='migration',mint=A,pool='migrated-pool',quote_mint=A,signature='migrate',event_index=2,slot=2,received=2))
  row=json.loads(self.store.db.execute('SELECT body FROM launch_events WHERE mint=?',(A,)).fetchone()[0])
  self.assertEqual(row['pool'],'migrated-pool');self.assertEqual(row['name'],'Original name');self.assertEqual(row['kind'],'pool')
  self.d.ingest(dict(type='event',kind='migration',mint=A,pool='different-pool',quote_mint=A,signature='other',event_index=2,slot=3,received=3))
  self.assertEqual(json.loads(self.store.db.execute('SELECT body FROM launch_events WHERE mint=?',(A,)).fetchone()[0])['pool'],'migrated-pool')
 def test_inflight_metadata_cannot_refill_after_clear(self):
  self.d.ingest(launch())
  def response(*args):
   self.d.clear();return {'value':[{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'type':'mint','info':{'supply':'1000','decimals':6}}}}]}
  self.rpc.side_effect=response;self.market.enrich();self.assertEqual(self.count('market_mints'),0)
 def test_inflight_chain_scan_cannot_refill_after_clear(self):
  chain=Chain(self.store,self.rpc);chain.watch({'address':A});watch=chain.status()['watches'][0]
  def response(*args):self.d.clear();return [{'signature':'old','slot':1,'blockTime':1}]
  self.rpc.side_effect=response;chain.scan(watch);self.assertEqual(self.count('chain_transactions'),0)
 def test_ram_only_and_restart_empty(self):
  self.assertEqual(self.store.db.execute('PRAGMA database_list').fetchone()[2],'');self.d.ingest(launch());other=LiveStore()
  try:self.assertFalse(other.exists('launch_events'))
  finally:other.close()
 def test_legacy_cleanup_preserves_wallet_records(self):
  with tempfile.TemporaryDirectory() as tmp:
   db=sqlite3.connect(str(Path(tmp)/'test.sqlite3'));db.executescript('CREATE TABLE launch_events(x);INSERT INTO launch_events VALUES (1);CREATE TABLE wallet_keys(secret);INSERT INTO wallet_keys VALUES (42);')
   remove_legacy_cache(SimpleNamespace(lock=threading.RLock(),db=db));self.assertEqual(db.execute('SELECT secret FROM wallet_keys').fetchone()[0],42);self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='launch_events'").fetchone());db.close()

 def test_trade_retention_has_hard_count_limit(self):
  self.d.ingest(launch());e=trade()
  with self.store.db:
   self.store.db.executemany('INSERT INTO market_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',[(str(n),1,A,n,n,n,'1','1',1,'1','1',json.dumps(e)) for n in range(12005)])
  self.store.prune();self.assertEqual(self.count('market_trades'),12000);self.assertEqual(self.store.db.execute('SELECT MIN(slot) FROM market_trades').fetchone()[0],5)
 def test_read_metadata_cannot_refill_after_clear(self):
  self.d.ingest(launch());self.d.ingest(trade())
  def response(*args):
   self.d.clear();return {'value':{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'type':'mint','info':{'decimals':6}}}}}
  self.rpc.side_effect=response
  with self.assertRaises(ValueError):self.market.read(A)
  self.assertEqual(self.count('market_mints'),0)

 def test_discard_rejects_late_events_and_preserves_pins(self):
  self.d.ingest(launch());self.d.ingest(trade());self.d.discard({'mint':A});self.d.ingest(launch(A,10));self.d.ingest(trade(A,11));self.assertEqual(self.count('launch_events'),0);self.assertEqual(self.count('market_trades'),0)
  self.d.ingest(launch(B,12));self.d.pin({'mint':B,'pinned':True})
  with self.assertRaises(ValueError):self.d.discard({'mint':B})
 def test_expiry_and_cache_measurement(self):
  self.d.ingest(launch());self.d.ingest(launch(B,2));self.d.pin({'mint':A,'pinned':True});self.d.maintain();self.assertEqual(self.count('launch_events'),1)
  usage=self.store.usage();self.assertEqual(usage['disk_bytes'],0);self.assertGreaterEqual(usage['allocated_bytes'],usage['used_bytes'])
 def test_memory_measurement_does_not_latch_and_cache_is_capped(self):
  self.assertEqual(self.store.usage()['max_bytes'],32*1048576)
  with patch('live_store.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=str(300*1024))):self.assertTrue(self.store.sample_memory())
  self.assertTrue(self.store.memory_pressure);self.store.last_memory_sample=0
  with patch('live_store.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=str(220*1024))):self.assertTrue(self.store.sample_memory())
  self.assertFalse(self.store.memory_pressure);self.store.last_memory_sample=0
  with patch('live_store.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=str(100*1024))):self.assertFalse(self.store.sample_memory())
  self.assertFalse(self.store.memory_pressure)
 def test_pressure_cleanup_preserves_pins_and_positions(self):
  self.d.ingest(launch());self.d.ingest(launch(B,2));self.store.protected={A}
  self.store.memory_pressure=True
  with patch.object(self.store,'sample_memory',return_value=True):self.d.maintain()
  self.assertEqual(self.count('launch_events'),1);self.assertIn(A,self.store.protected)
  self.d.ingest(launch(B,10,self.store.generation));self.assertEqual(self.count('launch_events'),2)
 def test_trade_pressure_reserves_position_history(self):
  self.d.ingest(launch());self.d.ingest(launch(B,2));self.store.protected={A};e=trade()
  with self.store.db:
   self.store.db.executemany('INSERT INTO market_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',[(str(n),1,A if n<120 else B,n,n,n,'1','1',1,'1','1',json.dumps(e)) for n in range(3000)])
  self.store.memory_pressure=True;self.store.prune();self.assertLessEqual(self.count('market_trades'),2000)
  self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM market_trades WHERE mint=?',(A,)).fetchone()[0],120)
 def test_open_position_does_not_switch_to_an_alternate_pool(self):
  self.d.ingest({**launch(A),'kind':'pool','pool':'held-pool','quote_mint':A})
  self.store.protected={A}
  self.d.ingest({**launch(A,2),'kind':'pool','pool':'alternate-pool','quote_mint':A})
  body=json.loads(self.store.db.execute('SELECT body FROM launch_events WHERE mint=?',(A,)).fetchone()[0]);self.assertEqual(body['pool'],'held-pool')
 def test_existing_canonical_pool_is_verified_without_invented_migration_time(self):
  self.d.ingest({**launch(A,100),'kind':'pool','pool':'canonical','quote_mint':A,'canonical_migration':True})
  ctx=self.market.paper_snapshot(120)[A]
  self.assertEqual(ctx['stage'],'verified_migrated');self.assertEqual(ctx['migration_received'],100)
  self.assertIn('not migration time',ctx['migration_basis'])
 def test_strategy_rejection_releases_data_but_preserves_positions(self):
  self.d.ingest(launch());self.d.ingest(launch(B,2));self.store.protected={A}
  self.d.reject([A,B]);self.assertEqual(self.count('launch_events'),1)
  self.d.ingest(launch(B,3));self.assertEqual(self.count('launch_events'),1)
  self.d.rejected[B]=0;self.d.ingest(launch(B,4));self.assertEqual(self.count('launch_events'),2)
 def test_old_telemetry_cannot_remove_current_generation(self):
  self.d.clear();self.d.ingest(launch(A,4,self.store.generation))
  self.d.ingest(dict(type='telemetry',generation=0,mints=[]));self.assertEqual(self.count('launch_events'),1)
