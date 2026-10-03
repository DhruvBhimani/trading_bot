"""Offline launch -> migration -> real adapter -> paper entry/exit regression."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from discovery import Discovery
from live_store import LiveStore
from market import Market,SOL
from live_paper import LivePaper

MINT='B'*32
AMM='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA'
class PipelineTests(unittest.TestCase):
 def test_live_adapter_to_paper_and_migration_identity(self):
  with tempfile.TemporaryDirectory() as tmp:
   now=[1000.];live=LiveStore();rpc=Mock(return_value={'value':[{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'type':'mint','info':{'decimals':6,'supply':'1000000000000000','mintAuthority':None,'freezeAuthority':None}}}}]})
   market=Market(live,rpc);d=Discovery(live,market)
   d.ingest(dict(type='event',kind='pool',base_mint=MINT,pool='pool',quote_mint=SOL,base_mint_decimals=6,signature='launch',event_index=1,slot=1,received=940,name='Integration coin'))
   d.ingest(dict(type='event',kind='migration',mint=MINT,pool='wrong-pool',quote_mint=SOL,signature='migration',event_index=2,slot=2,received=950))
   market.enrich();self.assertEqual(market.paper_snapshot(1000)[MINT]['stage'],'migration_unknown')
   d.ingest(dict(type='event',kind='migration',mint=MINT,pool='pool',quote_mint=SOL,signature='migration2',event_index=2,slot=3,received=951))
   def trade(t,price):
    d.ingest(dict(type='event',kind='trade',program=AMM,mint=MINT,pool='pool',quote_mint=SOL,signature='trade'+str(t),event_index=1,slot=t,timestamp=str(t),received=t,is_buy=True,sol_amount='200000000',token_amount=str(int(.2/price*1e6)),real_sol_reserves='100000000000',real_token_reserves=str(int(100/price*1e6)),lp_fee='200000',fee='200000',creator_fee='100000'))
   trade(999,.01);trade(1000,.011)
   paper=LivePaper(Path(tmp)/'paper.sqlite3',d,dict(size_usd=0,min_age_seconds=0,min_window_trades=2,min_window_volume_sol=.01,momentum=.02),clock=lambda:now[0])
   try:
    paper.control('start');paper.tick();self.assertIn(MINT,paper.s['accounts']['momentum']['pending'])
    now[0]=1002;trade(1002,.011);paper.tick();self.assertIn(MINT,paper.s['accounts']['momentum']['positions'])
    d.clear();self.assertEqual(live.db.execute('SELECT COUNT(*) FROM launch_events').fetchone()[0],1)
    # Only events from the new clear generation may update the protected position.
    # Use current-generation events directly after clearing.
    now[0]=1004
    event=dict(type='event',kind='trade',generation=live.generation,program=AMM,mint=MINT,pool='pool',quote_mint=SOL,signature='exit-signal',event_index=1,slot=1004,timestamp='1004',received=1004,is_buy=True,sol_amount='200000000',token_amount='12500000',real_sol_reserves='100000000000',real_token_reserves='6250000000',fee='200000',creator_fee='100000')
    d.ingest(event);paper.tick();self.assertEqual(paper.s['accounts']['momentum']['pending'][MINT]['side'],'SELL')
    now[0]=1006;d.ingest({**event,'signature':'exit-fill','slot':1006,'timestamp':'1006','received':1006});paper.tick();self.assertEqual(paper.s['accounts']['momentum']['closed'],1)
   finally:paper.close();live.close()
