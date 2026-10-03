import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from server import handler
from engine import Bot
from wallet import Wallet
from chain import Chain
from discovery import Discovery
from vault import Vault
from portfolio import Portfolio
from live_store import LiveStore
from market import Market
from live_paper import LivePaper

class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.bot=Bot(Path(cls.temp.name)/'test.sqlite3')
        wallet=Wallet(cls.bot)
        vault=Vault(cls.bot,wallet)
        cls.live=LiveStore();cls.discovery=Discovery(cls.live,Market(cls.live,wallet.rpc))
        cls.paper=LivePaper(Path(cls.temp.name)/'live-paper.sqlite3',cls.discovery)
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler(cls.bot,wallet,Chain(cls.bot,wallet.rpc),cls.discovery,vault,Portfolio(cls.bot,wallet,vault),cls.paper))
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.worker.join();cls.server.server_close();cls.paper.close();cls.bot.close();cls.live.close();cls.temp.cleanup()
    def request(self,path,body=None,origin=True):
        host='127.0.0.1:'+str(self.server.server_port);c=http.client.HTTPConnection(host)
        headers={'Content-Type':'application/json'}
        if origin:headers['Origin']='http://'+host
        c.request('GET' if body is None else 'POST',path,body=None if body is None else json.dumps(body),headers=headers)
        r=c.getresponse();status=r.status;raw=r.read();c.close();return status,raw
    def test_html_and_static_assets(self):
        for path in ['/','/app.js','/style.css','/wallet-bundle.js']:self.assertEqual(self.request(path)[0],200)
    def test_step_and_export(self):
        self.assertEqual(self.request('/api/step',{})[0],200)
        s=json.loads(self.request('/api/state')[1]);self.assertGreater(s['tick'],0)
        self.assertEqual(self.request('/api/export/'+s['id'])[0],200)
    def test_chain_controls(self):
        self.assertEqual(self.request('/api/chain/watch',{'address':'So11111111111111111111111111111111111111112'})[0],200)
        data=json.loads(self.request('/api/chain/status')[1]);self.assertEqual(len(data['watches']),1)
        self.assertEqual(self.request('/api/chain/watch',{'address':'bad'})[0],400)
    def test_wallet_and_discovery_routes(self):
        self.assertEqual(self.request('/api/wallets')[0],200)
        self.assertEqual(self.request('/api/discovery')[0],200)
        self.assertEqual(self.request('/api/wallets/add',{'kind':'watch','address':'bad'})[0],400)
        self.assertEqual(self.request('/api/wallets/unlock',{'id':'x','password':'do-not-log-this'},origin=False)[0],403)
    def test_pin_and_clear_routes(self):
        mint='So11111111111111111111111111111111111111112'
        self.discovery.ingest(dict(type='event',kind='token',signature='create',event_index=1,mint=mint,slot=1,received=1))
        code,raw=self.request('/api/discovery/pin',{'mint':mint,'pinned':True});self.assertEqual(code,200);self.assertEqual(json.loads(raw)['pins'],[mint])
        code,raw=self.request('/api/discovery/clear',{});self.assertEqual(code,200);self.assertEqual(json.loads(raw)['count'],1)
        self.assertEqual(self.request('/api/discovery/pin',{'mint':mint,'pinned':False})[0],200)
        code,raw=self.request('/api/discovery/clear',{});self.assertEqual(json.loads(raw)['count'],0)
        self.assertEqual(self.request('/api/discovery/clear',{},origin=False)[0],403)
    def test_live_paper_routes_and_origin(self):
        code,raw=self.request('/api/live-paper');self.assertEqual(code,200);self.assertEqual(len(json.loads(raw)['accounts']),2)
        self.assertEqual(self.request('/api/live-paper/control',{'action':'start'},origin=False)[0],403)
        code,raw=self.request('/api/live-paper/control',{'action':'start'});self.assertEqual(code,200);self.assertTrue(json.loads(raw)['running'])
        self.assertEqual(self.request('/api/live-paper/control',{'action':'clear'})[0],400)
        self.assertEqual(self.request('/api/live-paper/control',{'action':'pause'})[0],200)
        self.assertEqual(self.request('/api/live-paper/control',{'action':'clear'})[0],200)
        self.assertEqual(self.request('/api/live-paper/export')[0],200)
        self.assertEqual(self.request('/api/live-paper/exit',{'strategy':'momentum','mint':'missing'})[0],400)
    def test_wrong_origin_blocked(self):self.assertEqual(self.request('/api/start',{},origin=False)[0],403)
    def test_execute_disabled_and_no_path_traversal(self):
        self.assertEqual(self.request('/api/wallet/execute',{'signed_transaction':'x'})[0],400)
        self.assertEqual(self.request('/../.env')[0],404)

if __name__=='__main__':unittest.main()
