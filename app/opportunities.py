"""Bounded scanner memory. Missing observations are censored, never rug labels."""
import json
from store import encode

LABEL_POLICY='observed-barrier-25-12-60s-v1'
FEATURE_KEYS=('age_seconds','trade_count','volume_sol','buy_fraction','pool_sol','momentum','fdv_sol','stage','experimental_score','unique_buyers','buyer_velocity')

class Opportunities:
    def __init__(self,db):
        self.db=db
        db.executescript('''CREATE TABLE IF NOT EXISTS seen_tokens(mint TEXT PRIMARY KEY,first_seen REAL,last_seen REAL,body TEXT);
        CREATE TABLE IF NOT EXISTS opportunities(id INTEGER PRIMARY KEY AUTOINCREMENT,mint TEXT NOT NULL,created REAL NOT NULL,version TEXT NOT NULL,status TEXT NOT NULL,body TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS opportunity_state ON opportunities(status,created);
        CREATE INDEX IF NOT EXISTS opportunity_mint ON opportunities(mint,created);''')
        # We did not observe the path while stopped. Do not backfill labels.
        db.execute("UPDATE opportunities SET status='censored_restart' WHERE status='pending'")
    def seen(self,events):
        for e in events:
            mint=e.get('mint') or e.get('base_mint')
            if not isinstance(mint,str) or len(mint)>64:continue
            now=e['received'];body={k:e.get(k) for k in ('kind','name','symbol','pool','stage')}
            self.db.execute('INSERT INTO seen_tokens VALUES (?,?,?,?) ON CONFLICT(mint) DO UPDATE SET last_seen=excluded.last_seen,body=excluded.body',(mint,now,now,encode(body)))
    def tick(self,contexts,now,version,features,friction,feed_healthy):
        pending=self.db.execute("SELECT * FROM opportunities WHERE status='pending' ORDER BY id LIMIT 512").fetchall()
        for row in pending:
            b=json.loads(row['body']);ctx=contexts.get(row['mint']);status='pending'
            if not feed_healthy:status='censored_feed'
            elif not ctx:status='censored_evicted'
            else:
                samples=sorted(ctx['samples'],key=lambda e:(e['received'],e['slot'],e['event_index']))
                for e in samples:
                    if e['received']<=b['last_received']:continue
                    if e['received']>b['deadline']:break
                    if e['received']-b['last_received']>10:status='censored_gap';break
                    b['last_received']=e['received'];move=e['price']/b['price']-1
                    b['last_move']=move
                    b['best']=max(b['best'],move);b['worst']=min(b['worst'],move)
                    if move>=.25 or move<=-.12:
                        status='target_first' if move>=.25 else 'stop_first'
                        b.update(label=1 if move>=.25 else 0,ended=e['received'],observed_return=move)
                        break
                if status=='pending' and now>=b['deadline']:
                    status='timeout' if b['deadline']-b['last_received']<=10 else 'censored_gap'
                    if status=='timeout':b.update(label=0,ended=b['deadline'],observed_return=b.get('last_move',0.))
                elif status=='pending' and now-b['last_received']>10:status='censored_gap'
            if status!='pending':b.setdefault('ended',now)
            self.db.execute('UPDATE opportunities SET status=?,body=? WHERE id=?',(status,encode(b),row['id']))
        active=self.db.execute("SELECT COUNT(*) FROM opportunities WHERE status='pending'").fetchone()[0]
        for mint,ctx in contexts.items():
            self.db.execute('INSERT OR IGNORE INTO seen_tokens VALUES (?,?,?,?)',(mint,now,now,encode(dict(name=ctx.get('name'),stage=ctx['stage']))))
            # Three spaced observations per retained coin/version, whether traded or skipped.
            prior=self.db.execute('SELECT COUNT(*) n,MAX(created) last FROM opportunities WHERE mint=? AND version=?',(mint,version)).fetchone()
            if prior['n']>=3 or (prior['last'] is not None and now-prior['last']<30) or active>=512:continue
            f=features(ctx,now)
            if not feed_healthy or not ctx.get('pool') or not f.get('price') or not ctx['samples']:continue
            e=ctx['samples'][-1]
            cost=friction(e)
            b=dict(features={k:f.get(k) for k in FEATURE_KEYS},price=f['price'],last_received=now,observed_received=e['received'],deadline=now+60,
                   best=0.,worst=0.,cost_fraction=cost,policy=LABEL_POLICY,name=ctx.get('name'),label=None,
                   wallet_evidence='unavailable',coverage='Observed path only; gaps censor labels')
            self.db.execute('INSERT INTO opportunities(mint,created,version,status,body) VALUES (?,?,?,?,?)',(mint,now,version,'pending',encode(b)));active+=1
    def prune(self,pressure=False):
        self.db.execute('DELETE FROM seen_tokens WHERE mint NOT IN (SELECT mint FROM seen_tokens ORDER BY last_seen DESC LIMIT ?)',(5000 if pressure else 10000,))
        self.db.execute("DELETE FROM opportunities WHERE status<>'pending' AND id NOT IN (SELECT id FROM opportunities ORDER BY id DESC LIMIT ?)",(2000 if pressure else 6000,))
    def status(self):
        groups={r['status']:r['n'] for r in self.db.execute('SELECT status,COUNT(*) n FROM opportunities GROUP BY status')}
        return dict(retained_tokens=self.db.execute('SELECT COUNT(*) FROM seen_tokens').fetchone()[0],frames=sum(groups.values()),
                    labeled=groups.get('target_first',0)+groups.get('stop_first',0),pending=groups.get('pending',0),
                    censored=sum(n for k,n in groups.items() if k.startswith('censored')),timeouts=groups.get('timeout',0),
                    policy=LABEL_POLICY,token_limit=10000,frame_limit=6512)

def postmortem(db,run_id):
    buckets={}
    def add(axis,bucket,pnl):
        key=(axis,bucket);b=buckets.setdefault(key,dict(axis=axis,bucket=bucket,count=0,losses=0,pnl_sol=0.))
        b['count']+=1;b['losses']+=int(pnl<0);b['pnl_sol']+=pnl
    for table in ('trades','writeoffs'):
        for row in db.execute('SELECT body FROM '+table+' ORDER BY id DESC LIMIT 5000'):
            t=json.loads(row['body'])
            if t.get('run_id')!=run_id:continue
            f=t.get('signal_features') or t.get('entry_features',{});pnl=t['pnl_sol']
            add('exit',t.get('exit_reason','Unresolved write-off'),pnl)
            for feature,edges in (('age_seconds',(60,300,1800)),('pool_sol',(10,50,200)),('experimental_score',(50,70,85))):
                value=f.get(feature);bucket='Unknown' if value is None else next(('<'+str(n) for n in edges if value<n),'>='+str(edges[-1]))
                add(feature,bucket,pnl)
            add('holder_concentration','Unknown — not collected',pnl)
            add('participation','Exploration' if t.get('exploration') else 'Rule/model selected',pnl)
    return sorted(buckets.values(),key=lambda b:(b['axis'],b['pnl_sol']))
