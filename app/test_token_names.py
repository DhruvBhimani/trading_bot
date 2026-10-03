import base64
import json
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from token_names import TokenNames,parse_metadata,extension_name,PROGRAM

MINT='So11111111111111111111111111111111111111112'
HEX='01'*32
def account(name='Example',symbol='EX'):
    data=bytes([4])+bytes(32)+bytes.fromhex(HEX)
    for s in (name,symbol):
        b=s.encode();data+=len(b).to_bytes(4,'little')+b
    return dict(owner=PROGRAM,executable=False,data=[base64.b64encode(data).decode(),'base64'])

class NameTests(unittest.TestCase):
    def test_real_token_2022_name_and_closed_token_fallback(self):
        fixture=json.loads(Path(__file__).with_name('fixtures').joinpath('token-2022-name.json').read_text())
        mint=fixture['mint'];a=fixture['account']
        self.assertEqual(extension_name(a,mint),dict(name='Super Accelerationism',symbol='s/acc'))
        self.assertIsNone(extension_name(a,MINT));self.assertIsNone(extension_name({**a,'owner':'wrong'},mint))
        rpc=Mock(side_effect=[{'value':[None]},{'value':[a]}]);names=TokenNames(rpc)
        helper=Mock(stdout=json.dumps([dict(mint=mint,hex=HEX,address='metadata')]))
        with patch('token_names.subprocess.run',return_value=helper):names.enrich([mint])
        self.assertEqual(names.get(mint)['symbol'],'s/acc');self.assertEqual(rpc.call_count,2)
    def test_owner_mint_discriminator_and_lengths_verified(self):
        self.assertEqual(parse_metadata(account(),HEX),dict(name='Example',symbol='EX'))
        self.assertIsNone(parse_metadata({**account(),'owner':'wrong'},HEX))
        self.assertIsNone(parse_metadata(account(),'02'*32))
        self.assertIsNone(parse_metadata(account('x'*33),HEX))
        bad=account();bad['data'][0]=base64.b64encode(b'\x03'+base64.b64decode(bad['data'][0])[1:]).decode()
        self.assertIsNone(parse_metadata(bad,HEX))
        self.assertEqual(parse_metadata(account('Coin\x00\u202e'),HEX)['name'],'Coin')
    def test_malformed_data_is_ignored(self):
        for data in (['!bad','base64'],['AAAA','base64'],['x','jsonParsed'],None):
            self.assertIsNone(parse_metadata({**account(),'data':data},HEX))
    def test_cache_retry_and_batch_bounded_and_clear_race(self):
        rpc=Mock(return_value={'value':[account()]});names=TokenNames(rpc)
        helper=Mock(stdout=json.dumps([dict(mint=MINT,hex=HEX,address='metadata')]))
        with patch('token_names.subprocess.run',return_value=helper):
            names.enrich([MINT],accept=lambda:False);self.assertEqual(names.get(MINT),{})
            names.enrich([MINT]);self.assertEqual(rpc.call_count,1)
            names.retry.clear();names.enrich([MINT]);self.assertEqual(names.get(MINT)['name'],'Example')
            names.enrich([MINT]);self.assertEqual(rpc.call_count,2)
        for i in range(2000):names.remember(str(i),dict(name='Coin',symbol='C'))
        self.assertEqual(len(names.cache),256)
        with patch('token_names.subprocess.run',side_effect=ValueError('helper unavailable')):
            for i in range(30):
                try:names.enrich(['missing'+str(i*20+j) for j in range(50)])
                except ValueError:pass
        self.assertEqual(len(names.retry),256)
