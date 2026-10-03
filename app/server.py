"""Local research, live launch discovery and opt-in encrypted bot wallets."""
import argparse
from usd_reference import UsdReference
import json
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from engine import Bot
from wallet import Wallet
from chain import Chain
from discovery import Discovery
from vault import Vault
from portfolio import Portfolio
from market import Market
from live_store import LiveStore,remove_legacy_cache
from live_paper import LivePaper
from paper_quotes import PaperQuotes

ROOT=Path(__file__).resolve().parents[1]


def handler(bot,wallet,chain=None,discovery=None,vault=None,portfolio=None,live_paper=None):
    class Handler(BaseHTTPRequestHandler):
        def send(self,status,body,kind='application/json'):
            payload=json.dumps(body,allow_nan=False).encode() if kind=='application/json' else body
            self.send_response(status);self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(payload)));self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(payload)

        def allowed(self):return self.headers.get('Host') in (f'localhost:{self.server.server_port}',f'127.0.0.1:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed():return self.send(403,{'error':'Local access only'})
            try:
                if self.path=='/api/live-paper' and live_paper:return self.send(200,live_paper.status())
                if self.path=='/api/live-paper/export' and live_paper:return self.send(200,live_paper.export())
                if self.path=='/api/discovery' and discovery:return self.send(200,discovery.status())
                if self.path=='/api/wallets' and vault:return self.send(200,vault.list())
                if self.path=='/api/chain/status' and chain:return self.send(200,chain.status())
                if self.path=='/api/state':return self.send(200,bot.snapshot())
                if self.path=='/api/runs':return self.send(200,bot.runs())
                if self.path=='/api/datasets':return self.send(200,bot.datasets())
                if self.path=='/api/wallet/status':return self.send(200,wallet.status())
                if self.path.startswith('/api/export/'):
                    return self.send(200,bot.export(self.path[len('/api/export/'):]))
                files={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/wallet-bundle.js':('wallet-bundle.js','text/javascript'),'/style.css':('style.css','text/css')}
                if self.path not in files:return self.send(404,{'error':'Not found'})
                name,kind=files[self.path];return self.send(200,(ROOT/'frontend'/name).read_bytes(),kind)
            except ValueError as exc:self.send(400,{'error':str(exc)})
            except Exception:self.send(500,{'error':'Local request failed; no wallet trade was requested'})

        def do_POST(self):
            if not self.allowed() or self.headers.get('Origin')!=f'http://{self.headers.get("Host")}':return self.send(403,{'error':'Same-origin local access required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                maximum=10_000_000 if self.path=='/api/import' else 30000
                if not 0<length<=maximum:raise ValueError('Invalid request size')
                if self.headers.get('Content-Type')!='application/json':raise ValueError('JSON required')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):raise ValueError('Expected an object')
                action=self.path.removeprefix('/api/')
                if action=='live-paper/control' and live_paper:
                    result=live_paper.control(body.get('action'))
                elif action=='live-paper/exit' and live_paper:
                    result=live_paper.request_exit(body)
                elif action=='discovery/clear' and discovery:
                    result=discovery.clear()
                elif action=='discovery/discard' and discovery:
                    result=discovery.discard(body)
                elif action=='discovery/pin' and discovery:
                    result=discovery.pin(body)
                elif action=='market' and discovery and discovery.market:
                    discovery.follow(body.get('mint'));result=discovery.market.read(body.get('mint'),body.get('interval',5))
                elif action=='wallets/add' and vault:result=vault.add(body)
                elif action=='wallets/unlock' and vault:result=vault.unlock(body)
                elif action=='wallets/enable' and vault:result=vault.enable(body)
                elif action=='wallets/lock' and vault:result=vault.lock_wallet(body.get('id'))
                elif action=='wallets/remove' and vault:result=vault.lock_wallet(body.get('id'),remove=True)
                elif action=='wallets/export' and vault:result=vault.export(body)
                elif action=='wallets/queue' and vault:result=vault.enqueue(body)
                elif action=='wallets/portfolio' and portfolio:result=portfolio.read(body.get('id'))
                elif action=='chain/watch'  and chain:result=chain.watch(body)
                elif action=='import':result=bot.import_data(body)
                elif action=='backup':result={'path':bot.backup()}
                elif action=='wallet/quote':result=wallet.quote(body)
                elif action=='wallet/execute':result=wallet.execute(body)
                elif action=='wallet/confirm':result=wallet.confirm(body.get('id'))
                elif action=='wallet/balance':result=wallet.balance(body.get('wallet'))
                elif action in ('start','pause','new','open','rename','step'):result=bot.action(action,body)
                else:return self.send(404,{'error':'Not found'})
                self.send(200,result)
            except (ValueError,TypeError,KeyError) as exc:self.send(400,{'error':str(exc)})
            except Exception:self.send(502,{'error':'Provider or storage request failed. Check order history before retrying a wallet submission.'})

        def log_message(self,*args):pass
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--database',type=Path,default=ROOT/'data/local/paper-bot.sqlite3')
    parser.add_argument('--enable-live-swaps',action='store_true',help='Permit Phantom or explicitly enabled bot-wallet mainnet swaps, capped at $5 each')
    args=parser.parse_args();bot=Bot(args.database);wallet=Wallet(bot,args.enable_live_swaps)
    remove_legacy_cache(bot);live=LiveStore()
    chain=Chain(live,wallet.rpc);discovery=Discovery(live,Market(live,wallet.rpc));vault=Vault(bot,wallet);portfolio=Portfolio(bot,wallet,vault)
    usd=UsdReference()
    live_paper=LivePaper(args.database.parent/'live-paper.sqlite3',discovery,quotes=PaperQuotes(),usd=usd)
    server=ThreadingHTTPServer(('127.0.0.1',args.port),handler(bot,wallet,chain,discovery,vault,portfolio,live_paper));stop=threading.Event()
    def loop():
        while not stop.wait(1):
            try:bot.tick()
            except Exception:
                with bot.lock:
                    bot.state['running']=False;bot.state['status']='error';bot.state['source_error']='Execution stopped after a data/storage error. Inspect before resuming.'
                    try:
                        with bot.db:bot.store.persist(bot.state)
                    except Exception:pass
    def paper_loop():
        while not stop.is_set():
            discovery.changed.wait(.5);discovery.changed.clear()
            if stop.wait(.2):break  # Coalesce bursts; one bounded wake flag, no event queue.
            try:live_paper.tick()
            except Exception:pass  # State records the error and pauses entries.
    paper_worker=threading.Thread(target=paper_loop,daemon=True);paper_worker.start()
    def quote_loop():
        while not stop.wait(3):
            try:live_paper.quote_tick()
            except Exception:pass  # Route checks cannot change paper cash or fills.
    quote_worker=threading.Thread(target=quote_loop,daemon=True);quote_worker.start()
    def collect():
        while not stop.wait(15):
            try:chain.tick();live.prune()
            except Exception:pass  # Individual RPC failures are persisted in feed status.
    def enrich():
        while not stop.is_set():
            discovery.metadata_changed.wait(2);discovery.metadata_changed.clear()
            if stop.wait(.5):break
            try:discovery.maintain();discovery.market.enrich();discovery.changed.set()
            except Exception:discovery.market.metadata_status='Metadata RPC unavailable; retrying after backoff. Some prices/caps may be unavailable.'
    enricher=threading.Thread(target=enrich,daemon=True);enricher.start()
    def names_loop():
        while not stop.wait(5):
            try:live_paper.enrich_names()
            except Exception:pass  # Cosmetic identity lookup cannot delay decision metadata.
    names_worker=threading.Thread(target=names_loop,daemon=True);names_worker.start()
    def learning_loop():
        while not stop.wait(2):
            try:live_paper.learning_tick()
            except Exception:pass  # Research cannot stop the trading engine.
    learning_worker=threading.Thread(target=learning_loop,daemon=True);learning_worker.start()
    def reference_loop():
        while not stop.is_set():
            usd.refresh()
            if stop.wait(30):break
    reference_worker=threading.Thread(target=reference_loop,daemon=True);reference_worker.start()
    def execute_jobs():
        while not stop.wait(1):
            try:vault.tick()
            except Exception:pass
    executor=threading.Thread(target=execute_jobs,daemon=True);executor.start();discovery.start()
    collector=threading.Thread(target=collect,daemon=True);collector.start()
    worker=threading.Thread(target=loop,daemon=True);worker.start()
    print(f'Local desk: http://127.0.0.1:{args.port} | real swaps: {args.enable_live_swaps}',flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();discovery.close();worker.join();collector.join();executor.join();server.server_close();enricher.join();names_worker.join();learning_worker.join();reference_worker.join();paper_worker.join();quote_worker.join();live_paper.close();live.close();bot.close()


if __name__=='__main__':main()
