"""Timestamped observation adapters. Real wallet routing is handled separately by wallet.py."""
import json
import math
import re
from pathlib import Path
from demo_feed import price,liquidity

ROOT=Path(__file__).resolve().parents[1]
WATCHLIST=[{k:c[k] for k in ('symbol','token','pool')} for c in json.loads((ROOT/'config/starter-cohort.json').read_text())['cases'][:3]]
ADDRESS=re.compile(r'[1-9A-HJ-NP-Za-km-z]{32,44}\Z')


def validate(row):
    row=dict(row)
    if not re.fullmatch(r'[A-Za-z0-9_$.-]{1,16}',str(row.get('symbol',''))):raise ValueError('Invalid symbol')
    for key in ('timestamp','price'):
        value=row.get(key)
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError('Invalid '+key)
    value=row.get('liquidity')
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<0):raise ValueError('Invalid liquidity')
    for key in ('token','pool'):
        if row.get(key) is not None and not ADDRESS.fullmatch(row[key]):raise ValueError('Invalid '+key)
    return {k:row.get(k) for k in ('timestamp','symbol','price','liquidity','token','pool')}


def demo_batch(tick):
    return [dict(timestamp=1704067200+tick*5,symbol=s,price=price(s,tick),liquidity=liquidity(s,tick),token=None,pool=None) for s in ('SCOUT','BOLT','DUST')]

