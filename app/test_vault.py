import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock
from contextlib import nullcontext
from engine import Bot
from vault import Vault
from wallet import Wallet

ADDRESS='So11111111111111111111111111111111111111112'
class VaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.bot=Bot(Path(self.tmp.name)/'db');Wallet(self.bot);self.wallet=Mock(enabled=True);self.v=Vault(self.bot,self.wallet)
        self.v.crypto=Mock(return_value={'address':ADDRESS,'vault':{'version':1}})
        self.id=self.v.add({'kind':'bot','name':'Test','password':'not-a-real-secret'})['id']
        self.v.unlock({'id':self.id,'password':'not-a-real-secret'})
    def tearDown(self):self.bot.close();self.tmp.cleanup()
    def enable(self):self.v.enable({'id':self.id,'enabled':True,'acknowledge':True})
    def queue(self):return self.v.enqueue({'id':self.id,'input_mint':ADDRESS,'output_mint':'token','amount':'0.01','slippage_bps':100})
    def test_explicit_enable_and_restart_lock(self):
        with self.assertRaises(ValueError):self.queue()
        with self.assertRaises(ValueError):self.v.enable({'id':self.id,'enabled':True})
        self.enable();self.queue();restarted=Vault(self.bot,self.wallet)
        self.assertFalse(restarted.list()['wallets'][0]['unlocked']);self.assertEqual(restarted.list()['jobs'][0]['state'],'interrupted')
    def test_lock_cancels_pending_and_remove_clears_key(self):
        self.enable();self.queue();self.v.lock_wallet(self.id,remove=True)
        self.assertEqual(self.v.list()['wallets'],[]);self.assertEqual(self.v.list()['jobs'][0]['state'],'cancelled')
        self.assertIsNone(self.bot.db.execute('SELECT vault FROM managed_wallets').fetchone()[0])
    def test_disabled_server(self):
        self.wallet.enabled=False
        with self.assertRaises(ValueError):self.enable()
        with self.assertRaises(ValueError):self.queue()
    def test_budget_blocks_sign_and_send(self):
        self.enable();self.v.sessions[self.id]['reserved']=24;self.queue();self.wallet.quote.return_value={'id':'q','input_usd':2,'transaction':'unsigned'}
        self.v.crypto.reset_mock();self.v.tick();self.v.crypto.assert_not_called();self.wallet.execute.assert_not_called()
    def test_sign_submit_once(self):
        self.enable();self.queue();self.wallet.quote.return_value={'id':'q','input_usd':1,'transaction':'unsigned'};self.v.crypto.return_value={'signed':'signed'}
        def execute(body,permit):
            with permit():pass
            return {'status':'submitted'}
        self.wallet.execute.side_effect=execute;self.v.tick();self.v.tick();self.wallet.execute.assert_called_once();self.assertEqual(self.v.list()['jobs'][0]['state'],'submitted')
    def test_pause_before_submit_prevents_send(self):
        self.enable();self.queue();self.wallet.quote.return_value={'id':'q','input_usd':1,'transaction':'unsigned'};self.v.crypto.return_value={'signed':'signed'}
        sent=[]
        def execute(body,permit):
            self.v.lock_wallet(self.id)
            with permit():sent.append(True)
        self.wallet.execute.side_effect=execute;self.v.tick();self.assertEqual(sent,[])
    def test_new_unlock_cannot_authorize_old_job(self):
        self.enable();self.queue();self.v.unlock({'id':self.id,'password':'not-a-real-secret'});self.enable()
        self.v.tick();self.wallet.quote.assert_not_called();self.wallet.execute.assert_not_called()
        self.assertEqual(self.v.list()['jobs'][0]['state'],'stopped')
    def test_secrets_not_in_list(self):
        self.assertNotIn('not-a-real-secret',json.dumps(self.v.list()));self.assertNotIn('vault',self.v.list()['wallets'][0])
    def test_watch_wallet_cannot_unlock(self):
        self.v.lock_wallet(self.id,remove=True);w=self.v.add({'kind':'watch','address':ADDRESS})
        with self.assertRaises(ValueError):self.v.unlock({'id':w['id'],'password':'abc'})
