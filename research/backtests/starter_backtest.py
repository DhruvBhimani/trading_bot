"""Replay a pinned database dataset through the educational price-only baseline.

No network market fetches, wallet access, or executable return claims. Each coin
uses its own virtual account; per-coin results are not a shared portfolio.
"""
import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/ingestion'))
from market_database import connect
from import_gecko import epoch
from starter_dataset import load_run, save_run, stored_bars
from local_simulator import Config, simulate


def replay(db, dataset_id, window, config):
    if window not in ('event','recent'):
        raise ValueError('Choose event or recent window')
    config.validate()
    dataset=load_run(db,dataset_id,'starter_dataset_v1')
    result=dict(dataset_id=dataset_id,window=window,config=asdict(config),
                strategy='local_simulator_v1_close_signal_next_close_fill',
                strategy_sha256=hashlib.sha256((ROOT/'research/backtests/local_simulator.py').read_bytes()).hexdigest(),
                execution_ready=False,limitations=[
                    'Retrospectively selected cases; no profitability inference or parameter tuning validation.',
                    'Independent virtual cash account per coin; not a portfolio backtest.',
                    'Observed hourly close signals fill at the following hourly close; assumes historical availability at candle end.',
                    'Fees and slippage are fixed assumptions, not reconstructed historical execution costs.',
                    'No historical liquidity, tradability, MEV, outages, or failed fills; exits may have been impossible.',
                    'Final position is marked liquidated by the teaching simulator; not a real fill.',
                    'Incomplete or gapped windows are skipped; missing data never means zero losses.',
                    'Recent window does not replay the historical rally or collapse.' if window=='recent' else
                    'Event-window prices alone do not establish executable fills.'
                ],cases=[])
    for case in dataset['cases']:
        bars=stored_bars(db,case,window)
        spec=case[window]
        row=dict(symbol=case['symbol'],token=case['token'],group=case['group'],
                 coverage=spec,status='skipped_incomplete_window')
        contiguous=(len(bars)>=2 and epoch(bars[0]['start'])==epoch(spec['start']) and
                    epoch(bars[-1]['end'])==epoch(spec['end']) and
                    all(epoch(b['start'])==epoch(a['end']) for a,b in zip(bars,bars[1:])))
        if spec['status']=='complete_prices' and contiguous:
            # Only the price series enters the strategy. Outcome labels stay in reporting.
            simulation=simulate([b['close'] for b in bars],config)
            row.update(status='price_only_replayed',result=simulation,
                       candle_snapshot_sha256=hashlib.sha256(json.dumps(bars,sort_keys=True).encode()).hexdigest())
            for trade in simulation['trades']:
                trade['entry_time']=bars[trade['entry_bar']]['end']
                trade['exit_time']=bars[trade['exit_bar']]['end']
        result['cases'].append(row)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset_id',type=int)
    parser.add_argument('--window',choices=['event','recent'],default='event')
    parser.add_argument('--config',type=Path,default=ROOT/'config/local-simulator.json')
    args=parser.parse_args()
    db=connect()
    try:
        report=replay(db,args.dataset_id,args.window,Config(**json.loads(args.config.read_text())))
        identifier=save_run(db,'starter_backtest_v1',report)
        print(json.dumps({'saved_report_id':identifier,'dataset_id':args.dataset_id,'window':args.window,
                          'cases':[{'symbol':c['symbol'],'status':c['status'],
                                    'summary':c.get('result',{}).get('summary')} for c in report['cases']]},indent=2))
    finally:
        db.close()


if __name__=='__main__':
    main()
