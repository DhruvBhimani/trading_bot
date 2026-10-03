"""Binary observed-path research with distinct time/coin calibration and test sets."""
import json
from ml_model import PROB_FEATURES as FEATURES,PROB_POLICY,THRESHOLD,raw_predict,predict,probability,validate,vector

def split(rows):
    rows=sorted(rows,key=lambda r:(r['entry_time'],r['id']));i=int(len(rows)*.6);j=int(len(rows)*.8)
    if not i or j>=len(rows):return [],[],[]
    a=rows[i]['entry_time'];b=rows[j]['entry_time']
    training=[r for r in rows[:i] if r['exit_time']<a]
    train_coins={r['mint'] for r in training}
    calibration=[r for r in rows[i:j] if r['exit_time']<b and r['mint'] not in train_coins]
    used=train_coins|{r['mint'] for r in calibration}
    test=[r for r in rows[j:] if r['mint'] not in used and r.get('validation_eligible',True)]
    return training,calibration,test

def train(rows):
    import numpy as np
    import xgboost as xgb
    from scipy.optimize import minimize
    training,calibration,test=split(rows)
    report={k+'_trades':len(v) for k,v in (('training',training),('calibration',calibration),('validation',test))}
    report.update({k+'_coins':len({r['mint'] for r in v}) for k,v in (('training',training),('calibration',calibration),('validation',test))})
    if len(training)<80 or len(calibration)<30 or len(test)<30 or report['training_coins']<40 or min(report['calibration_coins'],report['validation_coins'])<15:
        return dict(status='insufficient_split',report=report)
    if any(min(sum(r['label']==label for r in part) for label in (0,1))<5 for part in (training,calibration)):
        return dict(status='needs_both_barriers',report=report)
    matrix=lambda part:xgb.DMatrix(np.array([vector(r['features'],FEATURES) for r in part],dtype=np.float32),feature_names=list(FEATURES))
    d=matrix(training);d.set_label([r['label'] for r in training])
    params=dict(objective='binary:logistic',base_score=.5,max_depth=3,eta=.05,min_child_weight=5,reg_lambda=10,
                subsample=.8,colsample_bytree=.9,tree_method='hist',max_bin=64,nthread=1,seed=7)
    booster=xgb.train(params,d,num_boost_round=48)
    def tree(n):
        if 'leaf' in n:return [n['leaf']]
        children={c['nodeid']:c for c in n['children']}
        return [FEATURES.index(n['split']),float(np.float32(n['split_condition'])),n['missing']==n['yes'],tree(children[n['yes']]),tree(children[n['no']])]
    margins=booster.predict(matrix(calibration),output_margin=True);y=np.array([r['label'] for r in calibration])
    def loss(ab):
        z=ab[0]*margins+ab[1]
        return float(np.mean(np.logaddexp(0,z)-y*z)+.01*(ab[0]-1)**2+.01*ab[1]**2)
    fitted=minimize(loss,[1.,0.],method='Powell',bounds=((0,10),(-10,10)))
    if not fitted.success:return dict(status='calibration_failed',report=report)
    failures=[r['return']+r['features']['cost_fraction'] for r in calibration if not r['label']]
    model=dict(policy=PROB_POLICY,features=list(FEATURES),base=0,calibration=[float(v) for v in fitted.x],payoff_loss=max(-1,min(-.12,sum(failures)/len(failures))),
               trees=[tree(json.loads(t)) for t in booster.get_dump(dump_format='json')])
    validate(model)
    error=max(abs(float(v)-raw_predict(model,r['features'])) for v,r in zip(booster.predict(matrix(rows),output_margin=True),rows))
    if error>1e-6:raise ValueError('Portable/native margins differ')
    ps=[probability(model,r['features']) for r in test];prior=sum(y)/len(y)
    brier=sum((p-r['label'])**2 for p,r in zip(ps,test))/len(test)
    base_brier=sum((prior-r['label'])**2 for r in test)/len(test)
    selected=[r for r in test if predict(model,r['features'])>=THRESHOLD]
    mean=lambda rs:sum(r['return'] for r in rs)/len(rs) if rs else None
    halves=[test[:len(test)//2],test[len(test)//2:]]
    repeated=[ [r for r in part if predict(model,r['features'])>=THRESHOLD] for part in halves ]
    bins=[]
    for lo,hi in ((0,.33),(.33,.67),(.67,1.01)):
        group=[(p,r['label']) for p,r in zip(ps,test) if lo<=p<hi]
        bins.append(dict(range=[lo,min(1,hi)],count=len(group),predicted=sum(p for p,_ in group)/len(group) if group else None,observed=sum(v for _,v in group)/len(group) if group else None))
    average=mean(selected);baseline=mean(test)
    passed=len(selected)>=20 and len({r['mint'] for r in selected})>=10 and average>max(.01,baseline) and brier<base_brier and all(len(rs)>=8 and mean(rs)>.01 for rs in repeated)
    report.update(selected=len(selected),selected_coins=len({r['mint'] for r in selected}),mean_return=average,baseline_mean_return=baseline,
                  stressed_mean_return=average-.01 if average is not None else None,brier=brier,baseline_brier=base_brier,
                  reliability=bins,inference_max_error=error,period_means=[mean(rs) for rs in repeated],
                  label='Observed +25% before -12% within 60s; stop or covered timeout is negative; gaps excluded',
                  calibration_method='Regularized sigmoid on separate earlier coins/time; not a profitability guarantee')
    return dict(status='paper_candidate' if passed else 'validation_rejected',report=report,model=model,threshold=THRESHOLD,
                parameters=params,rounds=48,xgboost_version=xgb.__version__,importance=booster.get_score(importance_type='gain'),
                native_model=json.loads(bytes(booster.save_raw(raw_format='json'))),excluded_mints=sorted({r['mint'] for r in rows}))
