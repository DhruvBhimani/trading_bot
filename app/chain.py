"""Finalized transaction collection (session-only in the live desk). No synthetic market fallback or trades."""
import json
import time
from feeds import ADDRESS
from store import encode

SCHEMA='''
CREATE TABLE IF NOT EXISTS chain_watches(address TEXT PRIMARY KEY,enabled INTEGER NOT NULL,cursor TEXT,before_sig TEXT,head TEXT,status TEXT NOT NULL,updated REAL NOT NULL);
CREATE TABLE IF NOT EXISTS chain_transactions(signature TEXT PRIMARY KEY,slot INTEGER NOT NULL,block_time INTEGER,raw TEXT,attempts INTEGER NOT NULL DEFAULT 0,retry_at REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS chain_mentions(address TEXT NOT NULL,signature TEXT NOT NULL,PRIMARY KEY(address,signature));
'''

class Chain:
    def __init__(self,bot,rpc):
        self.bot=bot;self.rpc=rpc
        with bot.lock,bot.db:bot.db.executescript(SCHEMA)

    def watch(self,body):
        address=body.get('address');enabled=body.get('enabled',True)
        if not isinstance(address,str) or not ADDRESS.fullmatch(address) or type(enabled) is not bool:raise ValueError('Valid public pool address and boolean enabled required')
        with self.bot.lock,self.bot.db:
            if enabled and not self.bot.db.execute('SELECT 1 FROM chain_watches WHERE address=?',(address,)).fetchone() and self.bot.db.execute('SELECT COUNT(*) FROM chain_watches').fetchone()[0]>=5:raise ValueError('Maximum five watched addresses')
            self.bot.db.execute("INSERT INTO chain_watches VALUES (?,?,NULL,NULL,NULL,'Waiting for RPC',?) ON CONFLICT(address) DO UPDATE SET enabled=excluded.enabled",(address,int(enabled),time.time()))
        return self.status()

    def status(self):
        with self.bot.lock:
            watches=self.bot.store.rows('SELECT * FROM chain_watches')
            events=self.bot.store.rows('SELECT t.signature,t.slot,t.block_time,t.raw IS NOT NULL AS downloaded,t.attempts,m.address FROM chain_transactions t JOIN chain_mentions m USING(signature) ORDER BY t.slot DESC,t.signature DESC LIMIT 40')
            pending=self.bot.db.execute('SELECT COUNT(*) FROM chain_transactions WHERE raw IS NULL').fetchone()[0]
        return dict(watches=watches,events=events,pending=pending,transport='Finalized RPC transaction polling · 15 seconds',note='Transactions mentioning an address are not necessarily swaps. Initial coverage starts with the newest 20 transactions. No price candles are inferred.')

    def tick(self):
        generation=getattr(self.bot,'generation',0)
        with self.bot.lock:watches=self.bot.store.rows('SELECT * FROM chain_watches WHERE enabled=1')
        for w in watches:
            if generation!=getattr(self.bot,'generation',0):return
            try:self.scan(w)
            except Exception:
                with self.bot.lock,self.bot.db:self.bot.db.execute("UPDATE chain_watches SET status='RPC unavailable; retrying without advancing cursor',updated=? WHERE address=?",(time.time(),w['address']))
        # Bounded requests avoid flooding public RPC; live-session queue is ephemeral.
        with self.bot.lock:pending=self.bot.store.rows('SELECT signature,attempts FROM chain_transactions WHERE raw IS NULL AND retry_at<=? ORDER BY retry_at,slot LIMIT 2',(time.time(),))
        for row in pending:
            if generation!=getattr(self.bot,'generation',0):return
            try:
                tx=self.rpc('getTransaction',[row['signature'],{'encoding':'jsonParsed','commitment':'finalized','maxSupportedTransactionVersion':0}])
                if tx is None:raise ValueError('Receipt not yet available')
                if row['signature'] not in tx['transaction']['signatures']:raise ValueError('Receipt signature mismatch')
                with self.bot.lock,self.bot.db:self.bot.db.execute('UPDATE chain_transactions SET raw=? WHERE signature=?',(encode(tx),row['signature']))
            except Exception:
                with self.bot.lock,self.bot.db:self.bot.db.execute('UPDATE chain_transactions SET attempts=attempts+1,retry_at=? WHERE signature=?',(time.time()+min(900,15*2**min(row['attempts'],6)),row['signature']))

    def scan(self,w):
        generation=getattr(self.bot,'generation',0)
        config={'commitment':'finalized','limit':20}
        if w['before_sig']:config['before']=w['before_sig']
        rows=self.rpc('getSignaturesForAddress',[w['address'],config])
        if not isinstance(rows,list):raise ValueError('Invalid signature response')
        head=w['head'] or (rows[0]['signature'] if rows else None)
        found=any(r['signature']==w['cursor'] for r in rows)
        selected=[]
        for r in rows:
            if r['signature']==w['cursor']:break
            selected.append(r)
        initial=w['cursor'] is None
        done=initial or found
        gap=not initial and not found and len(rows)<20
        with self.bot.lock,self.bot.db:
            if generation!=getattr(self.bot,'generation',0):return
            for r in selected:
                self.bot.db.execute('INSERT OR IGNORE INTO chain_transactions(signature,slot,block_time) VALUES (?,?,?)',(r['signature'],r['slot'],r.get('blockTime')))
                self.bot.db.execute('INSERT OR IGNORE INTO chain_mentions VALUES (?,?)',(w['address'],r['signature']))
            if done:
                self.bot.db.execute("UPDATE chain_watches SET cursor=?,before_sig=NULL,head=NULL,status=?,updated=? WHERE address=?",(head or w['cursor'],'Following finalized transactions',time.time(),w['address']))
            elif gap:
                # Do not silently claim complete recovery if the provider cannot reach the checkpoint.
                self.bot.db.execute("UPDATE chain_watches SET status='History gap: checkpoint unavailable from RPC',updated=? WHERE address=?",(time.time(),w['address']))
            else:
                self.bot.db.execute("UPDATE chain_watches SET before_sig=?,head=?,status='Catching up to saved checkpoint',updated=? WHERE address=?",(rows[-1]['signature'],head,time.time(),w['address']))
