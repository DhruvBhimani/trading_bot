"""Migrate and verify saved research data without printing connection credentials."""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/ingestion'))
from market_database import connect,status
from migrate_local import open_source,copy_data,inspect_source

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--branch',required=True)
args=parser.parse_args()
result=subprocess.run(['neon','connection-string',args.branch,'--project-id','solitary-credit-06176932'],capture_output=True,text=True)
if result.returncode:
    raise SystemExit('Could not retrieve branch connection settings; no credentials printed.')
url=result.stdout.strip()
if not url.startswith(('postgres://','postgresql://')):
    raise SystemExit('Unexpected connection-string response; no credentials printed.')
os.environ['DATABASE_URL_UNPOOLED']=url
source=open_source(ROOT/'data/processed/market.sqlite3')
try:
    destination=connect()
    try:
        with destination.collector_lock():
            copy_data(source,destination)
            before=status(destination)
            copy_data(source,destination)
            after=status(destination)
            if before!=after:raise RuntimeError('Repeat migration changed counts')
            expected=source.execute('SELECT COUNT(*) FROM latest_candles').fetchone()[0]
            if after['unique_candles'] != expected:raise RuntimeError('Candle counts do not match')
            # Compare every imported candle value, not only row counts.
            query='SELECT pool,token,interval_seconds,start,"end",open,high,low,close,volume FROM latest_candles ORDER BY pool,start'
            original=[tuple(row) for row in source.execute(query)]
            saved=[tuple(row.values()) for row in destination.execute(query)]
            if original!=saved:raise RuntimeError('Saved candle values do not match')
            print(json.dumps({'branch':args.branch,'migration_verified':True,'idempotency_verified':True,
                              'candle_values_verified':True,'status':after},indent=2))
    finally:destination.close()
finally:source.close()
