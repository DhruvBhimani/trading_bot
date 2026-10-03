"""Live launch/pool events shared by the UI and future strategy consumers."""
import json
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from store import encode

class Discovery:
    def __init__(self,bot,market=None):
        self.observations=deque(maxlen=2048);self.observation_drops=0
        self.changed=threading.Event();self.metadata_changed=threading.Event();self.market=market;self.bot=bot;self.process=None;self.worker=None;self.stopping=False;self.state='Starting';self.last_message=None;self.discarded={};self.rejected={};self.scanner={};self.stop_event=threading.Event();self.high_memory_samples=0;self.restarts=0;self.last_worker_sample=None;self.last_prune=0
        with bot.lock,bot.db:
            bot.db.execute('CREATE TABLE IF NOT EXISTS launch_events(signature TEXT NOT NULL,event_index INTEGER NOT NULL,kind TEXT NOT NULL,mint TEXT NOT NULL,slot INTEGER NOT NULL,received REAL NOT NULL,body TEXT NOT NULL,PRIMARY KEY(signature,event_index))')
            bot.db.execute('CREATE TABLE IF NOT EXISTS migration_events(mint TEXT PRIMARY KEY,pool TEXT NOT NULL,received REAL NOT NULL,body TEXT NOT NULL)')
    def command(self,body):
        if self.process and self.process.poll() is None:
            self.process.stdin.write(json.dumps(body)+'\n');self.process.stdin.flush()
    def ingest(self,event):
        with self.bot.lock:
            if event.get('type')=='observation':
                if event.get('generation',0)!=self.bot.generation:return
                if len(self.observations)==self.observations.maxlen:self.observation_drops+=1
                self.observations.append({k:(v[:128] if isinstance(v,str) else v) for k,v in event.items() if k in ('mint','base_mint','kind','received','name','symbol','pool','stage')});return
            if event.get('type')=='status':self.state=event['status'];return
            if event.get('type')=='telemetry':
                if event.get('generation',0)!=self.bot.generation:return
                self.scanner=dict(scanner_counters=event.get('counters',{}),scanner_stages=event.get('stages',{}),worker_memory=event.get('memory',{}),worker_restarts=self.restarts)
                keep=set(event.get('mints',[]))|self.bot.pins|self.bot.protected
                for row in self.bot.store.rows('SELECT mint FROM launch_events'):
                    if row['mint'] not in keep:self.bot.discard(row['mint'])
                return
            if event.get('type')!='event':return
            if event.get('generation',0)!=getattr(self.bot,'generation',0):return
            event={k:v for k,v in event.items() if k!='raw'}
            mint=event.get('mint') or event.get('base_mint')
            if mint in self.discarded:return
            if self.rejected.get(mint,0)>time.time() and mint not in self.bot.pins|self.bot.protected and event.get('kind')!='migration':return
            if event.get('kind')=='migration':
                with self.bot.db:self.bot.db.execute('INSERT OR REPLACE INTO migration_events VALUES (?,?,?,?)',(mint,event['pool'],event['received'],encode(event)))
                existing=self.bot.db.execute('SELECT body FROM launch_events WHERE mint=?',(mint,)).fetchone()
                # Promote a known bonding-curve launch into its observed pool.
                # A different already-mapped pool must not inherit migration proof.
                if existing and json.loads(existing['body']).get('pool'):return
                event={**event,'kind':'pool','base_mint':mint}
            if event.get('kind')=='trade':
                if hasattr(self.bot,'prune') and not self.bot.db.execute('SELECT 1 FROM launch_events WHERE mint=?',(mint,)).fetchone():return
                if self.market:self.market.ingest(event)
            else:
                self.last_message=time.time()
                with self.bot.db:
                    old=self.bot.db.execute('SELECT body FROM launch_events WHERE mint=?',(mint,)).fetchone()
                    if old:
                        previous=json.loads(old['body'])
                        if mint in getattr(self.bot,'protected',set()) and previous.get('pool') and event.get('pool') and previous['pool']!=event['pool']:return
                        if previous['slot']>event['slot']:return
                        for key in ('name','symbol'):
                            if key not in event and key in previous:event[key]=previous[key]
                        self.bot.db.execute('DELETE FROM launch_events WHERE mint=?',(mint,))
                    self.bot.db.execute('INSERT OR IGNORE INTO launch_events VALUES (?,?,?,?,?,?,?)',(event['signature'],event['event_index'],event['kind'],mint,event['slot'],event['received'],encode(event)))
                if self.market:self.market.launch(event)
                self.metadata_changed.set()
            self.changed.set()
            if hasattr(self.bot,'prune') and (event.get('kind')!='trade' or time.monotonic()-self.last_prune>.25):
                self.bot.prune();self.last_prune=time.monotonic()
    def discard(self,body):
        mint=body.get('mint')
        from feeds import ADDRESS
        if not isinstance(mint,str) or not ADDRESS.fullmatch(mint):raise ValueError('Invalid mint')
        with self.bot.lock:
            self.bot.discard(mint)
            self.discarded[mint]=True
            while len(self.discarded)>1000:self.discarded.pop(next(iter(self.discarded)))
            if self.market:self.market.metadata_retry.pop(mint,None)
            self.command(dict(type='discard',mints=[mint]))
            return self.status()
    def maintain(self):
        self.bot.sample_memory(self.process.pid if self.process and self.process.poll() is None else None)
        rss=self.bot.memory_sample.get('worker_rss_bytes')
        stamp=self.bot.memory_sample.get('sampled')
        if stamp!=self.last_worker_sample:
            self.high_memory_samples=self.high_memory_samples+1 if rss is not None and rss>384*1048576 else 0
            self.last_worker_sample=stamp
        if self.high_memory_samples>=3 and self.process and self.process.poll() is None:
            self.high_memory_samples=0;self.state='Recycling feed worker; paper engine remains active';self.process.terminate()
        with self.bot.lock:
            expired=self.bot.expire();self.bot.prune()
            if expired:self.command(dict(type='discard',mints=expired))
            if self.market:
                for mint in expired:self.market.metadata_retry.pop(mint,None)
    def reject(self,mints):
        with self.bot.lock:
            now=time.time();self.rejected={m:t for m,t in self.rejected.items() if t>now};removed=[]
            for mint in mints[:80]:
                if mint in self.bot.pins|self.bot.protected:continue
                self.bot.discard(mint);self.rejected[mint]=now+60;removed.append(mint)
                if self.market:self.market.metadata_retry.pop(mint,None)
            while len(self.rejected)>256:self.rejected.pop(next(iter(self.rejected)))
            if removed:self.command(dict(type='reject',mints=removed))
    def pin(self,body):
        mint=body.get('mint');enabled=body.get('pinned')
        if type(enabled) is not bool:raise ValueError('Boolean pinned required')
        with self.bot.lock:
            if not isinstance(mint,str) or not self.bot.db.execute('SELECT 1 FROM launch_events WHERE mint=?',(mint,)).fetchone():raise ValueError('Token expired; load a fresh discovery')
            if enabled:
                if mint not in self.bot.pins and len(self.bot.pins)>=10:raise ValueError('Maximum ten pinned coins')
                self.bot.pins.add(mint)
            else:self.bot.pins.discard(mint)
            self.command(dict(type='pins',mints=sorted(self.bot.pins)))
            return self.status()
    def clear(self):
        with self.bot.lock:
            self.bot.clear();self.last_message=None
            if self.market:self.market.metadata_retry={k:v for k,v in self.market.metadata_retry.items() if k in self.bot.pins|self.bot.protected}
            self.command(dict(type='reset',generation=self.bot.generation,mints=sorted(self.bot.pins)))
            return self.status()
    def status(self):
        with self.bot.lock:
            rows=self.bot.store.rows('SELECT body FROM launch_events ORDER BY received DESC,rowid DESC LIMIT 214')
            events=[json.loads(r['body']) for r in rows]
            metrics=self.market.metrics([e.get('mint') or e.get('base_mint') for e in events]) if self.market else {}
            return dict(status=self.state,last_event=self.last_message,count=len(events),events=events,metrics=metrics,pins=sorted(getattr(self.bot,'pins',set())),protected=sorted(getattr(self.bot,'protected',set())),generation=getattr(self.bot,'generation',0),storage=self.bot.usage() if hasattr(self.bot,'usage') else {},metadata_status=getattr(self.market,'metadata_status',''),coverage='Confirmed Pump.fun and observed PumpSwap SOL pools. Session RAM only: 64 pool + 16 near-migration candidates + up to 10 pinned coins + open/pending paper positions; 12,000 recent trades. Clear preserves pins and paper positions. All live data and pins disappear on server exit. No downtime backfill; values show observation age.')
    def follow(self,mint):
        from feeds import ADDRESS
        if not isinstance(mint,str) or not ADDRESS.fullmatch(mint):raise ValueError('Invalid mint')
        with self.bot.lock:
            if hasattr(self.bot,'prune') and not self.bot.db.execute('SELECT 1 FROM launch_events WHERE mint=?',(mint,)).fetchone():raise ValueError('Token expired or cleared')
            self.command(dict(type='track',mints=[mint]))

    def start(self):
        def run():
            while not self.stopping:
                try:
                    self.process=subprocess.Popen(['node','--max-old-space-size=96',str(Path(__file__).with_name('discovery_stream.cjs'))],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
                    with self.bot.lock:
                        protected=sorted(self.bot.protected);pins=sorted(self.bot.pins);pools=[]
                        for row in self.bot.store.rows("SELECT body FROM launch_events WHERE kind='pool'"):
                            event=json.loads(row['body'])
                            if (event.get('mint') or event.get('base_mint')) in self.bot.protected|self.bot.pins:pools.append(dict(pool=event['pool'],base_mint=event.get('mint') or event['base_mint'],quote_mint=event.get('quote_mint')))
                        self.command(dict(type='reset',generation=self.bot.generation,mints=pins))
                        self.command(dict(type='protected',mints=protected,pools=pools))
                    if self.stopping:self.process.terminate()
                    for line in self.process.stdout:
                        if len(line)>50000:continue
                        try:self.ingest(json.loads(line))
                        except Exception:self.state='Event storage/decoding error; feed incomplete'
                    self.process.wait()
                except Exception:self.state='Feed worker unavailable; retrying automatically'
                finally:
                    if self.process:
                        if self.process.poll() is None:
                            self.process.terminate()
                            try:self.process.wait(timeout=3)
                            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
                        for pipe in (self.process.stdin,self.process.stdout):
                            if pipe:
                                try:pipe.close()
                                except OSError:pass
                if not self.stopping:
                    self.restarts+=1;self.state='Reconnecting feed worker; observations during gap may be missing'
                    self.stop_event.wait(min(10,1+self.restarts))
            self.state='Stopped'
        self.worker=threading.Thread(target=run,daemon=True);self.worker.start()
    def close(self):
        self.stopping=True;self.stop_event.set()
        if self.process and self.process.poll() is None:self.process.terminate()
        if self.worker:self.worker.join(timeout=5)
