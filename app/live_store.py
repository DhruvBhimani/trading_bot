"""Bounded session-only market cache. Wallet/paper records live elsewhere."""
import sqlite3
import threading
import time
import os
import subprocess

TABLES=('launch_events','market_trades','market_mints','token_metrics','launch_supply','feature_memory','chain_mentions','chain_transactions','market_risk','migration_events')
MINT_TABLES=TABLES[:6]+('market_risk','migration_events')

class LiveStore:
    def __init__(self):
        self.lock=threading.RLock();self.pins=set();self.protected=set();self.generation=0
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA temp_store=MEMORY')
        self.db.execute('PRAGMA max_page_count=8192')
        self.memory_pressure=False;self.memory_status='Automatic limits active';self.memory_sample={};self.last_memory_sample=0
        self.store=self
    def rows(self,sql,args=()):return [dict(r) for r in self.db.execute(sql,args)]
    def exists(self,table):return self.db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(table,)).fetchone()
    def clear(self):
        with self.lock,self.db:
            self.generation+=1
            keep=tuple(self.pins|self.protected);marks=','.join('?' for _ in keep) or 'NULL'
            for table in MINT_TABLES:
                if self.exists(table):
                    if keep:self.db.execute(f'DELETE FROM {table} WHERE mint NOT IN ({marks})',keep)
                    else:self.db.execute('DELETE FROM '+table)
            for table in ('chain_mentions','chain_transactions'):
                if self.exists(table):self.db.execute('DELETE FROM '+table)
            if self.exists('chain_watches'):self.db.execute('UPDATE chain_watches SET enabled=0,cursor=NULL,before_sig=NULL,head=NULL')
    def discard(self,mint):
        with self.lock,self.db:
            if mint in self.protected:raise ValueError('Coin has an open or pending paper position')
            if mint in self.pins:raise ValueError('Unpin this coin before discarding it')
            for table in MINT_TABLES:
                if self.exists(table):self.db.execute('DELETE FROM '+table+' WHERE mint=?',(mint,))
    def usage(self):
        with self.lock:
            page=self.db.execute('PRAGMA page_size').fetchone()[0]
            allocated=self.db.execute('PRAGMA page_count').fetchone()[0]*page
            free=self.db.execute('PRAGMA freelist_count').fetchone()[0]*page
            return dict(mode='RAM-only SQLite cache',allocated_bytes=allocated,used_bytes=allocated-free,reusable_bytes=free,disk_bytes=0,max_bytes=page*8192,max_tokens=210+len(self.protected),max_trades=12000,unpinned_ttl_seconds=900,pressure=self.memory_pressure,status=self.memory_status,**self.memory_sample)
    def sample_memory(self,worker_pid=None):
        now=time.monotonic()
        if self.last_memory_sample and now-self.last_memory_sample<10:return False
        self.last_memory_sample=now
        def rss(pid):
            if not pid:return None
            try:
                r=subprocess.run(['ps','-o','rss=','-p',str(int(pid))],capture_output=True,text=True,timeout=2)
                return int(r.stdout.strip())*1024 if r.returncode==0 and r.stdout.strip().isdigit() else None
            except (OSError,ValueError,subprocess.TimeoutExpired):return None
        server=rss(os.getpid());worker=rss(worker_pid)
        with self.lock:
            previous=self.memory_pressure
            high=(server is not None and server>256*1048576) or (worker is not None and worker>384*1048576)
            recovered=server is not None and server<192*1048576 and (worker_pid is None or (worker is not None and worker<128*1048576))
            self.memory_pressure=high
            self.memory_status='Trimming cache automatically; scanner remains active' if self.memory_pressure else 'Continuous scan · bounded rotating shortlist'
            self.memory_sample=dict(server_rss_bytes=server,worker_rss_bytes=worker,server_guard_bytes=256*1048576,worker_guard_bytes=384*1048576,sampled=time.time())
            return self.memory_pressure!=previous
    def expire(self):
        with self.lock:
            expired=[r['mint'] for r in self.rows('SELECT mint FROM launch_events WHERE received<?',(time.time()-900,)) if r['mint'] not in self.pins|self.protected]
            for mint in expired:self.discard(mint)
            return expired
    def prune(self):
        with self.lock,self.db:
            # Reserve half the 200 slots for pools so launch bursts do not evict
            # candidates before they accumulate a strategy observation window.
            # launch also removes its metrics/supply, so counters never outlive it.
            if self.exists('launch_events'):
                keep=tuple(self.pins|self.protected);marks=','.join('?' for _ in keep) or 'NULL'
                pool_count=min(100,self.db.execute("SELECT COUNT(*) FROM launch_events WHERE kind='pool'").fetchone()[0])
                retained=f"SELECT rowid FROM (SELECT rowid FROM launch_events WHERE kind='pool' ORDER BY received DESC,rowid DESC LIMIT 100) UNION SELECT rowid FROM (SELECT rowid FROM launch_events WHERE kind<>'pool' ORDER BY received DESC,rowid DESC LIMIT {200-pool_count})"
                protected_clause=f' AND mint NOT IN ({marks})' if keep else ''
                self.db.execute(f'DELETE FROM launch_events WHERE rowid NOT IN ({retained}){protected_clause}',keep)
                for table in MINT_TABLES[1:]:
                    if self.exists(table):self.db.execute(f'DELETE FROM {table} WHERE mint NOT IN (SELECT mint FROM launch_events)')
            page=self.db.execute('PRAGMA page_size').fetchone()[0]
            used=(self.db.execute('PRAGMA page_count').fetchone()[0]-self.db.execute('PRAGMA freelist_count').fetchone()[0])*page
            pressured=used>24*1048576 or self.memory_pressure
            for table,limit in {'market_trades':2000 if pressured else 12000,'feature_memory':0,'chain_transactions':50 if pressured else 200}.items():
                if not self.exists(table):continue
                if table=='market_trades' and self.protected:
                    mints=sorted(self.protected);global_limit=max(0,limit-120*len(mints))
                    retained=['SELECT rowid FROM (SELECT rowid FROM market_trades ORDER BY rowid DESC LIMIT ?)']+['SELECT rowid FROM (SELECT rowid FROM market_trades WHERE mint=? ORDER BY rowid DESC LIMIT 120)' for _ in mints]
                    self.db.execute('DELETE FROM market_trades WHERE rowid NOT IN ('+' UNION '.join(retained)+')',(global_limit,*mints))
                else:self.db.execute(f'DELETE FROM {table} WHERE rowid NOT IN (SELECT rowid FROM {table} ORDER BY rowid DESC LIMIT ?)',(limit,))
            if self.exists('chain_mentions'):self.db.execute('DELETE FROM chain_mentions WHERE signature NOT IN (SELECT signature FROM chain_transactions)')
    def close(self):self.db.close()

def remove_legacy_cache(bot):
    """Delete obsolete live cache only; wallet/paper records and backups survive."""
    with bot.lock:
        existing={r[0] for r in bot.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not existing.intersection(TABLES):return
        with bot.db:
            for table in TABLES:bot.db.execute('DROP TABLE IF EXISTS '+table)
        bot.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        bot.db.execute('VACUUM')
        bot.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
