import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from engine import Bot
from wallet import Wallet,SOL
from vault import Vault
from portfolio import Portfolio
class PortfolioTests(unittest.TestCase):
    def test_empty_balance_does_not_invent_pnl(self):
        with tempfile.TemporaryDirectory() as folder:
            bot=Bot(Path(folder)/'db');wallet=Wallet(bot);vault=Vault(bot,wallet);w=vault.add({'kind':'watch','address':SOL})
            wallet.balance=Mock(return_value={'sol':0,'slot':1});wallet.rpc=Mock(return_value={'value':[]})
            p=Portfolio(bot,wallet,vault).read(w['id']);self.assertIsNone(p['recorded_pnl_sol']);self.assertIsNone(p['unrealized_pnl']);self.assertEqual(p['holdings'],[]);self.assertEqual(wallet.rpc.call_count,2);bot.close()
