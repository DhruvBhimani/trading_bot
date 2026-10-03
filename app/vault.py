"""Opt-in encrypted bot wallets. Explicit bounded sessions; all restart locked."""
from contextlib import contextmanager
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from store import encode
from feeds import ADDRESS

class Vault:
    def __init__(self,bot,wallet):
        self.bot=bot;self.wallet=wallet;self.lock=threading.RLock();self.sessions={};self.next_reconcile=0
        with bot.lock,bot.db:
            bot.db.executescript('''CREATE TABLE IF NOT EXISTS managed_wallets(id TEXT PRIMARY KEY,name TEXT NOT NULL,address TEXT NOT NULL UNIQUE,vault TEXT,created REAL NOT NULL,removed INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS bot_jobs(id TEXT PRIMARY KEY,wallet_id TEXT NOT NULL,created REAL NOT NULL,state TEXT NOT NULL,body TEXT NOT NULL,quote_id TEXT,error TEXT);
            UPDATE bot_jobs SET state='interrupted',error='Restart interrupted this job; check wallet order history before retrying' WHERE state IN ('queued','processing');''')
    def crypto(self,body):
        result=subprocess.run(['node',str(Path(__file__).with_name('vault_crypto.cjs'))],input=encode(body),text=True,capture_output=True,timeout=15)
        if result.returncode:raise ValueError('Vault operation failed. Check passphrase and wallet details.')
        return json.loads(result.stdout)
    def row(self,identifier):
        with self.bot.lock:r=self.bot.db.execute('SELECT * FROM managed_wallets WHERE id=? AND removed=0',(identifier,)).fetchone()
        if not r:raise ValueError('Wallet not found')
        return dict(r)
    def list(self):
        with self.lock,self.bot.lock:
            rows=self.bot.store.rows('SELECT id,name,address,vault IS NOT NULL AS can_sign,created FROM managed_wallets WHERE removed=0')
            for r in rows:
                s=self.sessions.get(r['id']);active=bool(s and s['expires']>time.time())
                r.update(unlocked=active,automatic=bool(active and s['automatic']),expires=s['expires'] if active else None,budget_remaining=round(s['budget']-s['reserved'],4) if active else None)
            jobs=self.bot.store.rows('SELECT id,wallet_id,created,state,quote_id,error FROM bot_jobs ORDER BY created DESC LIMIT 30')
        return dict(wallets=rows,jobs=jobs,live_enabled=self.wallet.enabled)
    def add(self,body):
        name=str(body.get('name','Wallet')).strip()[:80]
        if not name:raise ValueError('Wallet name required')
        kind=body.get('kind','watch');vault=None
        if kind=='watch':
            address=body.get('address')
            if not isinstance(address,str) or not ADDRESS.fullmatch(address):raise ValueError('Invalid public address')
        elif kind=='bot':
            result=self.crypto(dict(action='create',password=body.get('password'),secret=body.get('secret')));address=result['address'];vault=encode(result['vault'])
        else:raise ValueError('Unknown wallet type')
        with self.lock,self.bot.lock,self.bot.db:
            existing=self.bot.db.execute('SELECT id,removed FROM managed_wallets WHERE address=?',(address,)).fetchone()
            if existing and not existing['removed']:raise ValueError('Wallet already added')
            identifier=str(uuid.uuid4())
            if existing:self.bot.db.execute('UPDATE managed_wallets SET address=? WHERE id=?',(address+':removed:'+existing['id'],existing['id']))
            self.bot.db.execute('INSERT INTO managed_wallets VALUES (?,?,?,?,?,0)',(identifier,name,address,vault,time.time()))
        return dict(id=identifier,address=address,can_sign=vault is not None)
    def unlock(self,body):
        r=self.row(body.get('id'))
        if not r['vault']:raise ValueError('Watch-only/Phantom wallets cannot automatically sign')
        self.crypto(dict(action='unlock',address=r['address'],vault=json.loads(r['vault']),password=body.get('password')))
        with self.lock:
            self.row(r['id']);self.sessions[r['id']]=dict(session_id=str(uuid.uuid4()),password=body['password'],automatic=False,expires=time.time()+3600,budget=25.,reserved=0.)
        return self.list()
    def enable(self,body):
        with self.lock:
            s=self.sessions.get(body.get('id'))
            if not s or s['expires']<=time.time():raise ValueError('Unlock the bot wallet first')
            if body.get('enabled') is True:
                if not self.wallet.enabled:raise ValueError('Server real swaps disabled')
                if body.get('acknowledge') is not True:raise ValueError('Explicit automatic-signing acknowledgement required')
                s['automatic']=True
            else:s['automatic']=False
        return self.list()
    def lock_wallet(self,identifier,remove=False):
        with self.lock,self.bot.lock,self.bot.db:
            self.sessions.pop(identifier,None)
            self.bot.db.execute("UPDATE bot_jobs SET state='cancelled',error='Wallet locked or removed' WHERE wallet_id=? AND state='queued'",(identifier,))
            if remove:self.bot.db.execute('UPDATE managed_wallets SET vault=NULL,removed=1 WHERE id=?',(identifier,))
        return self.list()
    def export(self,body):
        r=self.row(body.get('id'))
        if not r['vault']:raise ValueError('No signing key in this wallet')
        return self.crypto(dict(action='export',address=r['address'],vault=json.loads(r['vault']),password=body.get('password')))
    def authorized(self,identifier,expected=None):
        s=self.sessions.get(identifier)
        if not s or not s['automatic'] or s['expires']<=time.time():raise ValueError('Automatic signing is locked, paused or expired')
        if expected is not None and s['session_id']!=expected:raise ValueError('Signing session changed; queue a fresh order')
        return s
    def enqueue(self,body):
        identifier=body.get('id');trade={k:body.get(k) for k in ('input_mint','output_mint','amount','slippage_bps')}
        if not self.wallet.enabled:raise ValueError('Real swaps disabled')
        with self.lock,self.bot.lock,self.bot.db:
            self.row(identifier);session=self.authorized(identifier);trade['_session_id']=session['session_id']
            if self.bot.db.execute("SELECT 1 FROM bot_jobs WHERE wallet_id=? AND state IN ('queued','processing')",(identifier,)).fetchone():raise ValueError('A wallet job is already pending')
            job=str(uuid.uuid4());self.bot.db.execute('INSERT INTO bot_jobs VALUES (?,?,?,?,?,NULL,NULL)',(job,identifier,time.time(),'queued',encode(trade)))
        return dict(id=job,state='queued')
    def reconcile(self):
        if time.monotonic()<self.next_reconcile:return
        self.next_reconcile=time.monotonic()+15
        with self.bot.lock:
            row=self.bot.db.execute("SELECT j.id,j.quote_id FROM bot_jobs j JOIN wallet_orders w ON w.id=j.quote_id WHERE j.state IN ('submitted','unknown','interrupted','stopped') AND w.signature IS NOT NULL ORDER BY j.created LIMIT 1").fetchone()
        if not row:return
        try:
            result=self.wallet.confirm(row['quote_id'])
            with self.bot.lock,self.bot.db:self.bot.db.execute('UPDATE bot_jobs SET state=? WHERE id=?',(result['status'],row['id']))
        except Exception:pass  # Retain outcome and signature; never resubmit.

    def tick(self):
        self.reconcile()
        with self.lock:
            for identifier in list(self.sessions):
                if self.sessions[identifier]['expires']<=time.time():self.sessions.pop(identifier,None)
        with self.bot.lock:r=self.bot.db.execute("SELECT * FROM bot_jobs WHERE state='queued' ORDER BY created LIMIT 1").fetchone()
        if not r:return
        r=dict(r);quote=None;expected=json.loads(r['body']).get('_session_id')
        if not expected:
            with self.bot.lock,self.bot.db:self.bot.db.execute("UPDATE bot_jobs SET state='stopped',error='Legacy order needs a fresh signing session' WHERE id=?",(r['id'],))
            return
        try:
            with self.lock,self.bot.lock,self.bot.db:
                self.authorized(r['wallet_id'],expected);wallet=self.row(r['wallet_id'])
                if self.bot.db.execute("UPDATE bot_jobs SET state='processing' WHERE id=? AND state='queued'",(r['id'],)).rowcount!=1:return
            if time.time()-r['created']>30:raise ValueError('Job expired before execution')
            quote=self.wallet.quote({**json.loads(r['body']),'wallet':wallet['address']})
            with self.lock,self.bot.lock,self.bot.db:
                s=self.authorized(r['wallet_id'],expected)
                if s['reserved']+quote['input_usd']>s['budget']:raise ValueError('Session $25 input budget exhausted')
                s['reserved']+=quote['input_usd'] # Failures remain reserved conservatively.
                self.bot.db.execute('UPDATE bot_jobs SET quote_id=? WHERE id=?',(quote['id'],r['id']))
                signed=self.crypto(dict(action='sign',address=wallet['address'],vault=json.loads(wallet['vault']),password=s['password'],transaction=quote['transaction']))['signed']
            # Validate session once more immediately before submission reservation.
            @contextmanager
            def permit():
                with self.lock:
                    self.authorized(r['wallet_id'],expected)
                    yield
            result=self.wallet.execute({'id':quote['id'],'signed_transaction':signed},permit=permit)
            with self.bot.lock,self.bot.db:self.bot.db.execute('UPDATE bot_jobs SET state=? WHERE id=?',(result['status'],r['id']))
        except Exception as exc:
            # No secret/provider request data in stored errors.
            with self.bot.lock,self.bot.db:self.bot.db.execute("UPDATE bot_jobs SET state='stopped',error=? WHERE id=?",('Execution stopped; inspect linked wallet order before retrying',r['id']))
