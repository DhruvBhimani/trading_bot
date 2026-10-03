import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from engine import Bot
from wallet import Wallet,SOL,USDC

class WalletTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.bot=Bot(Path(self.temp.name)/'test.sqlite3');self.wallet=Wallet(self.bot)
    def tearDown(self):self.bot.close();self.temp.cleanup()
    def response(self):
        return dict(inputMint=SOL,outputMint=USDC,inAmount='10000000',outAmount='1200000',otherAmountThreshold='1188000',slippageBps=100,swapType='aggregator',inUsdValue=1.2,priceImpactPct=.01,routePlan=[dict(percent=100,swapInfo=dict(ammKey=SOL,label='test'))],requestId='test',transaction=None)
    def body(self):return dict(input_mint=SOL,output_mint=USDC,amount='0.01')
    def test_real_quote_shape_and_storage(self):
        with patch('wallet.fetch',return_value=self.response()):q=self.wallet.quote(self.body())
        self.assertEqual(q['output_amount'],'1.2');self.assertEqual(q['minimum_output'],'1.188')
        self.assertEqual(self.wallet.status()['orders'][0]['status'],'quoted')
    def test_quote_mismatch_and_oversized_value_rejected(self):
        for field,value in [('inputMint',USDC),('inUsdValue',100),('otherAmountThreshold','1'),('swapType','rfq')]:
            self.wallet.last_quote=None;r=self.response();r[field]=value
            with patch('wallet.fetch',return_value=r),self.assertRaises(ValueError):self.wallet.quote(self.body())
    def test_disabled_execution_never_calls_provider(self):
        with patch('wallet.fetch') as fetch,self.assertRaises(ValueError):self.wallet.execute({'id':'x','signed_transaction':'x'})
        fetch.assert_not_called()
    def test_expired_or_duplicate_quote_never_sends(self):
        self.wallet.enabled=True
        q=self.response();q.update(transaction='x',_wallet=SOL,_expires=time.time()-1)
        with self.bot.db:self.bot.db.execute('INSERT INTO wallet_orders VALUES (?,?,?,?,?,?,?)',('test',time.time(),SOL,'quoted',json.dumps(q),None,None))
        with patch('wallet.fetch') as fetch,self.assertRaises(ValueError):self.wallet.execute({'id':'test','signed_transaction':'x'})
        fetch.assert_not_called()
        with self.bot.db:self.bot.db.execute("UPDATE wallet_orders SET status='submitting'")
        with patch('wallet.fetch') as fetch,self.assertRaises(ValueError):self.wallet.execute({'id':'test','signed_transaction':'x'})
        fetch.assert_not_called()
    def test_submission_uncertainty_blocks_duplicate_send(self):
        from types import SimpleNamespace
        self.wallet.enabled=True
        q=self.response();q.update(transaction='x',_wallet=SOL,_expires=time.time()+20)
        with self.bot.db:self.bot.db.execute('INSERT INTO wallet_orders VALUES (?,?,?,?,?,?,?)',('one',time.time(),SOL,'quoted',json.dumps(q),None,None))
        guard=SimpleNamespace(returncode=0,stdout=json.dumps({'signature':'testsig'}))
        with patch('wallet.subprocess.run',return_value=guard),patch.object(self.wallet,'rpc',return_value={'value':{'err':None}}),patch('wallet.fetch',side_effect=TimeoutError):
            result=self.wallet.execute({'id':'one','signed_transaction':'x'})
        self.assertEqual(result['status'],'unknown')
        with patch('wallet.fetch') as fetch,self.assertRaises(ValueError):self.wallet.execute({'id':'one','signed_transaction':'x'})
        fetch.assert_not_called()

    def test_failed_simulation_never_sends(self):
        from types import SimpleNamespace
        self.wallet.enabled=True;q=self.response();q.update(transaction='x',_wallet=SOL,_expires=time.time()+20)
        with self.bot.db:self.bot.db.execute('INSERT INTO wallet_orders VALUES (?,?,?,?,?,?,?)',('sim',time.time(),SOL,'quoted',json.dumps(q),None,None))
        with patch('wallet.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='{"signature":"sig"}')),patch.object(self.wallet,'rpc',return_value={'value':{'err':'failure'}}),patch('wallet.fetch') as fetch,self.assertRaises(ValueError):
            self.wallet.execute({'id':'sim','signed_transaction':'x'})
        fetch.assert_not_called()

    def test_amounts_are_exact_integers(self):
        with self.assertRaises(ValueError):self.wallet.quote({**self.body(),'amount':'0.0000000001'})

if __name__=='__main__':unittest.main()
