import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from engine import Bot
from market import Market,ZERO
MINT='So11111111111111111111111111111111111111112'
class MarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.bot=Bot(Path(self.tmp.name)/'db');self.rpc=Mock();self.m=Market(self.bot,self.rpc)
        with self.bot.db:self.bot.db.execute('INSERT INTO market_mints VALUES (?,6)',(MINT,))
    def tearDown(self):self.bot.close();self.tmp.cleanup()
    def event(self,sig='one',ts=100,sol='2000000000'):
        return dict(signature=sig,event_index=1,mint=MINT,slot=ts,timestamp=str(ts),received=ts+1,sol_amount=sol,token_amount='1000000',is_buy=True,real_sol_reserves='3000000000',real_token_reserves='2000000',quote_mint=ZERO)
    def test_candles_from_trades_not_gap_fill(self):
        for e in [self.event(),self.event('two',102,'4000000000'),self.event('three',120,'1000000000')]:self.m.ingest(e)
        r=self.m.read(MINT,5);self.assertEqual(len(r['candles']),2);c=r['candles'][0];self.assertEqual((c['open'],c['high'],c['low'],c['close'],c['volume_sol']),(2,4,2,4,6));self.assertEqual(r['real_sol_reserves'],'3')
    def test_duplicate_and_out_of_order(self):
        self.m.ingest(self.event('late',110));self.m.ingest(self.event());self.m.ingest(self.event());r=self.m.read(MINT,5)
        self.assertEqual(len(r['trades']),2);self.assertEqual(r['candles'][0]['timestamp'],100)
    def test_unknown_quote_and_zero_rejected(self):
        self.assertFalse(self.m.ingest({**self.event(),'quote_mint':'unsupported'}));self.assertFalse(self.m.ingest(self.event(sol='0')));self.assertEqual(self.m.read(MINT)['candles'],[])
    def test_valuation_fees_and_memory_deduplicated(self):
        self.m.launch({'mint':MINT,'token_total_supply':'1000000000','received':99})
        e={**self.event(),'fee':'10000000','creator_fee':'2000000'}
        self.m.ingest(e);self.m.ingest(e)
        m=self.m.metrics([MINT])[MINT]
        self.assertEqual(m['fdv_sol'],'2000');self.assertEqual(m['volume_sol'],'2')
        self.assertEqual(m['protocol_fees_sol'],'0.01');self.assertEqual(m['creator_fees_sol'],'0.002')
        self.assertEqual((m['buys'],m['sells']),(1,0))
        self.assertEqual(self.bot.db.execute('SELECT COUNT(*) FROM feature_memory').fetchone()[0],1)
    def test_missing_supply_has_no_fabricated_cap(self):
        self.m.ingest(self.event());self.assertIsNone(self.m.metrics([MINT])[MINT]['fdv_sol'])
    def test_old_slot_does_not_overwrite_latest_price(self):
        self.m.launch({'mint':MINT,'token_total_supply':'1000000000','received':99})
        self.m.ingest(self.event('new',120,'4000000000'));self.m.ingest(self.event('old',100))
        m=self.m.metrics([MINT])[MINT];self.assertEqual(m['fdv_sol'],'4000');self.assertEqual(m['volume_sol'],'6')
    def test_invalid_interval_and_mint(self):
        with self.assertRaises(ValueError):self.m.read(MINT,0)
        with self.assertRaises(ValueError):self.m.read('bad')
    def test_no_decimals_no_guessed_price(self):
        with self.bot.db:self.bot.db.execute('DELETE FROM market_mints')
        self.m.ingest(self.event());self.rpc.return_value={'value':None}
        with self.assertRaises(ValueError):self.m.read(MINT)
