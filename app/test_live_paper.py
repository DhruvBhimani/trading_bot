import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from live_store import LiveStore
from market import Market,SOL
from discovery import Discovery
from live_paper import LivePaper

MINT='So11111111111111111111111111111111111111112'
AMM='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
class LivePaperTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.now=1000.;self.live=LiveStore();self.market=Market(self.live,Mock());self.d=Discovery(self.live,self.market)
  self.ctx=dict(mint=MINT,name='Test coin',pool='pool',quote_mint=SOL,decimals=6,age=60,stage='migration_unknown',risk=dict(authority_known=True,mint_authority=None,freeze_authority=None,observed=1000),samples=[])
  self.sample(999,.01);self.sample(1000,.011)
  self.contexts={MINT:self.ctx};self.market.paper_snapshot=Mock(side_effect=lambda *a:self.contexts)
  self.d.ingest(dict(type='event',kind='pool',base_mint=MINT,pool='pool',quote_mint=SOL,base_mint_decimals=6,signature='launch',event_index=0,slot=1,received=940))
  self.path=Path(self.tmp.name)/'paper.sqlite3';self.cfg=dict(size_usd=0,min_age_seconds=0,min_window_trades=2,min_window_volume_sol=.01,momentum=.02,max_hold_seconds=20)
  self.paper=LivePaper(self.path,self.d,self.cfg,clock=lambda:self.now);self.paper.control('start')
 def tearDown(self):self.paper.close();self.live.close();self.tmp.cleanup()
 def sample(self,t,price=.011,**extra):
  self.ctx['samples'].append(dict(signature='sig'+str(t),event_index=1,slot=int(t),received=t,timestamp=int(t),price=price,volume_sol=.2,buy=True,pool_sol=100.,pool_tokens=100./price,fee_fraction=.003,**extra))
 def tick(self,t):self.now=t;self.paper.tick(t)
 def account(self,key='momentum'):return self.paper.s['accounts'][key]
 def open_position(self):
  self.tick(1000);self.sample(1002);self.tick(1002);self.assertIn(MINT,self.account()['positions'])
 def test_delay_requires_subsequent_trade(self):
  self.tick(1000);self.assertIn(MINT,self.account()['pending']);self.assertEqual(self.account()['cash'],10)
  self.tick(1001);self.assertEqual(self.account()['positions'],{})
  self.sample(1002);self.tick(1002);self.assertLess(self.account()['cash'],9.9);self.assertIn(MINT,self.live.protected)
 def test_usd_size_is_frozen_at_queue_and_missing_reference_blocks_only_entries(self):
  self.paper.s['config']['size_usd']=50;self.paper.usd=Mock();self.paper.usd.rate.return_value=None
  self.tick(1000);self.assertFalse(self.account()['pending'])
  self.paper.usd.rate.return_value=100;self.sample(1001);self.tick(1001)
  self.assertEqual(self.account()['pending'][MINT]['amount'],.5)
  self.paper.usd.rate.return_value=99;self.sample(1003);self.tick(1003)
  p=self.account()['positions'][MINT];self.assertEqual(p['allocation_sol'],.5);self.assertEqual(p['allocation_usd'],50)
  self.paper.usd.rate.return_value=None;self.paper.request_exit(dict(strategy='momentum',mint=MINT));self.sample(1005);self.tick(1005)
  self.assertFalse(self.account()['positions'])
 def test_disabled_time_limit_does_not_force_exit(self):
  self.paper.s['config']['max_hold_seconds']=0;self.open_position()
  p=self.account()['positions'][MINT]
  self.assertIsNone(self.paper.exit_reason(p,None,999999))
  self.assertIsNone(self.paper.position_view(MINT,p,self.account(),self.ctx,self.now)['exit_plan']['remaining_seconds'])
 def test_manual_writeoff_is_not_sale_or_cash_refund_and_releases_slot(self):
  self.open_position();cash=self.account()['cash'];cost=self.account()['positions'][MINT]['cost']
  self.now=1015;status=self.paper.request_exit(dict(strategy='momentum',mint=MINT,write_off=True))
  self.assertEqual(self.account()['cash'],cash);self.assertFalse(self.account()['positions']);self.assertNotIn(MINT,self.live.protected)
  w=status['writeoffs'][0];self.assertEqual(w['pnl_sol'],-cost);self.assertFalse(w['sale_executed']);self.assertIsNone(w['exit_time']);self.assertEqual(w['rug_label'],'unknown')
  self.assertEqual(status['analysis'][0]['trades'],0);self.assertTrue(status['postmortem'])
 def test_global_feed_gap_does_not_auto_write_off_but_healthy_gap_does(self):
  self.open_position();self.paper.s['config']['unresolved_after_seconds']=3
  self.paper.s['running']=False;self.d.state='Disconnected'
  for t in range(1015,1020):self.tick(t)
  self.assertIn(MINT,self.account()['positions'])
  self.d.state='Live';other=copy.deepcopy(self.ctx);other['mint']='other';self.contexts['other']=other
  for t in range(1020,1024):
   other['samples'][-1]['received']=t;self.tick(t)
  self.assertFalse(self.account()['positions']);self.assertEqual(self.account()['writeoffs'],1)
 def test_v1_checkpoint_migrates_new_sizing_without_losing_positions(self):
  self.open_position();version=self.paper.s['version'];cash=self.account()['cash']
  self.paper.s['config'].pop('paper_policy_revision');self.paper.close()
  self.paper=LivePaper(self.path,self.d,clock=lambda:self.now)
  self.assertEqual(self.paper.s['config']['size_usd'],50);self.assertEqual(self.paper.s['config']['max_hold_seconds'],0)
  self.assertEqual(self.account()['cash'],cash);self.assertEqual(self.account()['positions'][MINT]['entry_version'],version)
 def test_signal_ceiling_cannot_reset_to_chase_same_move(self):
  self.tick(1000);ceiling=self.account()['pending'][MINT]['maximum_entry_price']
  self.sample(1002,.013);self.tick(1002);self.assertFalse(self.account()['positions'])
  self.sample(1013,.013);self.tick(1013)
  self.assertEqual(self.account()['pending'][MINT]['maximum_entry_price'],ceiling)
  self.sample(1015,.013);self.tick(1015);self.assertFalse(self.account()['positions']);self.assertEqual(self.account()['cash'],10)
 def test_signal_is_rechecked_before_fill(self):
  self.tick(1000);self.sample(1002,.010);self.tick(1002)
  self.assertFalse(self.account()['positions']);self.assertEqual(self.account()['cash'],10)
 def test_entry_timing_separates_account_wait_and_subsequent_event(self):
  self.account()['day_pnl']=-1;self.tick(1000)
  self.account()['day_pnl']=0;self.sample(1005,.011);self.tick(1005)
  self.sample(1007,.011);self.tick(1007.2)
  p=self.account()['positions'][MINT]
  self.assertAlmostEqual(p['signal_to_entry_seconds'],7.2)
  self.assertEqual(p['entry_wait_before_queue_seconds'],5)
  self.assertAlmostEqual(p['entry_delay_seconds'],2.2)
  self.assertAlmostEqual(p['entry_event_to_evaluation_seconds'],.2)
 def test_learning_failure_is_visible_and_does_not_pause_trading(self):
  self.paper.learner.update=Mock(side_effect=RuntimeError('test failure'))
  self.paper.learning_tick();self.assertTrue(self.paper.s['running']);self.assertIn('Research update failed',self.paper.status()['learning']['error'])
  self.paper.learning_tick();self.assertEqual(self.paper.learner.update.call_count,1)
  self.now+=61;self.paper.learner.update=Mock();self.paper.learning_tick();self.assertIsNone(self.paper.learning_error)
 def test_observation_failure_rolls_back_research_and_keeps_paper_entries_running(self):
  self.paper.opportunities.tick=Mock(side_effect=RuntimeError('broken recorder'))
  self.tick(1000)
  self.assertTrue(self.paper.s['running']);self.assertIn(MINT,self.account()['pending'])
  self.assertIn('Observation recording failed',self.paper.s['observation_error'])
 def install_candidate(self,prediction=.2,excluded=None):
  from ml_model import FEATURES,POLICY
  body=dict(baseline_version=self.paper.s['version'],status='paper_candidate',threshold=.02,excluded_mints=excluded or [],report={},model=dict(policy=POLICY,features=list(FEATURES),base=0,trees=[[prediction]]))
  with self.paper.db:
   self.paper.db.execute('INSERT INTO ml_versions VALUES (?,?,?,?)',('candidate1','momentum',900,json.dumps(body)))
   self.paper.sync_model_trial(self.now)
 def test_ml_pair_has_independent_balances_and_applies_filter_at_fill(self):
  self.install_candidate();self.tick(1000)
  self.assertIn(MINT,self.account('ml_control')['pending']);self.assertIn(MINT,self.account('ml_candidate')['pending'])
  self.sample(1002);self.tick(1002)
  self.assertIn(MINT,self.account('ml_candidate')['positions']);self.assertIn(MINT,self.live.protected)
  self.assertEqual(self.account('ml_control')['cash'],self.account('ml_candidate')['cash'])
  self.assertEqual(self.paper.status()['learning']['models']['trial']['id'],'candidate1')
  self.paper.request_exit(dict(strategy='ml_candidate',mint=MINT));self.sample(1004);self.tick(1004)
  self.assertFalse(self.account('ml_candidate')['positions']);self.assertIn(MINT,self.account('ml_control')['positions'])
  self.assertIn(MINT,self.live.protected)
  trade=next(t for t in self.paper.status()['trades'] if t['strategy']=='ml_candidate')
  self.assertEqual(trade['ml_comparison'],'candidate1');self.assertIn('signal_features',trade)
 def test_ml_rejection_does_not_stop_baseline_and_both_arms_exclude_training_coins(self):
  self.install_candidate(prediction=-.1);self.tick(1000)
  self.assertFalse(self.account('ml_candidate')['pending']);self.assertTrue(self.account('ml_control')['pending']);self.assertTrue(self.account()['pending'])
  self.paper.s['ml_trial']['excluded_mints']=[MINT]
  self.sample(1002);self.tick(1002)
  self.assertFalse(self.account('ml_control')['positions']);self.assertTrue(self.account()['positions'])
 def test_exploration_is_stable_bounded_and_still_obeys_risk_rules(self):
  import hashlib
  self.install_candidate(prediction=-.1)
  def chosen(identity,mint):return int(hashlib.sha256((identity+':'+mint).encode()).hexdigest()[:8],16)/2**32<.05
  identity=next(str(i) for i in range(1000) if chosen(str(i),MINT));self.paper.s['ml_trial']['id']=identity
  self.tick(1000);self.assertTrue(self.account('ml_candidate')['pending'][MINT]['exploration'])
  other=next('other'+str(i) for i in range(1000) if chosen(identity,'other'+str(i)));ctx={**self.ctx,'mint':other}
  self.assertEqual(self.paper.signal_reason('ml_candidate',ctx,self.paper.features(ctx,1000)),'ML filter skipped this signal')
  self.ctx['risk']['mint_authority']='active';self.sample(1002);self.tick(1002)
  self.assertFalse(self.account('ml_candidate')['positions'])
 def test_observed_buyer_counts_distinguish_missing_identity(self):
  self.assertIsNone(self.paper.features(self.ctx,1000)['unique_buyers'])
  for e in self.ctx['samples']:e['wallet']='same-wallet'
  f=self.paper.features(self.ctx,1000);self.assertEqual(f['unique_buyers'],1);self.assertEqual(f['buyer_velocity'],.1)
 def test_broken_model_skips_candidate_without_pausing_baseline(self):
  self.install_candidate();self.paper.s['ml_trial']['model']={};self.tick(1000)
  self.assertTrue(self.paper.s['running']);self.assertTrue(self.account()['pending']);self.assertFalse(self.account('ml_candidate')['pending'])
 def test_ml_model_and_accounts_survive_restart_paused_and_clear_removes_models(self):
  self.install_candidate();self.open_position();model=copy.deepcopy(self.paper.s['ml_trial'])
  self.paper.close();self.paper=LivePaper(self.path,self.d,self.cfg,clock=lambda:self.now)
  self.assertFalse(self.paper.s['running']);self.assertEqual(self.paper.s['ml_trial'],model)
  self.assertIn(MINT,self.account('ml_candidate')['positions'])
  with self.assertRaises(ValueError):self.paper.control('clear')
  for a in self.paper.s['accounts'].values():a['positions']={};a['pending']={}
  self.paper.control('clear');self.assertEqual(len(self.paper.s['accounts']),2)
  self.assertEqual(self.paper.db.execute('SELECT COUNT(*) FROM ml_versions').fetchone()[0],0)
 def test_finished_comparison_waits_for_positions_then_archives_and_cannot_repeat(self):
  self.install_candidate();self.open_position();self.paper.s['ml_trial']['entries_until']=1003
  self.paper.sync_model_trial(1004);self.assertIn('ml_trial',self.paper.s)
  for key in ('ml_control','ml_candidate'):self.account(key)['positions']={};self.account(key)['pending']={}
  self.paper.sync_model_trial(1005);self.assertNotIn('ml_trial',self.paper.s)
  self.assertEqual(self.paper.db.execute('SELECT COUNT(*) FROM ml_comparisons').fetchone()[0],1)
  self.paper.sync_model_trial(1006);self.assertNotIn('ml_trial',self.paper.s)
 def test_qualifying_signal_anchor_survives_account_limit(self):
  self.account()['day_pnl']=-1;self.tick(1000);anchor=self.account()['entry_signals'][MINT]['price']
  self.account()['day_pnl']=0;self.sample(1002,.013);self.tick(1002)
  self.assertEqual(self.account()['pending'][MINT]['signal_price'],anchor)
  self.sample(1004,.013);self.tick(1004);self.assertFalse(self.account()['positions'])
 def test_dollars_frozen_on_entry_exit_and_stale_pnl_missing(self):
  rate=[150.];self.paper.usd=Mock();self.paper.usd.rate.side_effect=lambda:rate[0]
  self.paper.usd.snapshot.side_effect=lambda:dict(rate=rate[0],status='fresh')
  self.ctx['supply_tokens']=1000000;self.open_position();view=self.paper.status()['accounts'][0]['positions'][0]
  self.assertEqual(view['entry_fdv_usd'],1650000);self.assertIsNotNone(view['pnl_usd'])
  rate[0]=160;self.sample(1004,.016);self.tick(1004);self.sample(1006,.016);self.tick(1006)
  t=self.paper.status()['trades'][0];self.assertEqual(t['entry_fdv_usd'],1650000);self.assertEqual(t['exit_fdv_usd'],2560000)
  self.assertAlmostEqual(t['pnl_usd'],t['pnl_sol']*160);self.assertEqual(t['signal_to_entry_seconds'],2)
 def test_entry_current_exit_cap_are_distinct_and_frozen(self):
  self.ctx.update(supply_tokens=1000000,supply_observed=990,symbol='TEST')
  self.open_position();entry=self.paper.status()['accounts'][0]['positions'][0]
  self.assertAlmostEqual(entry['entry_fdv_sol'],11000);self.assertAlmostEqual(entry['current_fdv_sol'],11000)
  self.sample(1004,.016);self.tick(1004);current=self.paper.status()['accounts'][0]['positions'][0]
  self.assertEqual(current['entry_fdv_sol'],entry['entry_fdv_sol']);self.assertEqual(current['current_fdv_sol'],16000)
  self.sample(1006,.016);self.tick(1006);trade=self.paper.status()['trades'][0]
  self.assertEqual(trade['entry_fdv_sol'],entry['entry_fdv_sol']);self.assertEqual(trade['exit_fdv_sol'],16000)
  self.assertEqual(trade['symbol'],'TEST');self.assertGreater(trade['id'],0)
  self.ctx['supply_tokens']=2000000
  self.assertEqual(self.paper.status()['trades'][0]['entry_fdv_sol'],entry['entry_fdv_sol'])
 def test_missing_and_stale_caps_are_not_zero_or_invented(self):
  self.open_position();self.assertIsNone(self.paper.status()['accounts'][0]['positions'][0]['entry_fdv_sol'])
  self.ctx['supply_tokens']=1000000;self.sample(1004);self.tick(1004);self.now=1015
  view=self.paper.status()['accounts'][0]['positions'][0]
  self.assertIsNone(view['current_fdv_sol']);self.assertIsNone(view['entry_fdv_sol']);self.assertAlmostEqual(view['last_known_fdv_sol'],11000)
 def test_large_cap_pools_are_screened_and_coverage_is_explicit(self):
  self.ctx['supply_tokens']=1000000000
  reason,features=self.paper.screen(self.ctx,1000)
  self.assertIsNone(reason);self.assertGreater(features['fdv_sol'],10000000)
  coverage=self.paper.status()['feed']['valuation_coverage']
  self.assertEqual(coverage['above_10000_sol'],1);self.assertEqual(coverage['unknown_pools'],0)
  self.now=1015;self.assertEqual(self.paper.status()['feed']['valuation_coverage']['valued_pools'],0)
 def test_name_backfill_updates_closed_trade_without_changing_results(self):
  self.open_position();self.sample(1004,.016);self.tick(1004);self.sample(1006,.016);self.tick(1006)
  before=self.paper.status()['trades'][0]
  self.market.enrich_names=Mock();self.market.names.remember(MINT,dict(name='Real coin',symbol='REAL'))
  self.paper.enrich_names();after=self.paper.status()['trades'][0]
  self.assertEqual(after['name'],'Real coin');self.assertEqual(after['symbol'],'REAL');self.assertEqual(after['pnl_sol'],before['pnl_sol']);self.assertEqual(after['entry_features'],before['entry_features'])
 def test_stale_value_survives_and_feed_gap_is_not_liquidity_loss(self):
  self.open_position();fresh=self.paper.status()['accounts'][0]['positions'][0]
  self.now=1015;self.d.state='Disconnected';stale=self.paper.status()['accounts'][0]['positions'][0]
  self.assertEqual(stale['mark_sol'],0);self.assertEqual(stale['last_known_mark_sol'],fresh['mark_sol']);self.assertEqual(stale['data_health'],'feed_gap')
  self.assertEqual(stale['last_observation_age_seconds'],13)
 def test_quote_comparison_never_changes_inventory_or_cash(self):
  self.open_position();before=self.account()['cash'];quantity=self.account()['positions'][MINT]['quantity']
  self.paper.quotes=Mock();self.paper.quotes.check.return_value=dict(status='quoted',checked=1002,out_raw=95000000,minimum_raw=94050000,route=[dict(pool='pool',venue='PumpSwap')],price_impact_pct=.1)
  self.paper.quote_tick();p=self.account()['positions'][MINT]
  self.assertEqual(self.account()['cash'],before);self.assertEqual(p['quantity'],quantity);self.assertEqual(p['last_quote']['output'],.095)
  self.assertTrue(p['last_quote']['same_pool']);self.assertEqual(self.paper.db.execute('SELECT COUNT(*) FROM quote_checks').fetchone()[0],1)
  self.paper.quote_tick();self.assertLessEqual(self.paper.quotes.check.call_count,2)
  self.now=1018;self.assertFalse(self.paper.status()['accounts'][0]['positions'][0]['last_quote']['fresh'])
 def test_cost_analysis_is_retained_and_reset_per_run(self):
  self.open_position();self.sample(1004,.016);self.tick(1004);self.sample(1006,.016);self.tick(1006)
  status=self.paper.status();t=status['trades'][0];a=status['analysis'][0]
  self.assertEqual(t['holding_seconds'],4);self.assertEqual(t['entry_delay_seconds'],2);self.assertGreater(t['entry_costs']['total_sol'],0)
  self.assertEqual(a['trades'],1);self.assertEqual(a['win_rate_pct'],100);self.assertEqual(a['cost_coverage'],1)
  self.paper.control('pause');self.paper.control('new');self.assertEqual(self.paper.status()['analysis'][0]['trades'],0);self.assertEqual(self.paper.status()['trades'],[])
 def test_memory_pressure_keeps_engine_running_and_manages_exits(self):
  self.open_position();self.live.memory_pressure=True;self.sample(1004,.016);self.tick(1004)
  self.assertTrue(self.paper.s['running']);self.assertEqual(self.account()['pending'][MINT]['side'],'SELL')
  self.assertTrue(self.paper.control('start')['running'])
 def test_current_candidates_update_without_rewriting_audit_features(self):
  self.paper.control('pause');self.tick(1000)
  original=self.paper.features(self.ctx,1000)
  with self.paper.db:self.paper.decision('momentum',MINT,'watching','Same reason',original,1000)
  self.now=1002;self.sample(1002,.012)
  status=self.paper.status();candidate=next(d for d in status['candidates'] if d['strategy']=='momentum')
  self.assertEqual(candidate['features']['trade_count'],3);self.assertEqual(status['decisions'][0]['features']['trade_count'],2)
  self.assertEqual(status['feed']['fresh_pools'],1);self.assertFalse(status['running'])
  self.contexts['launch']={**self.ctx,'mint':'launch','pool':None,'samples':[]}
  self.assertEqual(len(self.paper.status()['candidates']),2);self.assertEqual(self.paper.status()['feed']['waiting_for_pool'],1)
 def test_missing_data_reasons_are_distinct(self):
  self.ctx.pop('decimals');self.assertEqual(self.paper.screen(self.ctx,1000)[0],'Waiting for verified mint decimals')
  self.ctx['decimals']=6;self.ctx['samples']=[];self.assertEqual(self.paper.screen(self.ctx,1000)[0],'Waiting for first mapped SOL-pool trade')
  self.sample(900);self.assertEqual(self.paper.screen(self.ctx,1000)[0],'Mapped SOL-pool trades are stale')
 def test_pool_fill_costs_reduce_output_and_account_for_exit(self):
  self.open_position();p=self.account()['positions'][MINT];self.assertLess(p['quantity'],.1/.011)
  self.sample(1004,.016);self.tick(1004);self.assertEqual(self.account()['pending'][MINT]['reason'],'Take profit')
  self.sample(1006,.016);self.tick(1006);self.assertFalse(self.account()['positions']);self.assertEqual(self.account()['closed'],1)
  self.assertAlmostEqual(self.account()['cash'],10+self.account()['realized_pnl']);self.assertGreater(self.account()['realized_pnl'],0)
  self.assertNotIn(MINT,self.live.protected);self.assertEqual(self.paper.db.execute('SELECT COUNT(*) FROM trades').fetchone()[0],1)
 def test_stale_exit_never_fabricates_fill(self):
  self.open_position();self.tick(1023);self.assertIn(MINT,self.account()['positions']);self.assertEqual(self.account()['pending'][MINT]['side'],'SELL')
  self.tick(1025);self.assertIn(MINT,self.account()['positions']);self.assertEqual(self.account()['closed'],0);self.assertEqual(self.paper.status()['accounts'][0]['positions'][0]['mark_sol'],0)
 def test_clear_and_discard_protect_pending_and_open_positions(self):
  self.tick(1000);self.d.clear();self.assertEqual(self.live.db.execute('SELECT COUNT(*) FROM launch_events').fetchone()[0],1)
  with self.assertRaises(ValueError):self.d.discard({'mint':MINT})
  with self.assertRaises(ValueError):self.paper.control('clear')
  self.paper.control('pause');self.assertNotIn(MINT,self.live.protected);self.paper.control('clear');self.assertEqual(self.paper.db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],0)
 def test_pause_entries_continues_position_exits(self):
  self.open_position();self.paper.control('pause');self.sample(1004,.008);self.tick(1004);self.assertEqual(self.account()['pending'][MINT]['reason'],'Stop loss')
  self.sample(1006,.008);self.tick(1006);self.assertFalse(self.account()['positions']);self.assertLess(self.account()['realized_pnl'],0)
 def test_active_authority_rejected_and_no_migration_inferred(self):
  self.ctx['risk']['mint_authority']='creator';self.tick(1000);self.assertFalse(self.account()['pending'])
  self.ctx['risk']['mint_authority']=None;self.sample(1002);self.tick(1002);self.assertFalse(self.account('recovery')['pending'])
  self.assertTrue(self.paper.db.execute("SELECT 1 FROM decisions WHERE strategy='recovery' AND reason='Verified migration evidence missing'").fetchone())
 def test_verified_recovery_requires_dip_then_rebound(self):
  self.ctx.update(stage='verified_migrated',migration_received=995)
  self.ctx['samples']=[];self.sample(997,.020);self.sample(998,.015);self.sample(1000,.016)
  self.tick(1000);self.assertIn(MINT,self.account('recovery')['pending']);self.assertFalse(self.account()['pending'])
 def test_adverse_move_rejects_entry_without_spending(self):
  self.tick(1000);self.sample(1002,.02);self.tick(1002);self.assertFalse(self.account()['positions']);self.assertEqual(self.account()['cash'],10)
  self.assertTrue(self.paper.db.execute("SELECT 1 FROM decisions WHERE reason='Skipped: entry exceeded signal ceiling (+10%)'").fetchone())
 def test_restart_restores_positions_and_pauses_entries(self):
  self.open_position();cash=self.account()['cash'];self.paper.close();self.paper=LivePaper(self.path,self.d,self.cfg,clock=lambda:self.now)
  self.assertFalse(self.paper.s['running']);self.assertEqual(self.account()['cash'],cash);self.assertIn(MINT,self.account()['positions']);self.assertIn(MINT,self.live.protected)
 def test_decision_features_are_frozen_and_labels_missing_without_future_data(self):
  self.tick(1000);r=self.paper.db.execute("SELECT * FROM decisions WHERE features LIKE '%0.011%' LIMIT 1").fetchone();features=r['features']
  self.sample(1030,.02);self.paper.control('pause');self.tick(1030)
  self.assertEqual(self.paper.db.execute('SELECT features FROM decisions WHERE id=?',(r['id'],)).fetchone()[0],features)
  self.assertTrue(self.paper.db.execute("SELECT 1 FROM labels WHERE status='observed'").fetchone())
  self.contexts={};self.tick(1130);self.assertTrue(self.paper.db.execute("SELECT 1 FROM labels WHERE status='unavailable'").fetchone())
 def test_daily_loss_limit_and_reset_guards(self):
  self.account()['day_pnl']=-1;self.tick(1000);self.assertFalse(self.account()['pending'])
  with self.assertRaises(ValueError):self.paper.control('new')
  self.paper.control('pause');self.paper.control('new');self.assertEqual(self.account()['cash'],10)
 def test_record_retention_and_database_cap(self):
  with self.paper.db:self.paper.db.executemany('INSERT INTO decisions(mint,strategy,created,state,reason,version,features) VALUES (?,?,?,?,?,?,?)',[(MINT,'momentum',t,'watching','test','v','{}') for t in range(10005)]);self.paper.prune()
  self.assertEqual(self.paper.db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],10000);self.assertEqual(self.paper.db.execute('PRAGMA max_page_count').fetchone()[0],12800)
 def test_versions_and_old_run_summary_remain_available(self):
  self.paper.control('pause');old=self.paper.s['id'];self.paper.control('new');export=self.paper.export()
  self.assertEqual(export['runs'][0]['id'],old);self.assertEqual(len(export['versions']),1);self.assertNotEqual(self.paper.s['id'],old)
 def test_recovery_rejects_rebound_before_drop(self):
  self.ctx.update(stage='verified_migrated',migration_received=995);self.ctx['samples']=[]
  self.sample(997,.015);self.sample(998,.020);self.sample(1000,.016);self.tick(1000);self.assertFalse(self.account('recovery')['pending'])
 def test_failed_exit_retains_inventory_and_cash(self):
  self.open_position();cash=self.account()['cash'];quantity=self.account()['positions'][MINT]['quantity']
  self.sample(1004,.008);self.tick(1004);self.sample(1006,.004);self.tick(1006)
  self.assertIn(MINT,self.account()['positions']);self.assertEqual(self.account()['cash'],cash);self.assertEqual(self.account()['positions'][MINT]['quantity'],quantity);self.assertEqual(self.account()['closed'],0)
