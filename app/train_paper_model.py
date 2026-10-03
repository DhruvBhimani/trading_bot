"""Bounded subprocess trainer. No wallet imports, network, or database writes."""
import json
import math
import sys
from pathlib import Path
from ml_model import FEATURES, POLICY, THRESHOLD, predict, split_rows, validate, vector

def train(rows):
    import numpy as np
    import xgboost as xgb
    training, holdout = split_rows(rows)
    report = dict(training_trades=len(training), validation_trades=len(holdout),
                  training_coins=len({r['mint'] for r in training}),
                  validation_coins=len({r['mint'] for r in holdout}))
    if report['training_trades'] < 120 or report['training_coins'] < 50 or report['validation_trades'] < 40 or report['validation_coins'] < 20:
        return dict(status='insufficient_split', report=report)
    x = np.array([vector(r['features']) for r in training], dtype=np.float32)
    y = np.array([max(-1., min(1., r['return'])) for r in training], dtype=np.float32)
    if len(set(y > 0)) < 2: return dict(status='needs_wins_and_losses', report=report)
    params = dict(objective='reg:squarederror', base_score=0, max_depth=3, eta=.05,
                  min_child_weight=5, reg_lambda=10, subsample=.8, colsample_bytree=.9,
                  tree_method='hist', max_bin=64, nthread=1, seed=7)
    booster = xgb.train(params, xgb.DMatrix(x, label=y, feature_names=list(FEATURES)), num_boost_round=48)
    def tree(node):
        if 'leaf' in node: return [node['leaf']]
        children = {v['nodeid']: v for v in node['children']}
        return [FEATURES.index(node['split']), float(np.float32(node['split_condition'])), node['missing'] == node['yes'],
                tree(children[node['yes']]), tree(children[node['no']])]
    model = dict(policy=POLICY, features=list(FEATURES), base=0,
                 trees=[tree(json.loads(t)) for t in booster.get_dump(dump_format='json')])
    validate(model)
    # Verify portable inference against native XGBoost, including missing fields.
    checks = [r['features'] for r in rows] + [{}, dict(pool_sol=50, momentum=.1)]
    native = booster.predict(xgb.DMatrix(np.array([vector(f) for f in checks], dtype=np.float32), feature_names=list(FEATURES)))
    error = max(abs(float(p)-predict(model, f)) for p, f in zip(native, checks))
    if error > 1e-6: raise ValueError('Portable/native predictions differ')
    selected = [r for r in holdout if predict(model, r['features']) >= THRESHOLD]
    average = lambda rs: sum(r['return'] for r in rs)/len(rs) if rs else None
    mean = average(selected); baseline = average(holdout)
    report.update(selected=len(selected), selected_coins=len({r['mint'] for r in selected}),
                  mean_return=mean, baseline_mean_return=baseline,
                  stressed_mean_return=mean-.01 if mean is not None else None,
                  inference_max_error=error, validation_start=min(r['entry_time'] for r in holdout),
                  training_end=max(r['exit_time'] for r in training))
    # Fixed gate, not a threshold search. Historical subset results aren't portfolio P&L.
    accepted = len(selected) >= 20 and report['selected_coins'] >= 10 and mean > max(.01, baseline)
    importance = booster.get_score(importance_type='gain')
    return dict(status='paper_candidate' if accepted else 'validation_rejected', report=report,
                model=model, threshold=THRESHOLD, parameters=params, rounds=48,
                xgboost_version=xgb.__version__, importance=importance,
                native_model=json.loads(bytes(booster.save_raw(raw_format='json'))),
                excluded_mints=sorted({r['mint'] for r in rows}))

if __name__ == '__main__':
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (30, 35))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024*1024, 1024*1024))
    source, target = map(Path, sys.argv[1:])
    if source.stat().st_size > 2*1024*1024: raise ValueError('Training input too large')
    rows = json.loads(source.read_text())
    if len(rows) > 500: raise ValueError('Training window too large')
    if rows and rows[0].get('dataset')=='opportunity':
        from train_opportunity_model import train as train_opportunities
        result=train_opportunities(rows)
    else:result=train(rows)
    target.write_text(json.dumps(result, allow_nan=False, separators=(',', ':')))
