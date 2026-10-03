"""Archive and normalize GeckoTerminal OHLCV; never invent execution inputs."""
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

INTERVALS = {'minute': (60, (1, 5, 15)), 'hour': (3600, (1, 4, 12)), 'day': (86400, (1,))}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def epoch(text):
    dt = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('retrieved_at must include a timezone')
    return dt.timestamp()


def iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def request_url(pool, timeframe, aggregate, before=None):
    if not re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}', pool):
        raise ValueError('Expected a Solana pool address')
    if timeframe not in INTERVALS or aggregate not in INTERVALS[timeframe][1]:
        raise ValueError('Unsupported timeframe/aggregate')
    query = dict(aggregate=aggregate, limit=1000, currency='usd', token='base', include_empty_intervals='false')
    if before is not None:
        if type(before) is not int or before <= 0:
            raise ValueError('before must be a positive epoch timestamp')
        query['before_timestamp'] = before
    return 'https://api.geckoterminal.com/api/v2/networks/solana/pools/' + pool + '/ohlcv/' + timeframe + '?' + urlencode(query)


def normalize(raw, pool, timeframe, aggregate, retrieved_at):
    request_url(pool, timeframe, aggregate)
    retrieved = epoch(retrieved_at)
    payload = json.loads(raw)
    candles = payload['data']['attributes']['ohlcv_list']
    token = payload['meta']['base']['address']
    if not isinstance(token, str) or not token:
        raise ValueError('Missing base token address')
    if not isinstance(candles, list):
        raise ValueError('ohlcv_list must be an array')
    interval = INTERVALS[timeframe][0] * aggregate
    bars, seen, unfinished = [], set(), 0
    for candle in candles:
        if not isinstance(candle, list) or len(candle) != 6:
            raise ValueError('Expected [timestamp, open, high, low, close, volume]')
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in candle):
            raise ValueError('Nonfinite or nonnumeric candle value')
        start, opening, high, low, close, volume = candle
        if start <= 0 or int(start) != start or min(opening, high, low, close) <= 0 or volume < 0:
            raise ValueError('Invalid timestamp, price or volume')
        if not low <= min(opening, close) <= max(opening, close) <= high:
            raise ValueError('Inconsistent OHLC bounds')
        if start in seen:
            raise ValueError('Duplicate candle timestamp')
        seen.add(start)
        if start + interval > retrieved:
            unfinished += 1
            continue
        bars.append(dict(token=token, pool=pool, interval_start=iso(start), interval_end=iso(start+interval),
                         open_usd=opening, high_usd=high, low_usd=low, close_usd=close, volume_usd=volume,
                         historical_available_at=None, liquidity_usd=None, tradable=None, _start=start))
    bars.sort(key=lambda b: b['_start'])
    gaps = [{'after': a['interval_end'], 'before': b['interval_start'],
             'missing_intervals': max(0, int((b['_start']-a['_start'])/interval)-1)}
            for a,b in zip(bars,bars[1:]) if b['_start']-a['_start'] > interval]
    for bar in bars:
        del bar['_start']
    blockers = ['Historical liquidity missing', 'Historical tradability not established',
                'Historical availability times unknown', 'Selected pool is not an unbiased token universe']
    if not bars:
        blockers.append('No completed candles returned')
    return dict(schema_version='market-bars-v1', synthetic=False, source='GeckoTerminal public API',
                retrieved_at=retrieved_at, raw_sha256=hashlib.sha256(raw).hexdigest(),
                network='solana', pool=pool, token=token, interval_seconds=interval,
                quality=dict(execution_backtest_ready=False, blockers=blockers, candle_count=len(bars),
                             incomplete_candles_excluded=unfinished, gaps=gaps,
                             note='Missing intervals may mean no swaps or missing coverage; do not fill silently.'), bars=bars)


def main():
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', required=True)
    parser.add_argument('--timeframe', choices=list(INTERVALS), default='minute')
    parser.add_argument('--aggregate', type=int, default=15)
    parser.add_argument('--before', type=int)
    parser.add_argument('--raw-input', type=Path, help='Normalize an already downloaded response instead of fetching')
    parser.add_argument('--retrieved-at', help='Actual download time, required with --raw-input')
    parser.add_argument('--output-dir', type=Path, default=root/'data/processed')
    parser.add_argument('--archive-dir', type=Path, default=root/'data/raw')
    args=parser.parse_args()
    try:
        url=request_url(args.pool,args.timeframe,args.aggregate,args.before)
        if args.raw_input:
            if not args.retrieved_at:
                raise ValueError('--raw-input requires --retrieved-at')
            raw=args.raw_input.read_bytes()
            retrieved=args.retrieved_at
        else:
            with urlopen(Request(url,headers={'Accept':'application/json','User-Agent':'DBBotResearch/0.1'}),timeout=30) as response:
                raw=response.read()
            retrieved=utc_now()
        # Save the original response even if normalization later rejects its contents.
        digest=hashlib.sha256(raw).hexdigest()
        args.archive_dir.mkdir(parents=True,exist_ok=True)
        archive=args.archive_dir/(digest+'.json')
        archive.write_bytes(raw)
        result=normalize(raw,args.pool,args.timeframe,args.aggregate,retrieved)
        result['request_url']=url
        result['raw_archive']=str(archive.resolve())
        args.output_dir.mkdir(parents=True,exist_ok=True)
        stamp=datetime.fromtimestamp(epoch(retrieved),timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        output=args.output_dir/(args.pool+'-'+stamp+'.json')
        output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    except (ValueError,KeyError,TypeError,OSError) as exc:
        parser.error(str(exc))
    print(json.dumps(result['quality'],indent=2))
    print('Normalized data:',output)


if __name__=='__main__':
    main()
