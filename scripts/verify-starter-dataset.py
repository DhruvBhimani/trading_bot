"""Verify stored snapshot determinism and save both event/recent diagnostic reports."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/ingestion'))
sys.path.insert(0,str(ROOT/'research/backtests'))
from market_database import connect
from starter_dataset import load_run,save_run
from starter_backtest import replay,Config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset_id',type=int)
    args=parser.parse_args()
    db=connect()
    try:
        dataset=load_run(db,args.dataset_id,'starter_dataset_v1')
        if len(dataset['cases'])!=5:
            raise ValueError('Expected all five starter cases to finish collecting')
        config=Config(**json.loads((ROOT/'config/local-simulator.json').read_text()))
        for window in ('event','recent'):
            first=replay(db,args.dataset_id,window,config)
            if first!=replay(db,args.dataset_id,window,config):
                raise ValueError('Replay is not deterministic')
            identifier=save_run(db,'starter_backtest_v1',first)
            if first!=load_run(db,identifier,'starter_backtest_v1'):
                raise ValueError('Saved report did not round trip')
            print(json.dumps({'dataset_id':args.dataset_id,'report_id':identifier,'window':window,
                 'verified_deterministic':True,'cases':[
                     {'symbol':c['symbol'],'candles':c['coverage']['candles'],'status':c['status'],
                      'summary':c.get('result',{}).get('summary')} for c in first['cases']]},indent=2))
    finally:
        db.close()


if __name__=='__main__':main()
