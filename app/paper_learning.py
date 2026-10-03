"""Versioned filter research on frozen paper fills; never changes entry rules.

Training fit is exploratory. Forward evaluation is a subset of baseline trades,
not a simulated replacement portfolio or evidence of executable profitability.
"""
import hashlib
import json
import math
from store import encode

FILTERS=[dict(feature='experimental_score',minimum=n) for n in (60,70,80)]+[dict(feature='pool_sol',minimum=n) for n in (10,25,50)]
def passes(trade,rule):
 value=trade.get('entry_features',{}).get(rule['feature'])
 return isinstance(value,(int,float)) and math.isfinite(value) and value>=rule['minimum']

class PaperLearning:
 def __init__(self,db):
  self.db=db
  db.execute('CREATE TABLE IF NOT EXISTS learning_versions(id TEXT PRIMARY KEY,strategy TEXT NOT NULL,created REAL NOT NULL,cutoff INTEGER NOT NULL,body TEXT NOT NULL)')
 def update(self,now):
  # Bounded by both database retention and this small training window.
  rows=[]
  for r in self.db.execute('SELECT id,strategy,body FROM trades ORDER BY id DESC LIMIT 300'):
   t=json.loads(r['body'])
   if not t.get('entry_features') or t.get('exit_time',now+1)>now:continue
   rows.append(dict(id=r['id'],strategy=r['strategy'],trade=t))
  for strategy in ('momentum','recovery'):
   group=[r for r in rows if r['strategy']==strategy]
   if group:
    baseline=group[0]['trade'];group=[r for r in group if r['trade']['version']==baseline['version'] and r['trade'].get('execution_policy')==baseline.get('execution_policy')]
   if len(group)<40 or len({r['trade']['mint'] for r in group})<20:continue
   last=self.db.execute('SELECT * FROM learning_versions WHERE strategy=? ORDER BY created DESC LIMIT 1',(strategy,)).fetchone()
   if last and sum(r['id']>last['cutoff'] for r in group)<50:continue
   # Keep the latest version frozen through at least 50 later closed trades.
   cutoff=max(r['id'] for r in group);base=sum(r['trade']['pnl_sol'] for r in group)/len(group);choices=[]
   for rule in FILTERS:
    subset=[r for r in group if passes(r['trade'],rule)]
    if len(subset)<15 or len({r['trade']['mint'] for r in subset})<10:continue
    average=sum(r['trade']['pnl_sol'] for r in subset)/len(subset)
    if average>0 and average>base:choices.append((average,len(subset),rule))
   if not choices:continue
   average,count,rule=max(choices,key=lambda x:(x[0],x[1]))
   payload=dict(execution_policy=group[0]['trade'].get('execution_policy'),rule=rule,baseline_version=group[0]['trade']['version'],training_trades=len(group),training_selected=count,training_mean_sol=average,baseline_mean_sol=base,training_mints=sorted({r['trade']['mint'] for r in group}),status='forward_observation',forward=dict(seen=0,selected=0,selected_pnl_sol=0.,baseline_pnl_sol=0.),last_evaluated_id=cutoff)
   identity=hashlib.sha256(encode(dict(strategy=strategy,cutoff=cutoff,rule=rule)).encode()).hexdigest()[:16]
   self.db.execute('INSERT OR IGNORE INTO learning_versions VALUES (?,?,?,?,?)',(identity,strategy,now,cutoff,encode(payload)))
  # Every version gets only later, same-baseline-version, newly entered trades.
  for version in self.db.execute('SELECT * FROM learning_versions ORDER BY created DESC LIMIT 20').fetchall():
   body=json.loads(version['body']);last=body['last_evaluated_id'];f=body['forward'];changed=False
   if rows and min(r['id'] for r in rows)>last+1:body['coverage_warning']='Some later records were not retained in the evaluation window';changed=True
   for r in reversed(rows):
    if r['id']<=last or r['strategy']!=version['strategy']:continue
    t=r['trade'];body['last_evaluated_id']=max(body['last_evaluated_id'],r['id']);changed=True
    if t['entry_time']<=version['created'] or t['version']!=body['baseline_version'] or t.get('execution_policy')!=body.get('execution_policy'):continue
    if t['mint'] in body['training_mints']:continue  # Separate coins as well as time.
    f['seen']+=1;f['baseline_pnl_sol']+=t['pnl_sol']
    if passes(t,body['rule']):f['selected']+=1;f['selected_pnl_sol']+=t['pnl_sol']
   if changed:self.db.execute('UPDATE learning_versions SET body=? WHERE id=?',(encode(body),version['id']))
  self.db.execute('DELETE FROM learning_versions WHERE id NOT IN (SELECT id FROM learning_versions ORDER BY created DESC LIMIT 20)')
 def status(self):
  versions=[]
  for row in self.db.execute('SELECT * FROM learning_versions ORDER BY created DESC LIMIT 4'):
   b=json.loads(row['body']);b.pop('training_mints',None);versions.append(dict(id=row['id'],strategy=row['strategy'],created=row['created'],**b))
  counts={r['strategy']:r['n'] for r in self.db.execute('SELECT strategy,COUNT(*) n FROM trades GROUP BY strategy')}
  return dict(mode='shadow_filters_only',versions=versions,closed_trades=counts,minimum_training_trades=40,minimum_training_coins=20,note='Requires enough diverse outcomes and a promising training filter. Versions observe later, different coins. Active trading rules stay unchanged; no automatic promotion.')
