"""Observed on-chain SOL trades and candles. No interpolated or synthetic prices."""
from decimal import Decimal
import json
import time
from feeds import ADDRESS
from store import encode
from token_names import TokenNames,extension_name
SOL='So11111111111111111111111111111111111111112'
ZERO='11111111111111111111111111111111'

class Market:
    def __init__(self,bot,rpc):
        self.bot=bot;self.rpc=rpc;self.names=TokenNames(rpc);self.names_generation=getattr(bot,'generation',0);self.metadata_retry={};self.metadata_status='Token metadata: waiting for discoveries'
        with bot.lock,bot.db:
            bot.db.executescript('''CREATE TABLE IF NOT EXISTS market_trades(signature TEXT NOT NULL,event_index INTEGER NOT NULL,mint TEXT NOT NULL,slot INTEGER NOT NULL,block_time INTEGER NOT NULL,received REAL NOT NULL,sol_raw TEXT NOT NULL,token_raw TEXT NOT NULL,is_buy INTEGER NOT NULL,real_sol_raw TEXT NOT NULL,real_token_raw TEXT NOT NULL,body TEXT NOT NULL,PRIMARY KEY(signature,event_index));
            CREATE INDEX IF NOT EXISTS market_mint_time ON market_trades(mint,block_time,slot);
            CREATE TABLE IF NOT EXISTS market_mints(mint TEXT PRIMARY KEY,decimals INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS token_metrics(mint TEXT PRIMARY KEY,volume_raw TEXT NOT NULL,protocol_fee_raw TEXT NOT NULL,creator_fee_raw TEXT NOT NULL,buys INTEGER NOT NULL,sells INTEGER NOT NULL,first_seen REAL NOT NULL,last_seen REAL NOT NULL,last_slot INTEGER NOT NULL,last_body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS launch_supply(mint TEXT PRIMARY KEY,supply_raw TEXT NOT NULL,observed REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS market_risk(mint TEXT PRIMARY KEY,observed REAL NOT NULL,body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS feature_memory(mint TEXT NOT NULL,signature TEXT NOT NULL,event_index INTEGER NOT NULL,version TEXT NOT NULL,received REAL NOT NULL,features TEXT NOT NULL,PRIMARY KEY(signature,event_index,version));''')
    def ingest(self,e):
        # Only explicitly native-SOL quote events are priceable by this adapter.
        if e.get('quote_mint') not in (SOL,ZERO):return False
        amount=int(e['sol_amount']);tokens=int(e['token_amount']);timestamp=int(e['timestamp'])
        if amount<=0 or tokens<=0 or timestamp<=0 or type(e['is_buy']) is not bool:return False
        e={k:e[k] for k in ('user','signature','event_index','mint','slot','timestamp','received','sol_amount','token_amount','is_buy','real_sol_reserves','real_token_reserves','quote_mint','program','pool','fee','creator_fee','lp_fee') if k in e}
        with self.bot.lock,self.bot.db:
            inserted=self.bot.db.execute('INSERT OR IGNORE INTO market_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',(e['signature'],e['event_index'],e['mint'],e['slot'],timestamp,e['received'],str(amount),str(tokens),int(e['is_buy']),e['real_sol_reserves'],e['real_token_reserves'],encode(e))).rowcount
            if inserted:
                self.aggregate(e)
                if hasattr(self.bot,'prune'):self.bot.db.execute('DELETE FROM market_trades WHERE mint=? AND rowid NOT IN (SELECT rowid FROM market_trades WHERE mint=? ORDER BY rowid DESC LIMIT 180)',(e['mint'],e['mint']))
        return True
    def launch(self,e):
        mint=e.get('mint') or e.get('base_mint');supply=e.get('token_total_supply')
        with self.bot.lock,self.bot.db:
            if supply is not None and int(supply)>0:self.bot.db.execute('INSERT OR IGNORE INTO launch_supply VALUES (?,?,?)',(mint,str(int(supply)),e['received']))
            if e.get('kind')=='pool' and type(e.get('base_mint_decimals')) is int:self.bot.db.execute('INSERT OR IGNORE INTO market_mints VALUES (?,?)',(mint,e['base_mint_decimals']))
    def enrich(self):
        # Batch metadata only, not snapshot prices. The displayed price is still
        # a confirmed trade; RPC supply/decimals unblock missing valuations.
        with self.bot.lock:
            generation=getattr(self.bot,'generation',0)
            known={r['mint'] for r in self.bot.store.rows('SELECT DISTINCT mint FROM launch_events')}
            self.metadata_retry={k:v for k,v in self.metadata_retry.items() if k in known}
            pending=self.bot.store.rows("SELECT DISTINCT e.mint,e.received,e.kind FROM launch_events e LEFT JOIN market_mints m ON m.mint=e.mint LEFT JOIN launch_supply s ON s.mint=e.mint WHERE m.mint IS NULL OR s.mint IS NULL OR NOT EXISTS (SELECT 1 FROM market_risk r WHERE r.mint=e.mint AND r.observed>CAST(strftime('%s','now') AS INTEGER)-120) ORDER BY e.received DESC")
            activity={r['mint']:r['last_seen'] for r in self.bot.store.rows('SELECT mint,last_seen FROM token_metrics')}
            pending.sort(key=lambda r:(r['mint'] not in getattr(self.bot,'pins',set())|getattr(self.bot,'protected',set()),r['kind']!='pool',-activity.get(r['mint'],0)))
            mints=list(dict.fromkeys(r['mint'] for r in pending if self.metadata_retry.get(r['mint'],0)<=time.time()))[:20]
            for mint in mints:self.metadata_retry[mint]=time.time()+60
        if not mints:return
        self.metadata_status='Verifying supply and decimals for '+str(len(mints))+' tokens'
        response=self.rpc('getMultipleAccounts',[mints,{'encoding':'jsonParsed','commitment':'confirmed'}])
        values=response.get('value',[])
        if len(values)!=len(mints):raise ValueError('Incomplete mint metadata response')
        self.metadata_status='Token metadata refreshed; missing accounts retry after 60 seconds'
        with self.bot.lock,self.bot.db:
            if generation!=getattr(self.bot,'generation',0):return
            for mint,account in zip(mints,values):
                if not self.bot.db.execute('SELECT 1 FROM launch_events WHERE mint=?',(mint,)).fetchone():continue
                if not account or account.get('owner') not in ('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb'):continue
                parsed=account.get('data',{}).get('parsed',{});info=parsed.get('info',{})
                if parsed.get('type')!='mint' or type(info.get('decimals')) is not int or not 0<=info['decimals']<=18:continue
                supply=info.get('supply','')
                if not isinstance(supply,str) or not supply.isdecimal():continue
                self.bot.db.execute('INSERT OR IGNORE INTO market_mints VALUES (?,?)',(mint,info['decimals']))
                self.bot.db.execute('INSERT OR REPLACE INTO launch_supply VALUES (?,?,?)',(mint,supply,time.time()))
                risk=dict(authority_known='mintAuthority' in info and 'freezeAuthority' in info,mint_authority=info.get('mintAuthority'),freeze_authority=info.get('freezeAuthority'),holders='unknown',bundlers='unknown',global_fees='unknown')
                self.bot.db.execute('INSERT OR REPLACE INTO market_risk VALUES (?,?,?)',(mint,time.time(),encode(risk)))
                identity=extension_name(account,mint)
                if identity:self.names.remember(mint,identity)

    def enrich_names(self,extra=()):
        with self.bot.lock:
            generation=getattr(self.bot,'generation',0)
            if generation!=self.names_generation:
                with self.names.lock:self.names.cache.clear();self.names.retry.clear();self.names_generation=generation
            rows=self.bot.store.rows('SELECT mint,body FROM launch_events ORDER BY received DESC')
            for row in rows:
                body=json.loads(row['body'])
                if body.get('name') and body['name']!=row['mint'][:10]:self.names.remember(row['mint'],body)
            mints=list(getattr(self.bot,'protected',set()))+list(extra)+[r['mint'] for r in rows]
        self.names.enrich(mints,accept=lambda:generation==getattr(self.bot,'generation',0))

    def aggregate(self,e):
        previous=self.bot.db.execute('SELECT * FROM token_metrics WHERE mint=?',(e['mint'],)).fetchone()
        v=int(e['sol_amount']);fee=int(e.get('fee',0));creator=int(e.get('creator_fee',0));buy=int(e['is_buy'])
        if previous:
            latest=e if e['slot']>=previous['last_slot'] else json.loads(previous['last_body'])
            values=(str(int(previous['volume_raw'])+v),str(int(previous['protocol_fee_raw'])+fee),str(int(previous['creator_fee_raw'])+creator),previous['buys']+buy,previous['sells']+1-buy,min(previous['first_seen'],e['received']),max(previous['last_seen'],e['received']),max(previous['last_slot'],e['slot']),encode(latest),e['mint'])
            self.bot.db.execute('UPDATE token_metrics SET volume_raw=?,protocol_fee_raw=?,creator_fee_raw=?,buys=?,sells=?,first_seen=?,last_seen=?,last_slot=?,last_body=? WHERE mint=?',values)
        else:self.bot.db.execute('INSERT INTO token_metrics VALUES (?,?,?,?,?,?,?,?,?,?)',(e['mint'],str(v),str(fee),str(creator),buy,1-buy,e['received'],e['received'],e['slot'],encode(e)))
        if hasattr(self.bot,'prune'):return  # No learning-history accumulation in live session mode.
        metric=self.metrics([e['mint']]).get(e['mint'],{})
        self.bot.db.execute('INSERT OR IGNORE INTO feature_memory VALUES (?,?,?,?,?,?)',(e['mint'],e['signature'],e['event_index'],'observed-features-v1',e['received'],encode(metric)))
    def metrics(self,mints):
        result={}
        with self.bot.lock:
            for mint in set(mints):
                r=self.bot.db.execute('SELECT * FROM token_metrics WHERE mint=?',(mint,)).fetchone()
                supply=self.bot.db.execute('SELECT supply_raw FROM launch_supply WHERE mint=?',(mint,)).fetchone()
                if not r:continue
                e=json.loads(r['last_body']);valuation=None
                meta=self.bot.db.execute('SELECT decimals FROM market_mints WHERE mint=?',(mint,)).fetchone()
                unit_price=str(Decimal(e['sol_amount'])*Decimal(10)**meta['decimals']/Decimal(e['token_amount'])/Decimal(10)**9) if meta else None
                if supply:valuation=str(Decimal(e['sol_amount'])*Decimal(supply['supply_raw'])/Decimal(e['token_amount'])/Decimal(10)**9)
                result[mint]=dict(price_sol=unit_price,age_seconds=max(0,time.time()-r['last_seen']),fdv_sol=valuation,volume_sol=str(Decimal(r['volume_raw'])/Decimal(10)**9),protocol_fees_sol=str(Decimal(r['protocol_fee_raw'])/Decimal(10)**9),creator_fees_sol=str(Decimal(r['creator_fee_raw'])/Decimal(10)**9),buys=r['buys'],sells=r['sells'],since=r['first_seen'],updated=r['last_seen'],real_sol_reserves=str(Decimal(e['real_sol_reserves'])/Decimal(10)**9),coverage='Observed SOL trades only; supply-based FDV, not circulating market cap or lifetime/global totals')
        return result

    def read(self,mint,interval=5):
        if not isinstance(mint,str) or not ADDRESS.fullmatch(mint):raise ValueError('Invalid mint')
        if type(interval) is not int or interval not in (1,5,10,60):raise ValueError('Choose 1, 5, 10 or 60 seconds')
        with self.bot.lock:
            generation=getattr(self.bot,'generation',0)
            meta=self.bot.db.execute('SELECT decimals FROM market_mints WHERE mint=?',(mint,)).fetchone()
            rows=self.bot.store.rows('SELECT rowid AS arrival,* FROM market_trades WHERE mint=? ORDER BY block_time DESC,slot DESC,rowid DESC LIMIT 3000',(mint,))
        if not rows:return dict(mint=mint,candles=[],trades=[],note='No supported SOL trades recorded yet. Coverage starts when this mint is followed.')
        if meta is None:
            result=self.rpc('getAccountInfo',[mint,{'encoding':'jsonParsed','commitment':'confirmed'}])
            account=result.get('value') or {};parsed=account.get('data',{}).get('parsed',{})
            if account.get('owner') not in ('TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb') or parsed.get('type')!='mint':raise ValueError('Mint decimals unavailable')
            decimals=parsed['info']['decimals']
            if type(decimals) is not int or not 0<=decimals<=18:raise ValueError('Unsupported decimals')
            with self.bot.lock,self.bot.db:
                if generation!=getattr(self.bot,'generation',0):raise ValueError('Session was cleared; select a current coin')
                if hasattr(self.bot,'prune') and not self.bot.db.execute('SELECT 1 FROM launch_events WHERE mint=?',(mint,)).fetchone():raise ValueError('Coin expired')
                self.bot.db.execute('INSERT OR IGNORE INTO market_mints VALUES (?,?)',(mint,decimals))
        else:decimals=meta['decimals']
        buckets={};trades=[]
        for r in reversed(rows):
            sol=Decimal(r['sol_raw'])/Decimal(10)**9;quantity=Decimal(r['token_raw'])/Decimal(10)**decimals;price=float(sol/quantity);ts=r['block_time']//interval*interval
            c=buckets.setdefault(ts,dict(timestamp=ts,open=price,high=price,low=price,close=price,volume_sol=0.,trades=0))
            c.update(high=max(c['high'],price),low=min(c['low'],price),close=price,volume_sol=c['volume_sol']+float(sol),trades=c['trades']+1)
            trades.append(dict(signature=r['signature'],timestamp=r['block_time'],received=r['received'],price_sol=price,quantity=str(quantity),sol=str(sol),side='BUY' if r['is_buy'] else 'SELL'))
        latest=rows[0]
        return dict(metrics=self.metrics([mint]).get(mint),mint=mint,interval=interval,decimals=decimals,candles=list(buckets.values())[-120:],trades=trades[-30:][::-1],last_received=latest['received'],real_sol_reserves=str(Decimal(latest['real_sol_raw'])/Decimal(10)**9),real_token_reserves=str(Decimal(latest['real_token_raw'])/Decimal(10)**decimals),note='Observed confirmed Pump.fun / mapped PumpSwap SOL trades only. Same-second order uses slot then receipt order. Missing intervals stay empty; downtime may omit trades. Last reserve values come from a trade event, not a current liquidity guarantee.')

    def paper_snapshot(self,now,window=30):
        """Decision-time SOL-pool observations; no outside price snapshot calls."""
        result={}
        with self.bot.lock:
            for row in self.bot.store.rows('SELECT * FROM launch_events'):
                mint=row['mint'];launch=json.loads(row['body'])
                context=dict(mint=mint,name=launch.get('name') or mint[:10],pool=launch.get('pool'),quote_mint=launch.get('quote_mint'),age=max(0,now-row['received']),risk=None,samples=[],stage=launch.get('stage','migration_unknown'))
                if launch.get('canonical_migration') is True:context.update(stage='verified_migrated',migration_received=row['received'],migration_basis='Canonical Pump.fun pool identity; recovery window begins at observation, not migration time')
                migration=self.bot.db.execute('SELECT * FROM migration_events WHERE mint=?',(mint,)).fetchone()
                if migration and migration['pool']==context['pool']:
                    context['stage']='verified_migrated';context['migration_received']=migration['received']
                meta=self.bot.db.execute('SELECT decimals FROM market_mints WHERE mint=?',(mint,)).fetchone()
                identity=self.names.get(mint)
                context.update(name=identity.get('name') or launch.get('name') or None,symbol=identity.get('symbol') or launch.get('symbol') or '')
                supply=self.bot.db.execute('SELECT supply_raw,observed FROM launch_supply WHERE mint=?',(mint,)).fetchone()
                if meta and supply:
                    context.update(supply_tokens=float(Decimal(supply['supply_raw'])/Decimal(10)**meta['decimals']),supply_observed=supply['observed'])
                risk=self.bot.db.execute('SELECT body,observed FROM market_risk WHERE mint=?',(mint,)).fetchone()
                if risk:context['risk']={**json.loads(risk['body']),'observed':risk['observed']}
                rows=self.bot.store.rows('SELECT * FROM market_trades WHERE mint=? AND received>=? ORDER BY block_time DESC,slot DESC,rowid DESC LIMIT 180',(mint,now-max(window,180)))
                if meta:
                    context['decimals']=meta['decimals']
                    for r in reversed(rows):
                        e=json.loads(r['body'])
                        if e.get('program')!='pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA' or e.get('pool')!=context['pool'] or e.get('quote_mint')!=SOL:continue
                        amount=float(Decimal(r['sol_raw'])/Decimal(10)**9);qty=float(Decimal(r['token_raw'])/Decimal(10)**meta['decimals'])
                        fees=(int(e.get('lp_fee',0))+int(e.get('fee',0))+int(e.get('creator_fee',0)))/int(r['sol_raw'])
                        sample=dict(wallet=e.get('user'),signature=r['signature'],event_index=r['event_index'],slot=r['slot'],received=r['received'],timestamp=r['block_time'],price=amount/qty,volume_sol=amount,buy=bool(r['is_buy']),pool_sol=float(Decimal(r['real_sol_raw'])/Decimal(10)**9),pool_tokens=float(Decimal(r['real_token_raw'])/Decimal(10)**meta['decimals']),fee_fraction=fees)
                        context['samples'].append(sample)
                result[mint]=context
        return result
