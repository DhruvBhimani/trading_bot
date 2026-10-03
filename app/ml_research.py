"""One bounded local trainer at a time; frozen models in the capped paper DB."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import time
from ml_model import POLICY,PROB_POLICY, validate
from opportunities import LABEL_POLICY
from store import encode

ROOT = Path(__file__).resolve().parents[1]

class ModelResearch:
    def __init__(self, db):
        self.db = db; self.job = None
        db.executescript('''CREATE TABLE IF NOT EXISTS ml_versions(id TEXT PRIMARY KEY,strategy TEXT NOT NULL,created REAL NOT NULL,body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS ml_attempts(strategy TEXT PRIMARY KEY,created REAL NOT NULL,cutoff INTEGER NOT NULL,status TEXT NOT NULL,body TEXT NOT NULL);''')
        # An interrupted trainer is retried after the normal cooldown, without losing models.
        db.execute("UPDATE ml_attempts SET status='interrupted' WHERE status='training'")

    def dataset(self, strategy, version):
        rows = []
        if strategy=='opportunity':
            for r in self.db.execute("SELECT * FROM opportunities WHERE version=? AND status IN ('target_first','stop_first','timeout') ORDER BY id DESC LIMIT 500",(version,)):
                b=json.loads(r['body']);cost=b.get('cost_fraction')
                if b.get('policy')!=LABEL_POLICY or b.get('label') not in (0,1) or cost is None:continue
                rows.append(dict(id=r['id'],mint=r['mint'],entry_time=r['created'],exit_time=b['ended'],dataset='opportunity',label=b['label'],
                                 features={**b['features'],'cost_fraction':cost},**{'return':b['observed_return']-cost}))
            return rows
        for r in self.db.execute('SELECT id,body FROM trades WHERE strategy=? ORDER BY id DESC LIMIT 500', (strategy,)):
            t = json.loads(r['body'])
            if t.get('version') != version or t.get('execution_policy') != 'signal-ceiling-v1-10pct': continue
            if not t.get('signal_features') or not t.get('cost_sol', 0) > 0: continue
            # Only pre-outcome observed fields are exposed to the training process.
            from ml_model import vector
            f = t['signal_features']
            if sum(v is not None for v in vector(f)) < 6: continue
            ret = t['pnl_sol']/t['cost_sol']
            if not math.isfinite(ret): continue
            rows.append(dict(id=r['id'], mint=t['mint'], entry_time=t['entry_time'], exit_time=t['exit_time'],
                             features={k:f.get(k) for k in ('age_seconds','trade_count','volume_sol','buy_fraction','pool_sol','momentum','fdv_sol','stage')}, **{'return':ret}))
        return rows

    def poll(self, now, keep=()):
        job = self.job
        if not job: return
        proc = job['process']; failed = None
        if proc.poll() is None:
            if time.monotonic()-job['started'] > 60: failed = 'trainer_timeout'
            else:
                try:
                    rss = int(subprocess.check_output(['ps','-o','rss=','-p',str(proc.pid)], timeout=1).strip() or 0)
                    if rss > 512*1024: failed = 'trainer_memory_limit'
                except (OSError, ValueError, subprocess.SubprocessError): pass
            if not failed: return
            proc.kill(); proc.wait(timeout=5)
        try:
            target = Path(job['temp'].name)/'output.json'
            if failed or proc.returncode != 0 or not target.exists():
                result = dict(status=failed or 'trainer_failed', report={})
            else:
                if target.stat().st_size > 512*1024: raise ValueError('Model too large')
                result = json.loads(target.read_text())
                if result.get('model'): validate(result['model'])
            result.setdefault('report',{})['validation_after']=job['validation_after']
            policy=result.get('model',{}).get('policy',POLICY)
            body = dict(**result, baseline_version=job['version'], cutoff=job['cutoff'], policy=policy)
            with self.db:
                self.db.execute('UPDATE ml_attempts SET status=?,body=? WHERE strategy=?', (result['status'], encode(body.get('report',{})), job['strategy']))
                if result.get('model'):
                    identity = hashlib.sha256(encode(dict(strategy=job['strategy'], version=job['version'], cutoff=job['cutoff'], policy=policy)).encode()).hexdigest()[:16]
                    self.db.execute('INSERT OR IGNORE INTO ml_versions VALUES (?,?,?,?)', (identity, job['strategy'], now, encode(body)))
                retained = {r['id'] for r in self.db.execute('SELECT id FROM ml_versions ORDER BY created DESC LIMIT 6')} | set(keep)
                for row in self.db.execute('SELECT id FROM ml_versions').fetchall():
                    if row['id'] not in retained: self.db.execute('DELETE FROM ml_versions WHERE id=?',(row['id'],))
        except Exception as exc:
            with self.db:self.db.execute('UPDATE ml_attempts SET status=?,body=? WHERE strategy=?', ('trainer_result_invalid', encode(dict(error=type(exc).__name__)), job['strategy']))
        finally:
            job['temp'].cleanup(); self.job = None

    def schedule(self, now, version):
        if self.job: return
        python = ROOT/'research/.venv-ml/bin/python'
        if not python.exists(): return
        for strategy in self.strategies():
            rows = self.dataset(strategy, version)
            if len(rows)<200 or len({r['mint'] for r in rows})<80: continue
            cutoff = max(r['id'] for r in rows)
            previous = self.db.execute('SELECT * FROM ml_attempts WHERE strategy=?',(strategy,)).fetchone()
            if previous:
                if now-previous['created']<3600: continue
                # Failed/interrupted jobs may retry the same data; successful fits need new evidence.
                if previous['status'] not in ('interrupted','trainer_failed','trainer_timeout','trainer_memory_limit','trainer_result_invalid') and sum(r['id']>previous['cutoff'] for r in rows)<50: continue
            failed_states=('interrupted','trainer_failed','trainer_timeout','trainer_memory_limit','trainer_result_invalid')
            validation_after=(json.loads(previous['body']).get('validation_after',0) if previous['status'] in failed_states else previous['cutoff']) if previous else 0
            for row in rows:row['validation_eligible']=row['id']>validation_after
            temp = tempfile.TemporaryDirectory(prefix='db-bot-train-')
            source = Path(temp.name)/'input.json';target = Path(temp.name)/'output.json';source.write_text(encode(rows))
            env = {**os.environ, 'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','VECLIB_MAXIMUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONDONTWRITEBYTECODE':'1'}
            try:
                proc = subprocess.Popen([str(python),str(ROOT/'app/train_paper_model.py'),str(source),str(target)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            except OSError:
                temp.cleanup(); raise
            self.job = dict(process=proc,temp=temp,started=time.monotonic(),strategy=strategy,version=version,cutoff=cutoff,validation_after=validation_after)
            self.db.execute('INSERT OR REPLACE INTO ml_attempts VALUES (?,?,?,?,?)',(strategy,now,cutoff,'training',encode(dict(validation_after=validation_after))));self.db.commit()
            return

    def candidate(self, version, used):
        for row in self.db.execute('SELECT * FROM ml_versions ORDER BY created DESC LIMIT 8'):
            body = json.loads(row['body'])
            if row['id'] not in used and body['baseline_version']==version and body['status']=='paper_candidate':
                validate(body['model']); return dict(id=row['id'],strategy='momentum' if row['strategy']=='opportunity' else row['strategy'],created=row['created'],**body)

    def strategies(self):
        return ('opportunity',) if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='opportunities'").fetchone() else ('momentum','recovery')

    def status(self, version):
        progress = []
        for strategy in self.strategies():
            rows = self.dataset(strategy,version)
            attempt = self.db.execute('SELECT status,body FROM ml_attempts WHERE strategy=?',(strategy,)).fetchone()
            progress.append(dict(strategy=strategy,trades=len(rows),coins=len({r['mint'] for r in rows}),
                                 status=attempt['status'] if attempt else 'collecting', report=json.loads(attempt['body']) if attempt else {}))
        versions = []
        for row in self.db.execute('SELECT * FROM ml_versions ORDER BY created DESC LIMIT 6'):
            body = json.loads(row['body'])
            versions.append(dict(id=row['id'],strategy=row['strategy'],created=row['created'],status=body['status'],report=body['report'],importance=body.get('importance',{})))
        return dict(engine='XGBoost',unit='observed outcomes' if self.strategies()==('opportunity',) else 'trades',minimum_trades=200,minimum_coins=80,progress=progress,versions=versions,
                    runtime_ready=(ROOT/'research/.venv-ml/bin/python').exists())

    def close(self):
        if self.job:
            proc = self.job['process']
            if proc.poll() is None: proc.kill()
            proc.wait(timeout=5);self.job['temp'].cleanup();self.job=None
            self.db.execute("UPDATE ml_attempts SET status='interrupted' WHERE status='training'")
