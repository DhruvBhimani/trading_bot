import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from engine import Bot,equity
from feeds import demo_batch

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.sqlite3';self.bot=Bot(self.path)
    def tearDown(self):self.bot.close();self.temp.cleanup()
    def run_demo(self):
        self.bot.action('start',{})
        for _ in range(360):self.bot.tick()

    def test_complete_accounting_and_fill_delay(self):
        self.run_demo();s=self.bot.snapshot()
        self.assertTrue(s['completed']);self.assertEqual(len(s['fills']),4)
        self.assertAlmostEqual(s['cash'],10000+s['realized_pnl'])
        self.assertFalse(s['positions']);self.assertTrue(all(f['symbol']!='DUST' for f in s['fills']))
        for f in s['fills']:
            row=self.bot.db.execute('SELECT created FROM orders WHERE id=?',(f['order_id'],)).fetchone()
            self.assertGreater(f['timestamp'],row['created'])
        self.assertGreater(sum(f['fee'] for f in s['fills']),0)

    def test_restart_and_saved_runs(self):
        self.bot.action('start',{})
        for _ in range(25):self.bot.tick()
        before=self.bot.snapshot();self.bot.close();self.bot=Bot(self.path);after=self.bot.snapshot()
        for key in ('cash','positions','pending','tick','fills'):self.assertEqual(before[key],after[key])
        self.assertFalse(after['running'])
        self.bot.action('new',{'name':'Second run'})
        self.bot.action('open',{'id':before['id']});self.assertEqual(self.bot.state['tick'],25)

    def test_duplicate_and_out_of_order_ignored(self):
        self.bot.apply(demo_batch(1));before=self.bot.snapshot()
        self.assertFalse(self.bot.apply(demo_batch(1)))
        self.assertFalse(self.bot.apply(demo_batch(0)))
        self.assertEqual(before,self.bot.snapshot())

    def test_missing_identity_and_invalid_values(self):
        self.bot.apply(demo_batch(1));rows=demo_batch(2);rows[0]['price']=float('nan')
        with self.assertRaises(ValueError):self.bot.apply(rows)
        self.assertEqual(self.bot.state['tick'],1)

    def test_fill_rechecks_minimum_liquidity(self):
        for i in range(1,19):self.bot.apply(demo_batch(i))
        self.assertIn('SCOUT',self.bot.state['pending'])
        rows=demo_batch(19);rows[0]['liquidity']=20000;self.bot.apply(rows)
        self.assertNotIn('SCOUT',self.bot.state['positions'])
        self.assertTrue(any(o['status']=='rejected' for o in self.bot.snapshot()['orders']))

    def test_expired_entry_cannot_fill(self):
        for i in range(1,19):self.bot.apply(demo_batch(i))
        rows=demo_batch(19)
        for row in rows:row['timestamp']+=100
        self.bot.apply(rows)
        self.assertFalse(self.bot.state['positions'])
        self.assertTrue(any(o['status']=='expired' for o in self.bot.snapshot()['orders']))

    def test_no_liquidity_or_stale_mark_is_zero(self):
        for i in range(1,20):self.bot.apply(demo_batch(i))
        s=self.bot.state;self.assertIn('SCOUT',s['positions'])
        rows=demo_batch(20);rows[0]['liquidity']=0;self.bot.apply(rows)
        self.assertIn('SCOUT',s['positions'])
        self.assertEqual(equity(s,s['timestamp']+1000),s['cash'])

    def test_atomic_failure_rolls_back_fill_and_state(self):
        for i in range(1,19):self.bot.apply(demo_batch(i))
        before=copy.deepcopy(self.bot.state)
        self.bot.db.execute("CREATE TRIGGER deny_fill BEFORE INSERT ON fills BEGIN SELECT RAISE(ABORT,'test failure'); END;")
        with self.assertRaises(sqlite3.IntegrityError):self.bot.apply(demo_batch(19))
        self.assertEqual(before,self.bot.state)
        self.assertEqual(self.bot.db.execute('SELECT count(*) FROM fills').fetchone()[0],0)

    def test_replay_matches_original_and_is_pinned(self):
        self.run_demo();first=self.bot.snapshot();self.bot.action('new',{'mode':'replay','name':'Replay','dataset_id':first['dataset_id']})
        self.bot.action('start',{})
        for _ in range(361):self.bot.tick()
        again=self.bot.snapshot()
        self.assertEqual(first['cash'],again['cash']);self.assertEqual(first['realized_pnl'],again['realized_pnl'])
        self.assertEqual([(f['side'],f['price'],f['quantity']) for f in first['fills']],[(f['side'],f['price'],f['quantity']) for f in again['fills']])
        self.assertEqual(self.bot.db.execute('SELECT count(*) FROM observations').fetchone()[0],1080)

    def test_import_export_backup_and_invalid_import(self):
        for i in range(1,5):self.bot.apply(demo_batch(i))
        body=self.bot.export(self.bot.state['id']);new=self.bot.import_data(body)
        self.assertEqual(new['observations'],12)
        bad=copy.deepcopy(body);bad['observations'].append(bad['observations'][0])
        with self.assertRaises(ValueError):self.bot.import_data(bad)
        with sqlite3.connect(self.bot.backup()) as db:self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')

    def test_no_snapshot_live_mode_and_immutable_settings(self):
        with self.assertRaises(ValueError):self.bot.action('new',{'mode':'live'})
        with self.assertRaises(ValueError):self.bot.action('settings',{'size':200})
        self.assertFalse(self.bot.snapshot()['live_execution_enabled'])

if __name__=='__main__':unittest.main()
