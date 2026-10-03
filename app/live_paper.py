"""Live rule evaluation and hypothetical SOL-pool fills; never signs transactions."""
import copy
import hashlib
import json
import math
import sqlite3
import threading
import time
import uuid
from decimal import Decimal
from pathlib import Path
from store import encode
from paper_learning import PaperLearning
from ml_research import ModelResearch
from ml_model import predict as model_predict, validate as validate_model,PROB_POLICY,probability
from opportunities import Opportunities,postmortem

ROOT=Path(__file__).resolve().parents[1]
STRATEGIES={'momentum':'Momentum baseline v1','recovery':'Verified migration recovery v1'}
SCHEMA='''CREATE TABLE IF NOT EXISTS versions(version TEXT PRIMARY KEY,created REAL NOT NULL,config TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,created REAL NOT NULL,version TEXT NOT NULL,summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS decisions(id INTEGER PRIMARY KEY,mint TEXT NOT NULL,strategy TEXT NOT NULL,created REAL NOT NULL,state TEXT NOT NULL,reason TEXT NOT NULL,version TEXT NOT NULL,features TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades(id INTEGER PRIMARY KEY,strategy TEXT NOT NULL,mint TEXT NOT NULL,created REAL NOT NULL,pnl REAL NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS labels(decision_id INTEGER NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,horizon INTEGER NOT NULL,due REAL NOT NULL,observed REAL,status TEXT NOT NULL,body TEXT,PRIMARY KEY(decision_id,horizon));
CREATE TABLE IF NOT EXISTS quote_checks(id INTEGER PRIMARY KEY,run_id TEXT NOT NULL,mint TEXT NOT NULL,strategy TEXT NOT NULL,created REAL NOT NULL,body TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS label_due ON labels(status,due);'''

class LivePaper:
    def __init__(self,path,discovery,config=None,clock=time.time,quotes=None,usd=None):
        self.lock=threading.RLock();self.discovery=discovery;self.clock=clock;self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),check_same_thread=False);self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA auto_vacuum=INCREMENTAL');self.db.execute('PRAGMA journal_mode=DELETE');self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('PRAGMA max_page_count=12800');self.db.executescript(SCHEMA);self.learner=PaperLearning(self.db);self.last_learning=None;self.learning_error=None
        self.models=ModelResearch(self.db)
        self.opportunities=Opportunities(self.db)
        self.db.execute('CREATE TABLE IF NOT EXISTS writeoffs(id INTEGER PRIMARY KEY AUTOINCREMENT,created REAL NOT NULL,body TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS ml_comparisons(id TEXT PRIMARY KEY,created REAL NOT NULL,body TEXT NOT NULL)')
        cfg=json.loads((ROOT/'config/live-paper.json').read_text());cfg.update(config or {})
        self.new_config=cfg
        self.quotes=quotes;self.quote_attempts={};self.usd=usd;self.last_pruned=None
        for key,value in cfg.items():
            if key!='version' and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):raise ValueError('Invalid paper setting: '+key)
        if cfg['max_positions'] not in (1,2) or cfg['size_sol']<=0 or cfg['starting_cash_sol']<=cfg['size_sol'] or cfg['execution_delay_seconds']<=0:raise ValueError('Invalid paper risk limits')
        if any(not 0<cfg[k]<1 for k in ('momentum','recovery_dip','recovery_rebound','max_pool_fraction','max_adverse_move','stop_loss','take_profit','trailing_stop')):raise ValueError('Invalid paper ratio')
        if cfg['slippage_bps']>=2000 or cfg['fee_bps_floor']>=2000:raise ValueError('Invalid paper cost setting')
        if cfg.get('exploration_fraction',0)>.1:raise ValueError('Paper exploration must be at most 10%')
        row=self.db.execute('SELECT body FROM checkpoint WHERE id=1').fetchone()
        self.s=json.loads(row['body']) if row else self.fresh(cfg)
        # Explicit v2 policy migration keeps balances/history and records the old
        # entry version. Old comparison arms finish exits but admit no new buys.
        if row and self.s['config'].get('paper_policy_revision',0)<2:
            old_version=self.s['version']
            with self.db:self.save()
            for a in self.s['accounts'].values():
                for p in a['positions'].values():p.setdefault('entry_version',old_version)
                a['pending']={m:o for m,o in a['pending'].items() if o['side']=='SELL' and o['reason']!='Maximum holding time'}
            self.s['config'].update({k:cfg[k] for k in ('version','paper_policy_revision','size_usd','max_hold_seconds','unresolved_after_seconds','exploration_fraction')})
            self.s['version']=self.fresh(self.s['config'])['version']
            if self.s.get('ml_trial'):self.s['ml_trial']['entries_until']=self.clock()
        self.s['running']=False;self.s['status']='Paused entries';self.s['error']=None
        self.restore_context();self.sync_protection()
        with self.db:self.save()
    def fresh(self,cfg):
        fingerprint=hashlib.sha256(encode(cfg).encode()).hexdigest()[:12]
        return dict(id=str(uuid.uuid4()),created=self.clock(),config=cfg,version=cfg['version']+'-'+fingerprint,running=False,status='Paused entries',error=None,last_tick=None,watch={},accounts={key:dict(cash=cfg['starting_cash_sol'],realized_pnl=0.,positions={},pending={},closed=0,peak_equity=cfg['starting_cash_sol'],drawdown=0.,day=int(self.clock()//86400),day_pnl=0.,cooldowns={}) for key in STRATEGIES})
    def save(self):
        self.db.execute('INSERT OR IGNORE INTO versions VALUES (?,?,?)',(self.s['version'],self.s['created'],encode(self.s['config'])))
        self.db.execute('INSERT OR REPLACE INTO checkpoint VALUES (1,?)',(encode(self.s),))
    def restore_context(self):
        live=self.discovery.bot
        with live.lock,live.db:
            for a in self.s['accounts'].values():
                # Pending buys are cancelled on restart; exits retain their reason.
                a['pending']={m:o for m,o in a['pending'].items() if o['side']=='SELL' and m in a['positions']}
                for mint,p in a['positions'].items():
                    context=p['context'];body=dict(type='event',kind='pool',base_mint=mint,quote_mint=context['quote_mint'],pool=context['pool'],name=context['name'],slot=0,received=self.clock(),signature='restored-'+mint,event_index=0)
                    live.db.execute('INSERT OR IGNORE INTO launch_events VALUES (?,?,?,?,?,?,?)',(body['signature'],0,'pool',mint,0,body['received'],encode(body)))
                    live.db.execute('INSERT OR IGNORE INTO market_mints VALUES (?,?)',(mint,context['decimals']))
    def sync_protection(self):
        live=self.discovery.bot
        wanted={m for a in self.s['accounts'].values() for group in ('positions','pending') for m in a[group]}
        with live.lock:
            changed=wanted!=live.protected;live.protected=wanted
            if changed:
                pools=[dict(pool=p['context']['pool'],base_mint=m,quote_mint=p['context']['quote_mint']) for a in self.s['accounts'].values() for m,p in a['positions'].items()]
                try:self.discovery.command(dict(type='protected',mints=sorted(wanted),pools=pools))
                except (BrokenPipeError,OSError):self.s['tracking_error']='Discovery worker unavailable; restart to restore tracking'
    def usd_value(self,value):
        rate=self.usd.rate() if self.usd else None
        return value*rate if value is not None and rate is not None else None
    def entry_size(self):
        c=self.s['config']
        if c.get('size_usd',0):
            rate=self.usd.rate() if self.usd else None
            if rate is None or not math.isfinite(rate) or rate<=0:raise ValueError('Waiting for fresh USD reference for $50 sizing')
            return c['size_usd']/rate
        return c['size_sol']
    def latest(self,context,now):
        rows=context.get('samples',[]) if context else []
        if not rows:return None
        e=rows[-1]
        if not 0<=now-e['received']<=self.s['config']['max_data_age_seconds']:return None
        return e
    def features(self,ctx,now):
        c=self.s['config'];rows=[e for e in ctx['samples'] if now-c['window_seconds']<=e['received']<=now];last=self.latest(ctx,now)
        score=(25*min(1,max(0,rows[-1]['price']/rows[0]['price']-1)/.10)+25*sum(e['buy'] for e in rows)/len(rows)+25*min(1,sum(e['volume_sol'] for e in rows)/2)+25*min(1,last['pool_sol']/50)) if rows and last else None
        buyers=[e for e in rows if e['buy']];known=bool(rows) and all(e.get('wallet') for e in buyers)
        return dict(unique_buyers=len({e['wallet'] for e in buyers}) if known else None,buyer_velocity=len({e['wallet'] for e in buyers if e['received']>=now-10})/10 if known else None,cost_fraction=self.observation_cost(last) if last else None,fdv_sol=last['price']*ctx['supply_tokens'] if last and ctx.get('supply_tokens') is not None else None,supply_tokens=ctx.get('supply_tokens'),supply_observed=ctx.get('supply_observed'),run_id=self.s['id'],experimental_score=round(score,2) if score is not None else None,stage=ctx['stage'],pool=ctx['pool'],price=last['price'] if last else None,age_seconds=ctx['age'],trade_count=len(rows),volume_sol=sum(e['volume_sol'] for e in rows),buy_fraction=sum(e['buy'] for e in rows)/len(rows) if rows else None,pool_sol=last['pool_sol'] if last else None,momentum=rows[-1]['price']/rows[0]['price']-1 if len(rows)>=2 else None,risk=ctx['risk'],coverage='Partial confirmed observations; missing events not reconstructed',holders='unknown',bundlers='unknown',global_fees='unknown')
    def screen(self,ctx,now,amount=None):
        c=self.s['config'];f=self.features(ctx,now);e=self.latest(ctx,now)
        if not ctx['pool']:return 'Waiting for observed PumpSwap pool',f
        if ctx['quote_mint']!='So11111111111111111111111111111111111111112':return 'Unsupported/non-SOL pool',f
        if 'decimals' not in ctx:return 'Waiting for verified mint decimals',f
        if not ctx['samples']:return 'Waiting for first mapped SOL-pool trade',f
        if not e:return 'Mapped SOL-pool trades are stale',f
        risk=ctx['risk']
        if not risk or not risk['authority_known']:return 'Mint/freeze authority evidence missing',f
        if now-risk['observed']>300:return 'Authority evidence expired',f
        if risk['mint_authority'] or risk['freeze_authority']:return 'Mint or freeze authority active',f
        if ctx['age']<c['min_age_seconds']:return 'Observing minimum token age',f
        if e['pool_sol']<c['min_pool_sol'] or e['pool_tokens']<=0:return 'Insufficient observed pool reserves',f
        try:amount=self.entry_size() if amount is None else amount
        except ValueError as exc:return str(exc),f
        if amount>e['pool_sol']*c['max_pool_fraction']:return 'Allocation too large for observed pool',f
        if f['trade_count']<c['min_window_trades'] or f['volume_sol']<c['min_window_volume_sol']:return 'Insufficient recent trading activity',f
        if f['buy_fraction']<c['min_buy_fraction']:return 'Insufficient recent buy participation',f
        return None,f
    def signal_reason(self,key,ctx,f):
        trial=self.s.get('ml_trial')
        if key.startswith('ml_'):
            if not trial:return 'No frozen ML comparison'
            if self.clock()>=trial['entries_until']:return 'Comparison entries finished; managing remaining exits'
            if ctx['mint'] in trial['excluded_mints']:return 'Training/validation coin excluded from forward comparison'
            if key=='ml_candidate':
                try:prediction=model_predict(trial['model'],f)
                except (KeyError,TypeError,ValueError,IndexError):return 'ML model unavailable; candidate entries skipped'
                if not math.isfinite(prediction):return 'ML prediction unavailable; candidate entries skipped'
                f['ml_expected_return']=prediction;f['ml_version']=trial['id']
                if trial['model']['policy']==PROB_POLICY:f['target_probability']=probability(trial['model'],f)
                if prediction<trial['threshold']:
                    draw=int(hashlib.sha256((trial['id']+':'+ctx['mint']).encode()).hexdigest()[:8],16)/2**32
                    a=self.s['accounts'][key]
                    exploring=any(m!=ctx['mint'] and p.get('exploration') for group in ('positions','pending') for m,p in a[group].items())
                    if draw>=self.s['config'].get('exploration_fraction',0) or exploring:return 'ML filter skipped this signal'
                    f['exploration']=True  # Deterministic per coin/model; never reroll on each tick.
            key=trial['strategy']
        if key=='momentum':return None if f['momentum'] is not None and f['momentum']>=self.s['config']['momentum'] else 'Momentum threshold not met'
        if ctx['stage']!='verified_migrated':return 'Verified migration evidence missing'
        prices=[e['price'] for e in ctx['samples'] if e['received']>=ctx['migration_received']]
        peak=max(prices) if prices else 0.;trough=min(prices) if prices else 0.
        peak_index=prices.index(peak) if prices else 0;trough_index=prices.index(trough) if prices else 0
        return None if len(prices)>=3 and peak_index<trough_index<len(prices)-1 and trough<=peak*(1-self.s['config']['recovery_dip']) and prices[-1]>=trough*(1+self.s['config']['recovery_rebound']) else 'Waiting for post-migration dip and recovery'
    def decision(self,key,mint,state,reason,f,now):
        watch=self.s['watch'].setdefault(key,{})
        if watch.get(mint,{}).get('reason')==reason and watch[mint]['state']==state:return
        watch[mint]=dict(state=state,reason=reason,updated=now)
        cur=self.db.execute('INSERT INTO decisions(mint,strategy,created,state,reason,version,features) VALUES (?,?,?,?,?,?,?)',(mint,key,now,state,reason,self.s['version'],encode(f)))
        if f.get('price'):
            for horizon in (30,120,600):self.db.execute('INSERT INTO labels VALUES (?,?,?,NULL,?,NULL)',(cur.lastrowid,horizon,now+horizon,'pending'))
    def estimate(self,e,side,amount):
        c=self.s['config'];fee=max(c['fee_bps_floor']/10000,e['fee_fraction']);slip=c['slippage_bps']/10000
        if not 0<=fee<.2 or e['pool_sol']<=0 or e['pool_tokens']<=0:raise ValueError('Pool/fee estimate unavailable')
        net=amount*(1-fee)
        output=(e['pool_tokens']*net/(e['pool_sol']+net) if side=='BUY' else e['pool_sol']*net/(e['pool_tokens']+net))*(1-slip)
        if side=='SELL':output=max(0,output-c['network_fee_sol'])
        return output
    def fill_costs(self,e,side,amount):
        c=self.s['config'];spot=e['pool_sol']/e['pool_tokens'];fee=max(c['fee_bps_floor']/10000,e['fee_fraction']);net=amount*(1-fee)
        if side=='BUY':ideal=amount/spot;gross=e['pool_tokens']*amount/(e['pool_sol']+amount);paid=e['pool_tokens']*net/(e['pool_sol']+net);unit=spot
        else:ideal=amount*spot;gross=e['pool_sol']*amount/(e['pool_tokens']+amount);paid=e['pool_sol']*net/(e['pool_tokens']+net);unit=1.
        result=dict(impact_sol=max(0,(ideal-gross)*unit),pool_fee_sol=max(0,(gross-paid)*unit),slippage_sol=paid*c['slippage_bps']/10000*unit,network_sol=c['network_fee_sol'])
        if side=='SELL':result['network_sol']=min(result['network_sol'],paid*(1-c['slippage_bps']/10000))
        result['total_sol']=sum(result.values());return result
    def observe_position(self,p,ctx,now):
        e=self.latest(ctx,now)
        if not e:return
        if ctx.get('name'):p['context'].update(name=ctx['name'],symbol=ctx.get('symbol',''))
        p['last_observation']=dict(fdv_sol=e['price']*ctx['supply_tokens'] if ctx.get('supply_tokens') is not None else None,received=e['received'],price=e['price'],pool_sol=e['pool_sol'],pool_tokens=e['pool_tokens'],value_sol=self.mark(p,ctx,now))
    def exit_reason(self,p,e,now):
        c=self.s['config']
        if c['max_hold_seconds']>0 and now-p['entry_time']>=c['max_hold_seconds']:return 'Maximum holding time'
        if not e:return None
        mark=self.estimate(e,'SELL',p['quantity']);move=mark/p['cost']-1;p['peak_value']=max(p['peak_value'],mark);p['mfe']=max(p['mfe'],move);p['mae']=min(p['mae'],move)
        if move<=-c['stop_loss']:return 'Stop loss'
        if move>=c['take_profit']:return 'Take profit'
        if mark<=p['peak_value']*(1-c['trailing_stop']) and p['peak_value']>p['cost']:return 'Trailing stop'
        return None
    def queue(self,a,key,mint,side,reason,f,ctx,now):
        e=self.latest(ctx,now);amount=self.entry_size() if side=='BUY' else a['positions'][mint]['quantity']
        try:expected=self.estimate(e,side,amount) if e else None
        except ValueError:expected=None
        anchor=a.setdefault('entry_signals',{}).setdefault(mint,dict(price=e['price'],fdv_sol=f.get('fdv_sol'),fdv_usd=self.usd_value(f.get('fdv_sol')),created=now,received=e['received'])) if side=='BUY' and e else {}
        a['pending'][mint]=dict(signal_features=copy.deepcopy(f),signal_price=anchor.get('price'),signal_fdv_sol=anchor.get('fdv_sol'),signal_fdv_usd=anchor.get('fdv_usd'),signal_created=anchor.get('created'),signal_received=anchor.get('received'),maximum_entry_price=anchor['price']*1.10 if anchor else None,execution_policy='signal-ceiling-v1-10pct',side=side,reason=reason,created=now,attempt=now,signature=e['signature'] if e else None,event_index=e['event_index'] if e else None,minimum=expected*(1-self.s['config']['max_adverse_move']) if expected else None)
        self.decision(key,mint,'pending_'+side.lower(),reason,f,now)
        a['pending'][mint].update(amount=amount,size_usd=self.s['config'].get('size_usd',0) if side=='BUY' else None,exploration=bool(f.get('exploration')))
    def process_orders(self,a,key,contexts,now):
        c=self.s['config']
        for mint,o in list(a['pending'].items()):
            ctx=contexts.get(mint);e=self.latest(ctx,now);f=self.features(ctx,now) if ctx else dict(price=None)
            if o['side']=='BUY' and now-o['created']>c['order_ttl_seconds']:
                del a['pending'][mint];a.setdefault('cooldowns',{})[mint]=now+10;self.decision(key,mint,'expired','Entry order expired',f,now);continue
            if now-o['attempt']<c['execution_delay_seconds']:continue
            if not e or e['received']<o['attempt']+c['execution_delay_seconds'] or (e['signature']==o['signature'] and e['event_index']==o['event_index']):
                if o['side']=='SELL':self.decision(key,mint,'exit_blocked','Exit waiting for fresh subsequent trade',f,now)
                continue
            amount=o.get('amount',c['size_sol']) if o['side']=='BUY' else a['positions'][mint]['quantity']
            try:
                if o['side']=='BUY':
                    reason,f=self.screen(ctx,now,amount)
                    if reason:raise ValueError(reason)
                    reason=self.signal_reason(key,ctx,f)
                    if reason:raise ValueError('Signal no longer qualifies: '+reason)
                    if a['day_pnl']<=-c['daily_loss_limit_sol']:raise ValueError('Daily realized-loss limit')
                    if len(a['positions'])>=c['max_positions'] or a['cash']<amount+c['network_fee_sol']:raise ValueError('Account limit')
                elif amount>e['pool_tokens']*.05:raise ValueError('Exit size too large for observed pool')
                output=self.estimate(e,o['side'],amount)
                if o['side']=='BUY' and o.get('maximum_entry_price') is not None and (e['price']>o['maximum_entry_price'] or amount/output>o['maximum_entry_price'] or (o.get('signal_fdv_sol') is not None and f.get('fdv_sol') is not None and f['fdv_sol']>o['signal_fdv_sol']*1.10) or (o.get('signal_fdv_usd') is not None and self.usd_value(f.get('fdv_sol')) is not None and self.usd_value(f['fdv_sol'])>o['signal_fdv_usd']*1.10)):raise ValueError('Skipped: entry exceeded signal ceiling (+10%)')
                if o['minimum'] is not None and output<o['minimum']:raise ValueError('Adverse move exceeded order limit')
            except ValueError as exc:
                if o['side']=='BUY':del a['pending'][mint];a.setdefault('cooldowns',{})[mint]=now+10;self.decision(key,mint,'rejected',str(exc),f,now)
                else:
                    o['blocked_attempts']=o.get('blocked_attempts',0)+1
                    self.decision(key,mint,'exit_blocked',str(exc),f,now);o.update(attempt=now,signature=e['signature'],event_index=e['event_index'],minimum=self.estimate(e,'SELL',amount)*(1-c['max_adverse_move']) if e['pool_sol']>0 and e['pool_tokens']>0 and e['fee_fraction']<.2 else None)
                continue
            if o['side']=='BUY':
                cost=amount+c['network_fee_sol'];a['cash']-=cost
                a['positions'][mint]=dict(quantity=output,cost=cost,entry_time=now,entry_price=amount/output,entry_fdv_sol=f.get('fdv_sol'),entry_fdv_usd=self.usd_value(f.get('fdv_sol')),entry_fx=self.usd.rate() if self.usd else None,entry_wait_before_queue_seconds=max(0,o['created']-o.get('signal_created',o['created'])),entry_event_to_evaluation_seconds=max(0,now-e['received']),signal_fdv_sol=o.get('signal_fdv_sol'),signal_to_entry_seconds=now-o.get('signal_created',o['created']),entry_move_pct=(e['price']/o['signal_price']-1)*100 if o.get('signal_price') else None,execution_policy=o.get('execution_policy'),entry_reason=o['reason'],entry_features=f,entry_costs=self.fill_costs(e,'BUY',amount),entry_delay_seconds=now-o['created'],peak_value=cost,mfe=0.,mae=0.,context={k:ctx.get(k) for k in ('mint','name','symbol','pool','quote_mint','decimals')})
                self.observe_position(a['positions'][mint],ctx,now)
                a['positions'][mint]['signal_features']=o.get('signal_features')
                a['positions'][mint].update(entry_version=self.s['version'],allocation_sol=amount,allocation_usd=o.get('size_usd'),exploration=o.get('exploration',False))
                if o.get('last_quote'):a['positions'][mint]['entry_quote']=o['last_quote']
                self.decision(key,mint,'position','Simulated buy on subsequent trade',f,now)
            else:
                p=a['positions'].pop(mint);a.setdefault('cooldowns',{})[mint]=now+300;pnl=output-p['cost'];a['cash']+=output;a['realized_pnl']+=pnl;a['day_pnl']+=pnl;a['closed']+=1
                record=dict(mint=mint,name=ctx.get('name') or p['context']['name'],pool=p['context']['pool'],entry_time=p['entry_time'],exit_time=now,cost_sol=p['cost'],proceeds_sol=output,pnl_sol=pnl,entry_reason=p['entry_reason'],exit_reason=o['reason'],quantity=p['quantity'],mfe=p['mfe'],mae=p['mae'],entry_features=p['entry_features'],exit_features=f,version=self.s['version'],model='Constant-product reserve approximation; observed fees/floor + slippage + network cost; not an executable quote')
                record.update(entry_wait_before_queue_seconds=p.get('entry_wait_before_queue_seconds'),entry_event_to_evaluation_seconds=p.get('entry_event_to_evaluation_seconds'),entry_fdv_usd=p.get('entry_fdv_usd'),exit_fdv_usd=self.usd_value(f.get('fdv_sol')),pnl_usd=self.usd_value(pnl),exit_fx=self.usd.rate() if self.usd else None,signal_fdv_sol=p.get('signal_fdv_sol'),signal_to_entry_seconds=p.get('signal_to_entry_seconds'),entry_move_pct=p.get('entry_move_pct'),execution_policy=p.get('execution_policy'),symbol=ctx.get('symbol') or p['context'].get('symbol',''),entry_fdv_sol=p.get('entry_fdv_sol'),exit_fdv_sol=f.get('fdv_sol'),entry_price_sol=p.get('entry_price'),exit_price_sol=output/p['quantity'],run_id=self.s['id'],holding_seconds=now-p['entry_time'],entry_delay_seconds=p.get('entry_delay_seconds'),exit_delay_seconds=now-o['created'],entry_costs=p.get('entry_costs'),exit_costs=self.fill_costs(e,'SELL',amount),blocked_exit_attempts=o.get('blocked_attempts',0),last_quote=p.get('last_quote'),entry_quote=p.get('entry_quote'))
                record['signal_features']=p.get('signal_features')
                record.update(version=p.get('entry_version',self.s['version']),allocation_sol=p.get('allocation_sol'),allocation_usd=p.get('allocation_usd'),exploration=p.get('exploration',False))
                if key.startswith('ml_'):record['ml_comparison']=self.s['ml_trial']['id']
                self.db.execute('INSERT INTO trades(strategy,mint,created,pnl,body) VALUES (?,?,?,?,?)',(key,mint,now,pnl,encode(record)))
                self.decision(key,mint,'closed',o['reason'],f,now)
            del a['pending'][mint]
    def feed_healthy(self,contexts,now):
        return str(getattr(self.discovery,'state','')).startswith('Live') and any(self.latest(ctx,now) for ctx in contexts.values())
    def observation_cost(self,e):
        try:
            amount=self.entry_size();quantity=self.estimate(e,'BUY',amount)
            return max(0,1-self.estimate(e,'SELL',quantity)/(amount+self.s['config']['network_fee_sol']))
        except (ValueError,ZeroDivisionError):return None
    def write_off(self,key,mint,now,reason):
        a=self.s['accounts'][key];p=a['positions'].pop(mint);a['pending'].pop(mint,None)
        # Capital was deducted at entry. No sale and no cash is credited here.
        a['impairment_pnl']=a.get('impairment_pnl',0)-p['cost'];a['writeoffs']=a.get('writeoffs',0)+1;a['day_pnl']-=p['cost']
        a.setdefault('cooldowns',{})[mint]=now+3600
        record=dict(mint=mint,name=p['context'].get('name'),symbol=p['context'].get('symbol'),strategy=key,run_id=self.s['id'],
                    version=p.get('entry_version',self.s['version']),entry_time=p['entry_time'],exit_time=None,retired_time=now,
                    exit_reason=reason,settlement='unresolved_paper_writeoff',rug_label='unknown',sale_executed=False,
                    retained_quantity=p['quantity'],cost_sol=p['cost'],pnl_sol=-p['cost'],pnl_usd=self.usd_value(-p['cost']),
                    entry_fdv_usd=p.get('entry_fdv_usd'),entry_features=p['entry_features'],signal_features=p.get('signal_features'),
                    exploration=p.get('exploration',False),ml_comparison=self.s.get('ml_trial',{}).get('id') if key.startswith('ml_') else None)
        self.db.execute('INSERT INTO writeoffs(created,body) VALUES (?,?)',(now,encode(record)))
    def retire_unresolved(self,key,a,contexts,now):
        limit=self.s['config'].get('unresolved_after_seconds',180)
        healthy=self.feed_healthy(contexts,now)
        for mint,p in list(a['positions'].items()):
            if self.latest(contexts.get(mint),now) or not healthy:
                p.pop('unresolved_since',None);continue
            if self.s['last_tick'] is None or now-self.s['last_tick']>5:p.pop('unresolved_since',None)
            p.setdefault('unresolved_since',now)
            if limit and now-p['unresolved_since']>=limit:self.write_off(key,mint,now,'No fresh token trades during healthy feed; unresolved paper write-off')
    def tick(self,now=None):
        now=self.clock() if now is None else now
        with self.lock:
            if self.s['last_tick'] is not None and now<=self.s['last_tick']:return
            contexts=self.discovery.market.paper_snapshot(now,self.s['config']['window_seconds']);before=copy.deepcopy(self.s)
            try:
                with self.db:
                    if self.last_pruned is None or now-self.last_pruned>=5:
                        self.prune();self.last_pruned=now
                    with self.discovery.bot.lock:
                        events=list(getattr(self.discovery,'observations',[]))
                        if hasattr(self.discovery,'observations'):self.discovery.observations.clear()
                    self.db.execute('SAVEPOINT opportunity_capture')
                    try:
                        self.opportunities.seen(events)
                        self.opportunities.tick(contexts,now,self.s['version'],self.features,self.observation_cost,self.feed_healthy(contexts,now))
                        self.s.pop('observation_error',None)
                    except Exception as exc:
                        self.db.execute('ROLLBACK TO opportunity_capture')
                        self.s['observation_error']='Observation recording failed ('+type(exc).__name__+'); paper trading continues, retrying next update.'
                        self.s['observation_drops']=self.s.get('observation_drops',0)+len(events)
                    finally:self.db.execute('RELEASE opportunity_capture')
                    for key,a in self.s['accounts'].items():
                        if a['day']!=int(now//86400):a['day']=int(now//86400);a['day_pnl']=0.
                        self.process_orders(a,key,contexts,now)
                        self.retire_unresolved(key,a,contexts,now)
                        for mint,p in list(a['positions'].items()):
                            self.observe_position(p,contexts.get(mint),now)
                            if mint in a['pending']:continue
                            ctx=contexts.get(mint);e=self.latest(ctx,now)
                            try:reason=self.exit_reason(p,e,now)
                            except ValueError:reason='Pool/fee estimate unavailable'
                            if reason:self.queue(a,key,mint,'SELL',reason,self.features(ctx,now) if ctx else dict(price=None),ctx,now)
                        if self.s['running']:
                            for mint,ctx in sorted(contexts.items(),key=lambda item:self.features(item[1],now).get('experimental_score') or 0,reverse=True):
                                if mint in a['positions'] or mint in a['pending'] or a.setdefault('cooldowns',{}).get(mint,0)>now:continue
                                reason,f=self.screen(ctx,now)
                                if reason:a.setdefault('entry_signals',{}).pop(mint,None);self.decision(key,mint,'rejected' if reason in ('Mint or freeze authority active','Unsupported/non-SOL pool') else 'watching',reason,f,now);continue
                                reason=self.signal_reason(key,ctx,f)
                                if reason:a.setdefault('entry_signals',{}).pop(mint,None);self.decision(key,mint,'watching',reason,f,now);continue
                                e=self.latest(ctx,now)
                                a.setdefault('entry_signals',{}).setdefault(mint,dict(price=e['price'],fdv_sol=f.get('fdv_sol'),fdv_usd=self.usd_value(f.get('fdv_sol')),created=now,received=e['received']))
                                c=self.s['config']
                                if len(a['positions'])+len(a['pending'])>=c['max_positions'] or a['cash']<self.entry_size()+c['network_fee_sol'] or a['day_pnl']<=-c['daily_loss_limit_sol']:
                                    self.decision(key,mint,'eligible','Signal eligible; account/risk limit',f,now);continue
                                base=self.s['ml_trial']['strategy'] if key.startswith('ml_') else key
                                self.queue(a,key,mint,'BUY','Paper exploration — model skipped, risk rules passed' if f.get('exploration') else ('Post-migration recovery' if base=='recovery' else 'Recent momentum + participation'),f,ctx,now)
                        a['entry_signals']={m:v for m,v in a.setdefault('entry_signals',{}).items() if m in contexts or m in a['positions'] or m in a['pending']}
                        a['cooldowns']={m:t for m,t in a.setdefault('cooldowns',{}).items() if m in contexts and t>now}
                        for mint in list(self.s['watch'].get(key,{})):
                            if mint not in contexts and mint not in a['positions'] and mint not in a['pending']:del self.s['watch'][key][mint]
                        value=a['cash']+sum(self.mark(p,contexts.get(m),now) for m,p in a['positions'].items());a['peak_equity']=max(a['peak_equity'],value);a['drawdown']=max(a['drawdown'],1-value/a['peak_equity'])
                    self.labels(contexts,now);self.s['last_tick']=now;self.save()
                self.sync_protection()
                rejected=[]
                if self.s['running']:
                    for mint,ctx in contexts.items():
                        reason,_=self.screen(ctx,now)
                        if reason in ('Mint or freeze authority active','Unsupported/non-SOL pool','Insufficient observed pool reserves','Allocation too large for observed pool') or (ctx['age']>60 and reason in ('Waiting for verified mint decimals','Waiting for first mapped SOL-pool trade','Mapped SOL-pool trades are stale')):rejected.append(mint)
                if rejected:self.discovery.reject(rejected)
            except Exception as exc:
                self.s=before;self.s['running']=False;self.s['error']='Paper evaluation stopped: '+type(exc).__name__;self.s['status']='Error / entries paused'
                try:
                    with self.db:self.save()
                except sqlite3.Error:pass
                self.sync_protection();raise
    def mark(self,p,ctx,now):
        e=self.latest(ctx,now)
        if not e or p['quantity']>e['pool_tokens']*.05:return 0.
        try:return self.estimate(e,'SELL',p['quantity'])
        except ValueError:return 0.
    def position_view(self,m,p,a,ctx,now):
        last=p.get('last_observation');e=self.latest(ctx,now);stale=e is None
        feed=str(getattr(self.discovery,'state','')).lower()
        if not stale:health='fresh_observation' if e['pool_sol']>0 and e['pool_tokens']>0 else 'observed_reserves_unusable'
        elif any(word in feed for word in ('disconnect','unavailable','stopped','error','backlog')):health='feed_gap'
        else:health='no_recent_trade_or_coverage_gap'
        q=p.get('last_quote');q=copy.deepcopy(q) if q else None
        if q:q['age_seconds']=max(0,now-q['checked']);q['fresh']=q['age_seconds']<=15
        return dict(entry_fdv_usd=p.get('entry_fdv_usd'),current_fdv_usd=self.usd_value(e['price']*ctx['supply_tokens']) if e and ctx.get('supply_tokens') is not None else None,pnl_usd=self.usd_value(self.mark(p,ctx,now)-p['cost']) if not stale else None,pnl_pct=(self.mark(p,ctx,now)/p['cost']-1)*100 if not stale else None,exit_plan=dict(stop_pct=self.s['config']['stop_loss']*100,target_pct=self.s['config']['take_profit']*100,trail_pct=self.s['config']['trailing_stop']*100,remaining_seconds=max(0,self.s['config']['max_hold_seconds']-(now-p['entry_time'])) if self.s['config']['max_hold_seconds']>0 else None),signal_to_entry_seconds=p.get('signal_to_entry_seconds'),entry_move_pct=p.get('entry_move_pct'),mint=m,name=(ctx or {}).get('name') or p['context']['name'],symbol=(ctx or {}).get('symbol') or p['context'].get('symbol',''),entry_fdv_sol=p.get('entry_fdv_sol'),current_fdv_sol=e['price']*ctx['supply_tokens'] if e and ctx.get('supply_tokens') is not None else None,last_known_fdv_sol=last.get('fdv_sol') if last else None,entry_price_sol=p.get('entry_price'),current_price_sol=e['price'] if e else None,pool=p['context']['pool'],cost_sol=p['cost'],mark_sol=self.mark(p,ctx,now),entry_reason=p['entry_reason'],entry_time=p['entry_time'],holding_seconds=max(0,now-p['entry_time']),status=a['pending'].get(m,{}).get('reason','Open'),stale=stale,data_health=health,last_known_mark_sol=last.get('value_sol') if last else None,last_observation_age_seconds=max(0,now-last['received']) if last else None,last_quote=q,entry_costs=p.get('entry_costs'),blocked_exit_attempts=a['pending'].get(m,{}).get('blocked_attempts',0))
    def quote_tick(self):
        if not self.quotes:return
        with self.lock:
            now=self.clock();contexts=self.discovery.market.paper_snapshot(now,self.s['config']['window_seconds']);targets=[]
            for key,a in self.s['accounts'].items():
                for mint,p in a['positions'].items():
                    targets.append((key,mint,'SELL',p['context'],p['quantity'],p['entry_time']))
                    if now-p['entry_time']<60 and not p.get('entry_quote'):targets.append((key,mint,'BUY',p['context'],p.get('allocation_sol',p['cost']-self.s['config']['network_fee_sol']),p['entry_time']))
                for mint,o in a['pending'].items():
                    if o['side']=='BUY' and mint in contexts and 'decimals' in contexts[mint]:targets.append((key,mint,'BUY',contexts[mint],o.get('amount',self.s['config']['size_sol']),o['created']))
            keys={(t[0],t[1],t[2]) for t in targets};self.quote_attempts={k:v for k,v in self.quote_attempts.items() if k in keys}
            targets.sort(key=lambda t:self.quote_attempts.get(t[:3],0))
            if not targets or now-self.quote_attempts.get(targets[0][:3],0)<30:return
            key,mint,side,ctx,amount,identity=targets[0];self.quote_attempts[(key,mint,side)]=now
            decimals=9 if side=='BUY' else ctx['decimals'];raw=int(Decimal(str(amount))*Decimal(10)**decimals)
            if raw<=0:return
            inp,out=('So11111111111111111111111111111111111111112',mint) if side=='BUY' else (mint,'So11111111111111111111111111111111111111112')
            output_decimals=ctx['decimals'] if side=='BUY' else 9;e=self.latest(contexts.get(mint),now)
            try:model=self.estimate(e,side,float(Decimal(raw)/Decimal(10)**decimals)) if e else None
            except ValueError:model=None
            run=self.s['id'];slippage=int(self.s['config']['slippage_bps'])
        # Network never holds the paper lock or changes balances/fills.
        q=self.quotes.check(inp,out,raw,slippage)
        if q['status']=='rate_limited':return
        q.update(side=side,input_raw=raw,model_output=model,model_observed=now,model_pool=ctx['pool'],output_unit='SOL' if side=='SELL' else 'tokens')
        if q['status']=='quoted':
            q['output']=q['out_raw']/10**output_decimals;q['minimum_output']=q['minimum_raw']/10**output_decimals
            q['model_difference_pct']=(model/q['output']-1)*100 if model is not None else None
            q['same_pool']=any(r['pool']==ctx['pool'] for r in q['route'])
        with self.lock:
            if run!=self.s['id']:return
            a=self.s['accounts'].get(key)
            if not a:return
            p=a['positions'].get(mint);order=a['pending'].get(mint)
            if side=='SELL' and (not p or p['entry_time']!=identity):return
            pending_match=order and order['created']==identity and order['side']=='BUY'
            position_match=p and p['entry_time']==identity
            if side=='BUY' and not (pending_match or position_match):return
            if p and side=='SELL':p['last_quote']=q
            elif side=='BUY' and position_match:p['entry_quote']=q
            elif order:order['last_quote']=q
            with self.db:self.db.execute('INSERT INTO quote_checks(run_id,mint,strategy,created,body) VALUES (?,?,?,?,?)',(run,mint,key,self.clock(),encode(q)));self.prune();self.save()
    def analysis(self):
        # Stream retained records: do not inflate thousands of JSON feature trees
        # into a second in-memory history on every dashboard poll.
        accum={key:dict(strategy=key,trades=0,wins=0,losses=0,win_sum=0.,loss_sum=0.,hold_sum=0.,modeled_costs_sol=0.,cost_coverage=0,blocked_exit_attempts=0,exit_reasons={}) for key in self.s['accounts']}
        for row in self.db.execute('SELECT strategy,body FROM trades ORDER BY id DESC LIMIT 5000'):
            t=json.loads(row['body'])
            if t.get('run_id',t.get('entry_features',{}).get('run_id'))!=self.s['id']:continue
            if row['strategy'] not in accum:continue
            if row['strategy'].startswith('ml_') and t.get('ml_comparison')!=self.s.get('ml_trial',{}).get('id'):continue
            a=accum[row['strategy']];a['trades']+=1;a['hold_sum']+=t['exit_time']-t['entry_time']
            if t['pnl_sol']>0:a['wins']+=1;a['win_sum']+=t['pnl_sol']
            elif t['pnl_sol']<0:a['losses']+=1;a['loss_sum']+=t['pnl_sol']
            if t.get('entry_costs') and t.get('exit_costs'):a['cost_coverage']+=1;a['modeled_costs_sol']+=t['entry_costs']['total_sol']+t['exit_costs']['total_sol']
            a['blocked_exit_attempts']+=t.get('blocked_exit_attempts',0);a['exit_reasons'][t['exit_reason']]=a['exit_reasons'].get(t['exit_reason'],0)+1
        report=[]
        for a in accum.values():
            a['win_rate_pct']=100*a['wins']/a['trades'] if a['trades'] else None
            a['average_win_sol']=a['win_sum']/a['wins'] if a['wins'] else None;a['average_loss_sol']=a['loss_sum']/a['losses'] if a['losses'] else None
            a['average_hold_seconds']=a['hold_sum']/a['trades'] if a['trades'] else None
            for k in ('wins','losses','win_sum','loss_sum','hold_sum'):del a[k]
            report.append(a)
        return report
    def labels(self,contexts,now):
        rows=self.db.execute("SELECT l.*,d.mint,d.features FROM labels l JOIN decisions d ON d.id=l.decision_id WHERE l.status='pending' AND l.due<=? ORDER BY l.due LIMIT 100",(now,)).fetchall()
        for r in rows:
            e=self.latest(contexts.get(r['mint']),now);initial=json.loads(r['features']).get('price')
            valid=e is not None and initial and now-r['due']<=5
            self.db.execute('UPDATE labels SET observed=?,status=?,body=? WHERE decision_id=? AND horizon=?',(now,'observed' if valid else 'unavailable',encode(dict(price=e['price'] if valid else None,return_pct=(e['price']/initial-1)*100 if valid else None,observation_time=e['received'] if valid else None)),r['decision_id'],r['horizon']))
    def prune(self):
        used=(self.db.execute('PRAGMA page_count').fetchone()[0]-self.db.execute('PRAGMA freelist_count').fetchone()[0])*self.db.execute('PRAGMA page_size').fetchone()[0]
        pressure=used>44*1048576
        self.opportunities.prune(pressure)
        self.db.execute('DELETE FROM writeoffs WHERE id NOT IN (SELECT id FROM writeoffs ORDER BY id DESC LIMIT 1000)')
        self.db.execute('DELETE FROM decisions WHERE id NOT IN (SELECT id FROM decisions ORDER BY id DESC LIMIT ?)',(5000 if pressure else 10000,))
        self.db.execute('DELETE FROM trades WHERE id NOT IN (SELECT id FROM trades ORDER BY id DESC LIMIT ?)',(2500 if pressure else 5000,))
        self.db.execute('DELETE FROM quote_checks WHERE id NOT IN (SELECT id FROM quote_checks ORDER BY id DESC LIMIT 500)')
        self.db.execute('DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY created DESC LIMIT 1000)')
        self.db.execute('DELETE FROM versions WHERE version NOT IN (SELECT version FROM versions ORDER BY created DESC LIMIT 1000) AND version<>?',(self.s['version'],))
        self.db.execute('PRAGMA incremental_vacuum(100)')
    def status(self):
        with self.lock:
            now=self.clock();contexts=self.discovery.market.paper_snapshot(now,self.s['config']['window_seconds']);accounts=[]
            for key,a in self.s['accounts'].items():
                positions=[self.position_view(m,p,a,contexts.get(m),now) for m,p in a['positions'].items()]
                equity=a['cash']+sum(p['mark_sol'] for p in positions)
                accounts.append(dict(strategy=key,writeoffs=a.get('writeoffs',0),impairment_pnl_sol=a.get('impairment_pnl',0),name=STRATEGIES.get(key,'ML candidate' if key=='ml_candidate' else 'ML comparison baseline'),cash_sol=a['cash'],equity_sol=equity,net_pnl_sol=equity-self.s['config']['starting_cash_sol'],realized_pnl_sol=a['realized_pnl'],closed=a['closed'],max_drawdown_pct=a['drawdown']*100,positions=positions,pending=copy.deepcopy(list(a['pending'].items()))))
            decisions=[dict(r,features=json.loads(r['features'])) for r in self.db.execute('SELECT * FROM decisions ORDER BY id DESC LIMIT 80')]
            # Current observations are separate from immutable audit decisions.
            # New bonding-curve launches cannot push active pool candidates away.
            candidates=[]
            for mint,ctx in contexts.items():
                if not ctx['pool']:continue
                for key,a in self.s['accounts'].items():
                    reason,f=self.screen(ctx,now);reason=reason or self.signal_reason(key,ctx,f)
                    state='watching' if reason else 'eligible'
                    if mint in a['positions']:state='position';reason=a['pending'].get(mint,{}).get('reason','Open paper position')
                    elif mint in a['pending']:state='pending';reason=a['pending'][mint]['reason']
                    elif not reason:reason='Signal eligible; entries paused' if not self.s['running'] else 'Signal eligible; awaiting evaluation / account limits'
                    candidates.append(dict(mint=mint,name=ctx['name'],symbol=ctx.get('symbol',''),strategy=key,state=state,reason=reason,features=f,created=now))
            candidates.sort(key=lambda d:(d['state'] not in ('position','pending'),d['features']['experimental_score'] is None,-(d['features']['experimental_score'] or 0)))
            summary=dict(tokens=len(contexts),pools=sum(bool(c['pool']) for c in contexts.values()),fresh_pools=sum(bool(c['pool']) and self.latest(c,now) is not None for c in contexts.values()),waiting_for_pool=sum(not c['pool'] for c in contexts.values()),missing_decimals=sum(bool(c['pool']) and 'decimals' not in c for c in contexts.values()),last_tick=self.s['last_tick'],feed_status=self.discovery.state if hasattr(self.discovery,'state') else 'Unknown',metadata_status=getattr(self.discovery.market,'metadata_status',''))
            caps=[self.features(c,now)['fdv_sol'] for c in contexts.values() if c['pool']]
            valued=[v for v in caps if v is not None]
            summary['valuation_coverage']=dict(valued_pools=len(valued),unknown_pools=len(caps)-len(valued),minimum_fdv_sol=min(valued) if valued else None,maximum_fdv_sol=max(valued) if valued else None,above_1000_sol=sum(v>=1000 for v in valued),above_10000_sol=sum(v>=10000 for v in valued),scope='Observed PumpSwap SOL pools only; no market-cap ceiling; not all Solana DEXs')
            trades=[]
            for r in self.db.execute('SELECT id,strategy,body FROM trades ORDER BY id DESC'):
                t=json.loads(r['body'])
                if t.get('run_id',t.get('entry_features',{}).get('run_id'))==self.s['id'] and (not r['strategy'].startswith('ml_') or t.get('ml_comparison')==self.s.get('ml_trial',{}).get('id')):trades.append(dict(**t,strategy=r['strategy'],id=r['id']))
                if len(trades)>=40:break
            page=self.db.execute('PRAGMA page_size').fetchone()[0];allocated=self.db.execute('PRAGMA page_count').fetchone()[0]*page
            return dict(opportunities={**self.opportunities.status(),'error':self.s.get('observation_error'),'queue_drops':getattr(self.discovery,'observation_drops',0)+self.s.get('observation_drops',0)},postmortem=postmortem(self.db,self.s['id']),writeoffs=[json.loads(r['body']) for r in self.db.execute('SELECT body FROM writeoffs ORDER BY id DESC LIMIT 20') if json.loads(r['body']).get('run_id')==self.s['id']],learning={**self.learner.status(),'models':self.model_status(),'error':self.learning_error},usd_reference=self.usd.snapshot() if self.usd else dict(rate=None,status='unavailable'),running=self.s['running'],status=self.s['status'],error=self.s['error'] or self.s.get('tracking_error'),version=self.s['version'],run_id=self.s['id'],config=self.s['config'],accounts=accounts,candidates=candidates[:80],feed={**summary,**getattr(self.discovery,'scanner',{})},decisions=decisions,trades=trades,analysis=self.analysis(),memory=self.discovery.bot.usage(),storage=dict(bytes=allocated,max_bytes=page*12800,decision_limit=10000,trade_limit=5000),note='Hypothetical reserve-model fills; quotes are read-only comparisons, never signed or submitted. Missing holder/bundler/global-fee evidence is unknown. Stale conservative marks count as zero; last observed values are shown separately.')
    def learning_tick(self):
        with self.lock:
            now=self.clock()
            model_error=None
            try:
                self.models.poll(now,keep=[self.s['ml_trial']['id']] if self.s.get('ml_trial') else [])
                with self.db:self.sync_model_trial(now)
            except Exception as exc:
                model_error='ML research unavailable ('+type(exc).__name__+'); baseline trading continues.'
                self.learning_error=model_error
            if self.last_learning is not None and now-self.last_learning<60:return
            self.last_learning=now
            try:
                with self.db:self.learner.update(now)
                self.models.schedule(now,self.s['version'])
                self.learning_error=model_error
            except Exception as exc:
                self.learning_error='Research update failed ('+type(exc).__name__+'); retrying automatically. Trading rules unchanged.'

    def archive_model_trial(self,now,reason):
        trial=self.s.get('ml_trial')
        if not trial:return
        report=dict(strategy=trial['strategy'],started=trial['created'],finished=now,reason=reason,
                    accounts={k:dict(cash_sol=self.s['accounts'][k]['cash'],net_pnl_sol=self.s['accounts'][k]['cash']-self.s['config']['starting_cash_sol'],closed=self.s['accounts'][k]['closed'],max_drawdown_pct=self.s['accounts'][k]['drawdown']*100) for k in ('ml_control','ml_candidate')},promoted=False)
        self.db.execute('INSERT OR REPLACE INTO ml_comparisons VALUES (?,?,?)',(trial['id'],now,encode(report)))
        self.db.execute('DELETE FROM ml_comparisons WHERE id NOT IN (SELECT id FROM ml_comparisons ORDER BY created DESC LIMIT 20)')

    def sync_model_trial(self,now):
        trial=self.s.get('ml_trial')
        if trial:
            pair=[self.s['accounts'][k] for k in ('ml_control','ml_candidate')]
            finished=now>=trial['entries_until'] or (now-trial['created']>=3600 and all(a['closed']>=50 for a in pair))
            if not finished or any(a['positions'] or a['pending'] for a in pair):return
            self.archive_model_trial(now,'Completed paper comparison; no automatic promotion')
            for key in ('ml_control','ml_candidate'):
                self.s['accounts'].pop(key);self.s['watch'].pop(key,None)
            self.s.pop('ml_trial');self.save()
        if not self.s['running']:return
        used={r['id'] for r in self.db.execute('SELECT id FROM ml_comparisons')}
        candidate=self.models.candidate(self.s['version'],used)
        if not candidate:return
        validate_model(candidate['model'])
        self.s['ml_trial']={k:copy.deepcopy(candidate[k]) for k in ('id','strategy','model','threshold','excluded_mints')}
        self.s['ml_trial'].update(created=now,entries_until=now+86400)
        for key in ('ml_control','ml_candidate'):
            self.s['accounts'][key]=dict(cash=self.s['config']['starting_cash_sol'],realized_pnl=0.,positions={},pending={},closed=0,peak_equity=self.s['config']['starting_cash_sol'],drawdown=0.,day=int(now//86400),day_pnl=0.,cooldowns={})
        self.save()

    def model_status(self):
        trial=self.s.get('ml_trial')
        return dict(**self.models.status(self.s['version']),trial={k:trial[k] for k in ('id','strategy','created','entries_until')} if trial else None,
                    comparisons=[dict(id=r['id'],**json.loads(r['body'])) for r in self.db.execute('SELECT * FROM ml_comparisons ORDER BY created DESC LIMIT 4')])

    def enrich_names(self):
        with self.lock:
            rows=[dict(r) for r in self.db.execute('SELECT id,mint,body FROM trades ORDER BY id DESC LIMIT 40')]
            extra=[r['mint'] for r in rows]
        self.discovery.market.enrich_names(extra)
        with self.lock,self.db:
            changed=False
            for a in self.s['accounts'].values():
                for mint,p in a['positions'].items():
                    identity=self.discovery.market.names.get(mint)
                    if identity and any(p['context'].get(k)!=v for k,v in identity.items()):p['context'].update(identity);changed=True
            for r in rows:
                identity=self.discovery.market.names.get(r['mint']);body=json.loads(r['body'])
                if identity and any(body.get(k)!=v for k,v in identity.items()):
                    body.update(identity)
                    self.db.execute('UPDATE trades SET body=? WHERE id=? AND mint=? AND body=?',(encode(body),r['id'],r['mint'],r['body']))
            if changed:self.save()

    def control(self,action):
        with self.lock:
            if action=='start':
                self.s['running']=True;self.s['status']='Scanning / paper entries enabled';self.s['error']=None
            elif action=='pause':
                self.s['running']=False;self.s['status']='Paused entries'
                for a in self.s['accounts'].values():a['pending']={m:o for m,o in a['pending'].items() if o['side']=='SELL'}
            elif action in ('new','clear'):
                if any(a['positions'] or a['pending'] for a in self.s['accounts'].values()):raise ValueError('Close paper positions and pause entries before resetting results')
                if self.s['running']:raise ValueError('Pause entries before resetting results')
                with self.db:
                    self.models.close()
                    if action=='new':self.archive_model_trial(self.clock(),'Run ended by user')
                    if action=='clear':
                        for table in ('ml_versions','ml_attempts','ml_comparisons','opportunities','seen_tokens','writeoffs'):self.db.execute('DELETE FROM '+table)
                    if action=='clear':self.db.execute('DELETE FROM learning_versions');self.last_learning=None;self.db.execute('DELETE FROM quote_checks');self.db.execute('DELETE FROM labels');self.db.execute('DELETE FROM decisions');self.db.execute('DELETE FROM trades');self.db.execute('DELETE FROM runs');self.db.execute('DELETE FROM versions')
                    else:self.db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?,?)',(self.s['id'],self.s['created'],self.s['version'],encode(self.s)))
                    self.s=self.fresh(self.new_config);self.save()
                if action=='clear':self.db.execute('VACUUM')
            else:raise ValueError('Unknown paper action')
            with self.db:self.save()
            self.sync_protection();return self.status()
    def request_exit(self,body):
        key=body.get('strategy');mint=body.get('mint')
        with self.lock:
            a=self.s['accounts'].get(key)
            if not a or mint not in a['positions']:raise ValueError('Paper position not found')
            now=self.clock();contexts=self.discovery.market.paper_snapshot(now,self.s['config']['window_seconds']);ctx=contexts.get(mint)
            if body.get('write_off'):
                if self.latest(ctx,now):raise ValueError('Fresh observations exist; use a paper exit')
                with self.db:self.write_off(key,mint,now,'Manual unresolved paper write-off; no sale');self.save()
                self.sync_protection();return self.status()
            with self.db:self.queue(a,key,mint,'SELL','Manual paper exit',self.features(ctx,now) if ctx else dict(price=None),ctx,now);self.save()
            self.sync_protection();return self.status()
    def export(self):
        with self.lock:return dict(state=copy.deepcopy(self.s),versions=[dict(r) for r in self.db.execute('SELECT * FROM versions')],runs=[dict(r) for r in self.db.execute('SELECT * FROM runs')],decisions=[dict(r) for r in self.db.execute('SELECT * FROM decisions')],trades=[dict(r) for r in self.db.execute('SELECT * FROM trades')],labels=[dict(r) for r in self.db.execute('SELECT * FROM labels')],quote_checks=[dict(r) for r in self.db.execute('SELECT * FROM quote_checks')],learning_versions=[dict(r) for r in self.db.execute('SELECT * FROM learning_versions')],ml_versions=[dict(r) for r in self.db.execute('SELECT * FROM ml_versions')],ml_comparisons=[dict(r) for r in self.db.execute('SELECT * FROM ml_comparisons')],opportunities=[dict(r) for r in self.db.execute('SELECT * FROM opportunities')],seen_tokens=[dict(r) for r in self.db.execute('SELECT * FROM seen_tokens')],writeoffs=[dict(r) for r in self.db.execute('SELECT * FROM writeoffs')])
    def close(self):
        with self.lock:
            self.models.close()
            self.s['running']=False
            with self.db:self.save()
            self.db.close()
