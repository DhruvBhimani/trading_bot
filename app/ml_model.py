"""Small, dependency-free inference contract for frozen paper entry filters."""
import math
import struct

FEATURES = ('log_age', 'trade_count', 'log_volume', 'buy_fraction',
            'log_pool', 'momentum', 'log_fdv', 'verified_migrated')
PROB_FEATURES=FEATURES+('log_buyers','buyer_velocity')
POLICY = 'xgb-net-return-v1'
PROB_POLICY = 'xgb-barrier-calibrated-v1'
THRESHOLD = .02  # Fixed before looking at validation; predicted net return, not probability.

def vector(f,names=FEATURES):
    def number(key, log=False):
        x = f.get(key)
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
            return None
        if log:
            if x < 0: return None
            x = math.log1p(x)
        if abs(x) > 1e30: return None
        return struct.unpack('f', struct.pack('f', x))[0]
    values=[number('age_seconds', True), number('trade_count'), number('volume_sol', True),
            number('buy_fraction'), number('pool_sol', True), number('momentum'),
            number('fdv_sol', True), 1. if f.get('stage') == 'verified_migrated' else 0.]
    return values+[number('unique_buyers',True),number('buyer_velocity')] if tuple(names)==PROB_FEATURES else values

def validate(model):
    if model.get('features') != list(PROB_FEATURES if model.get('policy')==PROB_POLICY else FEATURES) or model.get('policy') not in (POLICY,PROB_POLICY):
        raise ValueError('Unsupported model contract')
    if model['policy']==PROB_POLICY:
        a,b=model['calibration']
        if not 0<=a<=10 or not -10<=b<=10:raise ValueError('Invalid calibration')
        if not -1<=model.get('payoff_loss',-.12)<=-.12:raise ValueError('Invalid payoff assumption')
    trees = model['trees']
    if not 1 <= len(trees) <= 64 or model.get('base') != 0:
        raise ValueError('Model exceeds inference budget')
    def visit(node, depth=0):
        if depth > 3: raise ValueError('Tree too deep')
        if len(node) == 1:
            if not isinstance(node[0], (int, float)) or not math.isfinite(node[0]): raise ValueError('Invalid leaf')
            return
        if len(node) != 5 or type(node[0]) is not int or not 0 <= node[0] < len(model['features']) or not math.isfinite(node[1]) or type(node[2]) is not bool:
            raise ValueError('Invalid split')
        visit(node[3], depth+1); visit(node[4], depth+1)
    for tree in trees: visit(tree)

def raw_predict(model, features):
    values = vector(features,model['features']); result = model['base']
    for tree in model['trees']:
        node = tree
        while len(node) != 1:
            value = values[node[0]]
            left = node[2] if value is None else value < node[1]
            node = node[3] if left else node[4]
        result += node[0]
    return result

def probability(model,features):
    a,b=model['calibration'];z=max(-40,min(40,a*raw_predict(model,features)+b))
    return 1/(1+math.exp(-z))

def predict(model,features):
    if model['policy']==PROB_POLICY:
        cost=features.get('cost_fraction')
        if not isinstance(cost,(float,int)) or not math.isfinite(cost) or cost<0:return -1.
        p=probability(model,features)
        return p*.25+(1-p)*model.get('payoff_loss',-.12)-cost
    return raw_predict(model,features)

def split_rows(rows):
    """Later entries are holdout; embargo overlapping trades and shared mints."""
    rows = sorted(rows, key=lambda r: (r['entry_time'], r['id']))
    cut = int(len(rows)*.7)
    if not rows or cut == len(rows): return [], []
    boundary = rows[cut]['entry_time']
    train = [r for r in rows[:cut] if r['exit_time'] < boundary]
    seen = {r['mint'] for r in train}
    test = [r for r in rows[cut:] if r['mint'] not in seen and r.get('validation_eligible', True)]
    return train, test
