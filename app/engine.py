"""Paper execution engine for synthetic and imported observations."""
import copy
import hashlib
import json
import math
import threading
import time
import uuid
from pathlib import Path
from feeds import demo_batch,validate,WATCHLIST
from store import Store,encode

from strategy import VERSION, entry_signal, exit_reason
DEFAULTS=dict(starting_cash=10000.,size=150.,fee_bps=30.,slippage_bps=50.,min_liquidity=25000.,
              max_positions=2,max_pool_fraction=.01,order_ttl=30.,max_age=30.,lookback_seconds=15.,
              momentum=.02,stop_loss=.12,take_profit=.25,max_hold_seconds=180.)


def uid():return str(uuid.uuid4())


def fresh(name='Demo session',mode='demo',config=None,dataset=None,cutoff=None):
    cfg={**DEFAULTS,**(config or {})}
    if set(cfg)!=set(DEFAULTS):raise ValueError('Unknown setting')
    for key,value in cfg.items():
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError('Invalid setting: '+key)
    if not 10<=cfg['size']<=1000 or cfg['starting_cash']<=0 or not 0<=cfg['fee_bps']<1000 or not 0<=cfg['slippage_bps']<1000:raise ValueError('Invalid cash or costs')
    if not 1<=cfg['max_positions']<=10 or int(cfg['max_positions'])!=cfg['max_positions']:raise ValueError('Invalid position limit')
    if any(cfg[k]<=0 for k in ('min_liquidity','order_ttl','max_age','lookback_seconds','max_hold_seconds')):raise ValueError('Invalid risk limit')
    if any(not 0<cfg[k]<1 for k in ('max_pool_fraction','momentum','stop_loss','take_profit')):raise ValueError('Invalid ratio')
    if mode not in ('demo','replay'):raise ValueError('Unknown source mode')
    if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('Run name must be 1–80 characters')
    identifier=uid()
    return dict(id=identifier,name=name.strip(),created=time.time(),mode=mode,dataset_id=dataset or identifier,
                cutoff=cutoff,strategy_version=VERSION,config=cfg,running=False,status='paused',tick=0,
                timestamp=None,cash=cfg['starting_cash'],positions={},pending={},last={},trail={},used=[],
                realized_pnl=0.,peak_equity=cfg['starting_cash'],max_drawdown=0.,source_error=None,completed=False)


def equity(s,now=None):
    c=s['config'];now=s['timestamp'] if now is None else now
    total=s['cash']
    for symbol,p in s['positions'].items():
        row=s['last'].get(symbol)
        if row and now is not None and now-row['timestamp']<=c['max_age'] and (row['liquidity'] or 0)>0:
            total+=p['quantity']*row['price']*(1-c['slippage_bps']/10000)*(1-c['fee_bps']/10000)
    return total


class Bot:
    def __init__(self,path):
        self.lock=threading.RLock();self.store=Store(path);self.db=self.store.db
        self.generation=0;self.next_poll=0.;self.failures=0
        self.import_legacy()
        row=self.db.execute("SELECT value FROM metadata WHERE key='active_run'").fetchone()
        with self.db:
            if row:self.state=self.store.load(row['value'])
            else:
                self.state=fresh();self.store.dataset(self.state['id'],'Demo session','synthetic')
            self.state['running']=False;self.state['status']='paused'
            self.store.persist(self.state)
            self.event('Account restored; execution paused.' if row else 'Local paper workspace ready.')

    def import_legacy(self):
        # Original demo table is retained byte-for-byte; legacy runs are view-only.
        exists=self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='demo_sessions'").fetchone()
        if not exists:return
        with self.db:
            for row in self.db.execute('SELECT id,state_json FROM demo_sessions').fetchall():
                if self.db.execute('SELECT 1 FROM runs WHERE id=?',(row['id'],)).fetchone():continue
                old=json.loads(row['state_json']);s=fresh('Earlier demo '+row['id'][:8])
                s.update(id=row['id'],dataset_id=row['id'],strategy_version='legacy-demo-v1',completed=True,
                         cash=old['cash'],tick=old['tick'],timestamp=1704067200+old['tick']*5,
                         realized_pnl=sum(t['pnl'] for t in old['trades']),max_drawdown=old['max_drawdown'])
                self.store.dataset(s['id'],s['name'],'synthetic_legacy');self.store.persist(s)
                for h in old['history']:
                    rows=demo_batch(h['tick'])
                    for r in rows:r['price']=h['prices'][r['symbol']]
                    self.store.add_observations(s['id'],rows)
                    s['last']={r['symbol']:r for r in rows}
                for symbol,p in old['positions'].items():
                    s['positions'][symbol]=dict(quantity=p['quantity'],cost=p['cost'],entry=p['entry'],entry_time=1704067200+p['entry_tick']*5,entry_reason='Legacy demo',token=None,pool=None)
                for t in old['trades']:
                    order_id=uid();ts=1704067200+t['exit_tick']*5
                    details=dict(pnl=t['pnl'],reason=t['reason'],entry=t['entry'],entry_time=1704067200+t['entry_tick']*5,cost=t['cost'])
                    self.db.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)',(order_id,s['id'],t['symbol'],'SELL','filled',ts,ts,t['reason'],'{}'))
                    self.db.execute('INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?)',(uid(),order_id,s['id'],ts,t['symbol'],'SELL',t['exit'],t['quantity'],t['cost']+t['pnl'],0,encode(details)))
                self.store.persist(s)

    def event(self,message,kind='info'):
        s=self.state
        self.db.execute('INSERT INTO events VALUES (?,?,?,?,?)',(uid(),s['id'],s['timestamp'] or time.time(),kind,message))

    def signal(self,row,action,reason):
        self.db.execute('INSERT INTO signals VALUES (?,?,?,?,?,?,?)',(uid(),self.state['id'],row['timestamp'],row['symbol'],action,reason,encode(row)))

    def order(self,row,side,reason):
        order=dict(id=uid(),symbol=row['symbol'],side=side,status='pending',created=row['timestamp'],reason=reason,updated=row['timestamp'])
        self.state['pending'][row['symbol']]=order
        self.db.execute('INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?)',(order['id'],self.state['id'],row['symbol'],side,'pending',row['timestamp'],row['timestamp'],reason,encode(order)))
        self.signal(row,side,reason);self.event(row['symbol']+': '+side+' queued · '+reason)

    def update_order(self,order,status,reason=None):
        order['status']=status;order['updated']=self.state['timestamp']
        if reason:order['reason']=reason
        self.db.execute('UPDATE orders SET status=?,updated=?,reason=?,details=? WHERE id=?',(status,order['updated'],order['reason'],encode(order),order['id']))

    def apply(self,rows,raw=None,record=True):
        """Atomic observations + signals + fills + account checkpoint. No partial tick commits."""
        rows=[validate(r) for r in rows]
        if not rows:raise ValueError('Empty observation batch')
        timestamps={r['timestamp'] for r in rows}
        if len(timestamps)!=1 or len({r['symbol'] for r in rows})!=len(rows):raise ValueError('Batch must have one timestamp and unique symbols')
        ts=rows[0]['timestamp'];s=self.state;c=s['config']
        if s['timestamp'] is not None and ts<=s['timestamp']:return False
        # Identity cannot drift within a dataset/run, including after an import.
        for r in rows:
            old=s['last'].get(r['symbol'])
            if old and any(old.get(k)!=r.get(k) for k in ('token','pool')):raise ValueError('Token/pool identity changed')
        before=copy.deepcopy(s)
        try:
            with self.db:
                if record:self.store.add_observations(s['dataset_id'],rows,raw)
                s['timestamp']=ts;s['tick']+=1;s['source_error']=None
                for r in rows:s['last'][r['symbol']]=r
                fee=c['fee_bps']/10000;slip=c['slippage_bps']/10000
                for r in rows:
                    symbol=r['symbol'];o=s['pending'].get(symbol)
                    if not o:continue
                    liq=r['liquidity'] or 0
                    if ts-o['created']>c['order_ttl']:
                        self.update_order(o,'expired','Order TTL elapsed');del s['pending'][symbol]
                        self.event(symbol+': pending order expired.','warning');continue
                    if o['side']=='BUY':
                        reason=('Liquidity below entry minimum' if liq<c['min_liquidity'] else
                                'Allocation too large for pool' if c['size']>liq*c['max_pool_fraction'] else
                                'Account limit' if len(s['positions'])>=c['max_positions'] or s['cash']<c['size'] else None)
                        if reason:
                            self.update_order(o,'rejected',reason);del s['pending'][symbol];self.event(symbol+': buy rejected · '+reason,'warning');continue
                        fill=r['price']*(1+slip);cost=c['size'];qty=cost/(fill*(1+fee));charge=qty*fill*fee
                        s['cash']-=cost
                        s['positions'][symbol]=dict(quantity=qty,cost=cost,entry=fill,entry_time=ts,entry_reason=o['reason'],token=r['token'],pool=r['pool'])
                        delta=-cost;details=dict(reason=o['reason'],pnl=None)
                        s['used'].append(symbol)
                    else:
                        position=s['positions'].get(symbol)
                        if not position:
                            self.update_order(o,'cancelled','Position no longer open');del s['pending'][symbol];continue
                        if liq<=0 or position['quantity']*r['price']>liq*c['max_pool_fraction']:
                            if o['status']!='blocked':self.event(symbol+': exit blocked by liquidity.','warning')
                            self.update_order(o,'blocked','Insufficient exit liquidity');continue
                        fill=r['price']*(1-slip);qty=position['quantity'];charge=qty*fill*fee;delta=qty*fill-charge
                        pnl=delta-position['cost'];s['cash']+=delta;s['realized_pnl']+=pnl
                        details=dict(**position,pnl=pnl,reason=o['reason']);del s['positions'][symbol]
                    self.db.execute('INSERT INTO fills VALUES (?,?,?,?,?,?,?,?,?,?,?)',(uid(),o['id'],s['id'],ts,symbol,o['side'],fill,qty,delta,charge,encode(details)))
                    self.update_order(o,'filled');del s['pending'][symbol]
                    self.event(f'{symbol}: {o["side"]} paper fill at ${fill:.8f}',o['side'].lower())
                for r in rows:
                    symbol=r['symbol'];trail=s['trail'].setdefault(symbol,[])
                    trail.append([ts,r['price']]);s['trail'][symbol]=trail=[v for v in trail if ts-v[0]<=max(120,c['lookback_seconds']*2)]
                    if symbol in s['pending']:continue
                    p=s['positions'].get(symbol)
                    if p:
                        reason=exit_reason(r,p,c)
                        if reason:self.order(r,'SELL',reason)
                    elif symbol not in s['used']:
                        prior=[v for v in trail if v[0]<=ts-c['lookback_seconds']]
                        if not prior or ts-prior[-1][0]>c['lookback_seconds']+c['max_age']:continue
                        if not entry_signal(r['price'],prior[-1][1],c):continue
                        reason=('Liquidity missing/below minimum' if (r['liquidity'] or 0)<c['min_liquidity'] else
                                'Position limit' if len(s['positions'])+sum(o['side']=='BUY' for o in s['pending'].values())>=c['max_positions'] else None)
                        if reason:self.signal(r,'REJECT',reason)
                        else:self.order(r,'BUY','Placeholder momentum with liquidity filter')
                value=equity(s);s['peak_equity']=max(s['peak_equity'],value);s['max_drawdown']=max(s['max_drawdown'],1-value/s['peak_equity'])
                self.db.execute('INSERT INTO equity_curve VALUES (?,?,?,?)',(s['id'],ts,value,s['cash']))
                self.store.persist(s)
        except Exception:
            self.state=before;raise
        return True

    def finish(self):
        self.state.update(running=False,completed=True,status='complete')
        with self.db:
            self.event('Replay complete. Remaining positions are marked, not forcibly sold.')
            self.store.persist(self.state)

    def tick(self,force=False):
        with self.lock:
            s=self.state
            if not s['running'] and not force:return
            if s['completed']:return
            mode=s['mode'];generation=self.generation;identifier=s['id']
            if mode=='demo':
                self.apply(demo_batch(s['tick']+1))
                if s['tick']>=360:self.finish()
                return
            else:
                row=self.db.execute('SELECT MIN(timestamp) t FROM observations WHERE dataset_id=? AND timestamp>? AND id<=?',(s['dataset_id'],s['timestamp'] or 0,s['cutoff'])).fetchone()
                if row['t'] is None:self.finish();return
                rows=self.store.rows('SELECT timestamp,symbol,price,liquidity,token,pool FROM observations WHERE dataset_id=? AND timestamp=? AND id<=? ORDER BY symbol',(s['dataset_id'],row['t'],s['cutoff']))
                self.apply(rows,record=False);return

    def action(self,action,body):
        with self.lock:
            s=self.state
            if action=='pause':
                s['running']=False;s['status']='paused';self.generation+=1
            elif action=='start':
                if s['completed']:raise ValueError('Run complete. Create a new run or replay.')
                if s['strategy_version']!=VERSION:raise ValueError('Strategy changed; create a new run.')
                s['running']=True;s['status']='running'
            elif action=='step':
                if s['running']:raise ValueError('Step is for paused demo/replay only')
                self.tick(force=True)
            elif action in ('new','open'):
                if s['running']:raise ValueError('Pause before switching runs')
                self.generation+=1
                if action=='open':
                    self.state=self.store.load(body.get('id'));self.state['running']=False;self.state['status']='paused'
                else:
                    mode=body.get('mode','demo');dataset=body.get('dataset_id');cutoff=None
                    if mode=='replay':
                        row=self.db.execute('SELECT MAX(id) n FROM observations WHERE dataset_id=?',(dataset,)).fetchone()
                        if not row['n']:raise ValueError('Dataset has no observations')
                        cutoff=row['n']
                    elif dataset:raise ValueError('Dataset only applies to replay')
                    self.state=fresh(body.get('name','Paper run'),mode,body.get('config'),dataset,cutoff)
                    with self.db:
                        if mode!='replay':self.store.dataset(self.state['dataset_id'],self.state['name'],'synthetic')
                self.next_poll=0
            elif action=='rename':
                name=body.get('name','')
                if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise ValueError('Run name must be 1–80 characters')
                s['name']=name.strip()
            elif action=='settings':
                raise ValueError('Settings are immutable per run. Create a new run with the desired allocation.')
            else:raise ValueError('Unknown action')
            with self.db:self.store.persist(self.state)
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            s=copy.deepcopy(self.state)
            now=s['timestamp']
            s['equity']=equity(s,now);s['stale']=bool(s['timestamp'] and now-s['timestamp']>s['config']['max_age'])
            s['prices']={k:v['price'] for k,v in s['last'].items()};s['liquidity']={k:v['liquidity'] for k,v in s['last'].items()}
            s['events']=self.store.rows('SELECT timestamp,kind,message FROM events WHERE run_id=? ORDER BY rowid DESC LIMIT 100',(s['id'],))
            s['fills']=self.store.rows('SELECT * FROM fills WHERE run_id=? ORDER BY timestamp,id',(s['id'],))
            for f in s['fills']:f['details']=json.loads(f['details'])
            s['orders']=self.store.rows('SELECT id,symbol,side,status,reason,created,updated FROM orders WHERE run_id=? ORDER BY created DESC LIMIT 100',(s['id'],))
            args=[s['dataset_id'],s['timestamp'] or 0];cut=''
            if s['cutoff']:cut=' AND id<=?';args.append(s['cutoff'])
            s['observations']=self.store.rows('SELECT timestamp,symbol,price,liquidity,token,pool FROM observations WHERE dataset_id=? AND timestamp<=?'+cut+' ORDER BY timestamp DESC,id DESC LIMIT 1500',args)[::-1]
            s['live_execution_enabled']=False
            s['dataset_source']=self.db.execute('SELECT source FROM datasets WHERE id=?',(s['dataset_id'],)).fetchone()['source']
            return s

    def runs(self):
        with self.lock:
            rows=self.store.rows('SELECT id,name,created,config,state FROM runs ORDER BY created DESC LIMIT 100')
            out=[]
            for row in rows:
                s=json.loads(row.pop('state'));c=json.loads(row.pop('config'))
                out.append(dict(**row,mode=s['mode'],dataset_id=s['dataset_id'],cutoff=s['cutoff'],tick=s['tick'],
                                equity=equity(s),realized_pnl=s['realized_pnl'],max_drawdown=s['max_drawdown'],
                                strategy=s['strategy_version'],config=c,completed=s['completed']))
            return out

    def datasets(self):
        with self.lock:return self.store.rows('SELECT d.*,COUNT(o.id) observations,MIN(o.timestamp) first,MAX(o.timestamp) last FROM datasets d LEFT JOIN observations o ON d.id=o.dataset_id GROUP BY d.id ORDER BY d.created DESC')

    def import_data(self,body):
        if body.get('schema_version')!='observations-v1':raise ValueError('Expected observations-v1 JSON')
        rows=body.get('observations')
        if not isinstance(rows,list) or not 1<=len(rows)<=50000:raise ValueError('Import 1–50,000 observations')
        rows=[validate(r) for r in rows];rows.sort(key=lambda r:(r['timestamp'],r['symbol']))
        seen=set();identities={}
        for r in rows:
            key=(r['timestamp'],r['symbol'])
            if key in seen:raise ValueError('Duplicate timestamp/symbol')
            seen.add(key);identity=(r['token'],r['pool'])
            if r['symbol'] in identities and identities[r['symbol']]!=identity:raise ValueError('Symbol maps to different assets')
            identities[r['symbol']]=identity
        name=body.get('name','Imported observations')
        if not isinstance(name,str) or not 1<=len(name)<=80:raise ValueError('Invalid dataset name')
        with self.lock,self.db:
            identifier=uid();self.store.dataset(identifier,name,'imported')
            self.store.add_observations(identifier,rows)
        return dict(dataset_id=identifier,observations=len(rows))

    def export(self,identifier):
        with self.lock:
            s=self.store.load(identifier)
            args=[s['dataset_id']];condition='dataset_id=?'
            if s['cutoff']:condition+=' AND id<=?';args.append(s['cutoff'])
            count=self.db.execute('SELECT COUNT(*) FROM observations WHERE '+condition,args).fetchone()[0]
            if count>50000:raise ValueError('Export exceeds 50,000 observations; use database backup')
            return dict(schema_version='observations-v1',name=s['name'],run=s,
                        observations=self.store.rows('SELECT timestamp,symbol,price,liquidity,token,pool FROM observations WHERE '+condition+' ORDER BY timestamp,symbol',args),
                        fills=self.store.rows('SELECT * FROM fills WHERE run_id=?',(identifier,)),
                        signals=self.store.rows('SELECT * FROM signals WHERE run_id=?',(identifier,)),
                        orders=self.store.rows('SELECT * FROM orders WHERE run_id=?',(identifier,)))

    def backup(self):
        with self.lock:return self.store.backup()

    def close(self):
        with self.lock:self.db.close()
