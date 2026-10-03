"""Small curated GeckoTerminal dataset, stored only in configured PostgreSQL.

Uses the existing collection_runs JSON envelope; no database migration required.
Each dataset pins fetch IDs so later provider revisions cannot change a replay.
"""
import argparse
import json
from pathlib import Path
from urllib.error import HTTPError

from collect_market import PublicClient, BASE
from import_gecko import epoch, iso, normalize, request_url, utc_now
from market_database import connect, record_fetch, ingest_pools, ingest_candles

ROOT = Path(__file__).resolve().parents[2]


def save_run(db, kind, body, state='complete'):
    with db:
        return db.execute('INSERT INTO collection_runs(started_at,finished_at,status,config_json) VALUES (?,?,?,?)',
                          (utc_now(),utc_now(),state,json.dumps({'kind':kind,'body':body},allow_nan=False))).lastrowid


def load_run(db, run_id, kind):
    row=db.execute('SELECT config_json FROM collection_runs WHERE id=?',(run_id,)).fetchone()
    if not row:
        raise ValueError('Unknown saved run')
    envelope=json.loads(row[0])
    if envelope.get('kind') != kind:
        raise ValueError('Saved run has a different type')
    return envelope['body']


def fetch_window(db, client, case, start, end):
    # Hourly bars: a month fits in one free page. Never fill missing intervals.
    url=request_url(case['pool'],'hour',1,int(end))
    try:
        _,raw,retrieved,fid=client.get(url)
    except HTTPError as exc:
        raw=exc.read()
        fid=record_fetch(db,url,utc_now(),raw)
        return dict(start=iso(start),end=iso(end),status='provider_unavailable',
                    http_status=exc.code,fetch_ids=[fid],candles=0)
    normalized=normalize(raw,case['pool'],'hour',1,retrieved)
    if normalized['token'] != case['token']:
        raise ValueError('Provider returned a different mint for '+case['symbol'])
    count=ingest_candles(db,normalized,fid,start,end)
    bars=[b for b in normalized['bars'] if epoch(b['interval_start'])>=start and epoch(b['interval_end'])<=end]
    expected=int((end-start)//3600)
    return dict(start=iso(start),end=iso(end),fetch_ids=[fid],candles=count,
                expected_intervals=expected,missing_intervals=max(0,expected-count),
                status='complete_prices' if count==expected else ('partial_prices' if count else 'no_prices_returned'),
                first=bars[0]['interval_start'] if bars else None,last=bars[-1]['interval_end'] if bars else None)


def collect_starter(db, client, manifest, end, days=7, resume_id=None):
    if len(manifest['cases']) not in range(5,11):
        raise ValueError('Starter cohort must contain 5–10 cases')
    if len({c['token'] for c in manifest['cases']}) != len(manifest['cases']):
        raise ValueError('Duplicate token in cohort')
    end=int(end//3600)*3600
    body=dict(name=manifest['name'],selection=manifest['selection'],interval_seconds=3600,
              execution_ready=False,recent_end=end,recent_days=days,manifest=manifest,cases=[])
    if resume_id is not None:
        body=load_run(db,resume_id,'starter_dataset_v1')
        if body.get('manifest',manifest) != manifest:
            raise ValueError('Cannot resume with a changed manifest')
        # Backward compatibility with the first checkpoint written by this collector.
        if 'recent_end' in body:
            end=body['recent_end']
        elif body['cases']:
            end=int(epoch(body['cases'][0]['recent']['end']))
        days=body.get('recent_days',days)
        body.update(manifest=manifest,recent_end=end,recent_days=days)
        run_id=resume_id
        with db:
            db.execute('UPDATE collection_runs SET status=?,error=NULL WHERE id=?',('running',run_id))
    else:
        run_id=save_run(db,'starter_dataset_v1',body,'running')
    try:
        for case in manifest['cases']:
            if any(c['token']==case['token'] for c in body['cases']):
                continue
            payload,_,retrieved,fid=client.get(BASE+'/pools/'+case['pool'])
            pool=payload['data']
            if (pool['attributes']['address'] != case['pool'] or
                pool['relationships']['base_token']['data']['id'] != 'solana_'+case['token']):
                raise ValueError('Pool identity mismatch for '+case['symbol'])
            ingest_pools(db,{'data':[pool]},fid,retrieved)
            event=fetch_window(db,client,case,epoch(case['event_start']),epoch(case['event_end']))
            recent=fetch_window(db,client,case,end-days*86400,end)
            body['cases'].append({**case,'metadata_fetch_id':fid,'event':event,'recent':recent})
            with db:
                db.execute('UPDATE collection_runs SET config_json=? WHERE id=?',
                           (json.dumps({'kind':'starter_dataset_v1','body':body}),run_id))
            print(json.dumps({'dataset_id':run_id,'symbol':case['symbol'],'event':event['status'],
                              'recent':recent['status'],'recent_candles':recent['candles']}),flush=True)
        state='complete' if all(c['event']['status']=='complete_prices' for c in body['cases']) else 'complete_with_gaps'
        with db:
            db.execute('UPDATE collection_runs SET status=?,finished_at=? WHERE id=?',(state,utc_now(),run_id))
    except Exception as exc:
        with db:
            # Do not persist exception strings that might contain a connection secret.
            db.execute('UPDATE collection_runs SET status=?,finished_at=?,error=? WHERE id=?',
                       ('failed',utc_now(),type(exc).__name__,run_id))
        raise
    return run_id


def stored_bars(db, case, window):
    spec=case[window]
    rows=[]
    for fid in spec['fetch_ids']:
        rows.extend(dict(r) for r in db.execute('SELECT * FROM candle_versions WHERE pool=? AND token=? AND interval_seconds=3600 AND fetch_id=? AND start>=? AND "end"<=? ORDER BY start',
                    (case['pool'],case['token'],fid,spec['start'],spec['end'])))
    rows.sort(key=lambda r:r['start'])
    if len(rows)!=spec['candles'] or len({r['start'] for r in rows})!=len(rows):
        raise ValueError('Saved candle snapshot is incomplete or duplicated')
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    collect=sub.add_parser('collect')
    collect.add_argument('--manifest',type=Path,default=ROOT/'config/starter-cohort.json')
    collect.add_argument('--resume',type=int,help='Resume a saved dataset using its frozen end date')
    show=sub.add_parser('show');show.add_argument('dataset_id',type=int)
    report=sub.add_parser('report');report.add_argument('report_id',type=int)
    args=parser.parse_args()
    db=connect()
    try:
        if args.command=='collect':
            with db.collector_lock():
                identifier=collect_starter(db,PublicClient(db,delay=12),json.loads(args.manifest.read_text()),epoch(utc_now()),resume_id=args.resume)
            print(json.dumps({'saved_dataset_id':identifier}))
        elif args.command=='show':
            print(json.dumps(load_run(db,args.dataset_id,'starter_dataset_v1'),indent=2))
        else:
            print(json.dumps(load_run(db,args.report_id,'starter_backtest_v1'),indent=2))
    finally:
        db.close()


if __name__=='__main__':
    main()
