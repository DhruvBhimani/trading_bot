import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from engine import Bot
from chain import Chain

ADDRESS='So11111111111111111111111111111111111111112'
def row(n):return dict(signature=str(n),slot=n,blockTime=100+n)
class ChainTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.bot=Bot(Path(self.temp.name)/'db');self.rpc=Mock();self.chain=Chain(self.bot,self.rpc);self.chain.watch({'address':ADDRESS})
    def tearDown(self):self.bot.close();self.temp.cleanup()
    def watch(self):return self.chain.status()['watches'][0]
    def test_dedup_and_cursor(self):
        self.rpc.return_value=[row(2),row(1)];self.chain.scan(self.watch());self.chain.scan(self.watch())
        self.assertEqual(len(self.chain.status()['events']),2);self.assertEqual(self.watch()['cursor'],'2')
    def test_pagination_restart_checkpoint(self):
        self.rpc.return_value=[row(1)];self.chain.scan(self.watch())
        self.rpc.return_value=[row(n) for n in range(25,5,-1)];self.chain.scan(self.watch())
        self.assertEqual(self.watch()['cursor'],'1');self.assertEqual(self.watch()['before_sig'],'6')
        resumed=Chain(self.bot,self.rpc);self.rpc.return_value=[row(n) for n in range(5,0,-1)];resumed.scan(self.watch())
        self.assertEqual(self.watch()['cursor'],'25');self.assertEqual(len(self.chain.status()['events']),25)
    def test_history_gap_not_hidden(self):
        self.rpc.return_value=[row(1)];self.chain.scan(self.watch());self.rpc.return_value=[row(3)];self.chain.scan(self.watch())
        self.assertIn('gap',self.watch()['status']);self.assertEqual(self.watch()['cursor'],'1')
    def test_failure_retains_cursor_and_retries_receipt(self):
        self.rpc.return_value=[row(1)];self.chain.scan(self.watch());self.rpc.side_effect=RuntimeError('offline');self.chain.tick()
        self.assertEqual(self.watch()['cursor'],'1');self.assertEqual(self.chain.status()['events'][0]['attempts'],1)
    def test_receipt_saved_and_pause(self):
        self.rpc.return_value=[row(1)];self.chain.scan(self.watch());self.chain.watch({'address':ADDRESS,'enabled':False})
        self.rpc.return_value={'transaction':{'signatures':['1']},'meta':{'err':None}};self.chain.tick()
        self.assertEqual(self.chain.status()['events'][0]['downloaded'],1)
    def test_invalid_input(self):
        with self.assertRaises(ValueError):self.chain.watch({'address':'bad'})
