"""Resumable public Solana market collector. No wallet access or orders."""
import argparse
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from import_gecko import epoch, normalize, request_url, utc_now
from market_database import connect, record_fetch, ingest_pools, ingest_candles, status, export_prices, coverage

BASE='https://api.geckoterminal.com/api/v2/networks/solana'


class PublicClient:
    def __init__(self, db, delay=3):
        self.db,self.delay,self.last=db,delay,0

    def get(self,url):
        if hasattr(self.db,'ensure_capacity'):
            self.db.ensure_capacity(10_000_000)
        for attempt in range(3):
            time.sleep(max(0,self.delay-(time.monotonic()-self.last)))
            self.last=time.monotonic()
            try:
                with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'DBBotResearch/0.2'}),timeout=30) as response:
                    raw=response.read()
                retrieved=utc_now()
                fetch_id=record_fetch(self.db,url,retrieved,raw)
                return json.loads(raw),raw,retrieved,fetch_id
            except HTTPError as exc:
                if exc.code==429:
                    raise RuntimeError('Provider rate limit reached; stopped safely. Resume later.') from exc
                if exc.code < 500 or attempt==2:raise
            except (URLError,TimeoutError):
                if attempt==2:raise
            time.sleep(5*(attempt+1))


def discover(db,client,target,pages):
    dex_payload,_,_,_=client.get(BASE+'/dexes?page=1')
    dexes=[r['id'] for r in dex_payload['data']]
    routes=[BASE+'/new_pools',BASE+'/pools']+[BASE+'/dexes/'+dex+'/pools' for dex in dexes]
    # Round robin across sources before deep pagination to broaden coverage.
    exhausted=set()
    for page in range(1,pages+1):
        for route in routes:
            if route in exhausted:continue
            if db.execute('SELECT COUNT(DISTINCT base_token) FROM pools').fetchone()[0]>=target:return
            url=route+'?'+urlencode(dict(page=page))
            try:
                payload,_,retrieved,fetch_id=client.get(url)
            except HTTPError as exc:
                if exc.code in (400,403,404,422):
                    print(json.dumps({'discovery_unavailable':route,'http_status':exc.code}),flush=True)
                    exhausted.add(route)
                    continue
                raise
            count=ingest_pools(db,payload,fetch_id,retrieved)
            if count<20:exhausted.add(route)
            print(json.dumps({'discovery_page':page,'source':route,'pools_returned':count,
                              'distinct_base_tokens':db.execute('SELECT COUNT(DISTINCT base_token) FROM pools').fetchone()[0]}),flush=True)


def queue_jobs(db,target,days,cutoff):
    end=int(cutoff//900)*900
    start=end-days*86400
    # One deterministic representative pool per base token; never count pools as coins.
    rows=db.execute('SELECT base_token,MIN(address) pool FROM pools GROUP BY base_token ORDER BY MIN(first_seen_at),base_token LIMIT ?',(target,)).fetchall()
    with db:
        for row in rows:
            db.execute('INSERT OR IGNORE INTO jobs(pool,interval_seconds,start_epoch,end_epoch,before_epoch,updated_at) VALUES (?,900,?,?,?,?)',
                       (row['pool'],start,end,end,utc_now()))
    return start,end


def collect(db,client,start,end):
    while True:
        job=db.execute("SELECT * FROM jobs WHERE start_epoch=? AND end_epoch=? AND status='pending' ORDER BY pages,pool LIMIT 1",(start,end)).fetchone()
        if job is None:return
        key=(job['pool'],job['interval_seconds'],start,end)
        url=request_url(job['pool'],'minute',15,job['before_epoch'])
        try:
            payload,raw,retrieved,fetch_id=client.get(url)
            normalized=normalize(raw,job['pool'],'minute',15,retrieved)
            # Atomic candle insertion and pagination checkpoint.
            candles=payload['data']['attributes']['ohlcv_list']
            oldest=min((int(c[0]) for c in candles),default=None)
            if oldest is not None and oldest>=job['before_epoch']:
                raise ValueError('Provider pagination made no progress')
            state='range_fetched' if oldest is not None and oldest<=start else ('source_exhausted' if not candles else 'pending')
            with db:
                count=ingest_candles(db,normalized,fetch_id,start,end,commit=False)
                db.execute('UPDATE jobs SET before_epoch=?,status=?,pages=pages+1,error=NULL,updated_at=? WHERE pool=? AND interval_seconds=? AND start_epoch=? AND end_epoch=?',
                           (oldest-1 if oldest is not None else job['before_epoch'],state,utc_now())+key)
            print(json.dumps({'pool':job['pool'],'stored_rows':count,'state':state}),flush=True)
        except HTTPError as exc:
            if exc.code not in (400,403,404,422):raise
            with db:
                db.execute("UPDATE jobs SET status='error',error=?,updated_at=? WHERE pool=? AND interval_seconds=? AND start_epoch=? AND end_epoch=?",(str(exc),utc_now())+key)
            print(json.dumps({'pool':job['pool'],'error':str(exc)}),flush=True)
        except (ValueError,KeyError,TypeError) as exc:
            with db:
                db.execute("UPDATE jobs SET status='error',error=?,updated_at=? WHERE pool=? AND interval_seconds=? AND start_epoch=? AND end_epoch=?",(str(exc),utc_now())+key)
            print(json.dumps({'pool':job['pool'],'error':str(exc)}),flush=True)



@contextmanager
def collection_lock(db, local_path):
    if getattr(db,'dialect',None)=='postgres':
        with db.collector_lock():yield
        return
    import fcntl
    with Path(str(local_path)+'.collector.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('A collector is already running') from None
        yield


def main():
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','status','coverage','export','backup'])
    parser.add_argument('--database',type=Path,help='Explicit SQLite path for offline tests only; default uses hosted DATABASE_URL')
    parser.add_argument('--target-tokens',type=int,default=1000)
    parser.add_argument('--days',type=int,default=7)
    parser.add_argument('--discovery-pages',type=int,default=10)
    parser.add_argument('--delay',type=float,default=3)
    parser.add_argument('--cutoff',help='Frozen UTC end time; omission resumes latest run window')
    parser.add_argument('--pool')
    parser.add_argument('--output',type=Path,default=root/'research/output/stored-prices.json')
    args=parser.parse_args()
    if args.target_tokens<1 or args.days<1 or not 1<=args.discovery_pages<=10 or not 3<=args.delay<=60:
        parser.error('Require positive token/day counts, discovery pages 1..10, delay 3..60 seconds')
    try:
        db=connect(args.database)
    except RuntimeError as exc:
        parser.error(str(exc))
    if args.command=='status':
        print(json.dumps(status(db),indent=2));return
    if args.command=='coverage':
        print(json.dumps(coverage(db),indent=2));return
    if args.command=='backup':
        if args.database is None:parser.error('Use the hosted provider backup/export tools for PostgreSQL')
        if args.output.resolve()==args.database.resolve():parser.error('Backup must use a different path')
        args.output.parent.mkdir(parents=True,exist_ok=True)
        if args.output.exists():parser.error('Backup destination already exists; choose a new file')
        with sqlite3.connect(str(args.output)) as backup:
            db.backup(backup)
        print(args.output);return
    if args.command=='export':
        if not args.pool:parser.error('--pool required for export')
        result=export_prices(db,args.pool,900)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(args.output);return
    with collection_lock(db,args.database):
        previous=db.execute('SELECT config_json FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone()
        cutoff=epoch(args.cutoff) if args.cutoff else (json.loads(previous[0])['cutoff'] if previous else time.time())
        config=dict(target_tokens=args.target_tokens,days=args.days,cutoff=cutoff,pid=os.getpid())
        with db:
            db.execute("UPDATE collection_runs SET status='interrupted',finished_at=? WHERE status='running'",(utc_now(),))
            run_id=db.execute("INSERT INTO collection_runs(started_at,status,config_json) VALUES (?,'running',?)",(utc_now(),json.dumps(config))).lastrowid
        outcome,error='finished',None
        try:
            client=PublicClient(db,args.delay)
            discover(db,client,args.target_tokens,args.discovery_pages)
            start,end=queue_jobs(db,args.target_tokens,args.days,cutoff)
            collect(db,client,start,end)
            print(json.dumps(status(db),indent=2),flush=True)
        except (Exception,KeyboardInterrupt) as exc:
            outcome,error='interrupted',('PostgreSQL operation failed; check connectivity and permissions' if exc.__class__.__module__.startswith('psycopg') else str(exc) or 'KeyboardInterrupt')
            print(json.dumps({'stopped':error,'resume':'Run the same command again'}),flush=True)
        finally:
            with db:
                db.execute('UPDATE collection_runs SET status=?,finished_at=?,error=? WHERE id=?',(outcome,utc_now(),error,run_id))
        if outcome!='finished':raise SystemExit(1)


if __name__=='__main__':main()
