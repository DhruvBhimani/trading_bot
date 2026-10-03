"""Local append-only observations and auditable paper run records."""
import json
import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA='''
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,name TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,config TEXT NOT NULL,state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS datasets(id TEXT PRIMARY KEY,name TEXT NOT NULL,source TEXT NOT NULL,created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS raw_batches(id TEXT PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES datasets(id),received REAL NOT NULL,url TEXT NOT NULL,body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS observations(id INTEGER PRIMARY KEY,dataset_id TEXT NOT NULL REFERENCES datasets(id),timestamp REAL NOT NULL,symbol TEXT NOT NULL,price REAL NOT NULL,liquidity REAL,token TEXT,pool TEXT,raw_id TEXT REFERENCES raw_batches(id),UNIQUE(dataset_id,symbol,timestamp));
CREATE INDEX IF NOT EXISTS observations_time ON observations(dataset_id,timestamp);
CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),symbol TEXT NOT NULL,side TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,reason TEXT NOT NULL,details TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fills(id TEXT PRIMARY KEY,order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),run_id TEXT NOT NULL REFERENCES runs(id),timestamp REAL NOT NULL,symbol TEXT NOT NULL,side TEXT NOT NULL,price REAL NOT NULL,quantity REAL NOT NULL,cash_delta REAL NOT NULL,fee REAL NOT NULL,details TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS fills_run ON fills(run_id,timestamp);
CREATE TABLE IF NOT EXISTS signals(id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),timestamp REAL NOT NULL,symbol TEXT NOT NULL,action TEXT NOT NULL,reason TEXT NOT NULL,inputs TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,run_id TEXT NOT NULL REFERENCES runs(id),timestamp REAL NOT NULL,kind TEXT NOT NULL,message TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equity_curve(run_id TEXT NOT NULL REFERENCES runs(id),timestamp REAL NOT NULL,equity REAL NOT NULL,cash REAL NOT NULL,PRIMARY KEY(run_id,timestamp));
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
'''


def encode(value):return json.dumps(value,allow_nan=False,sort_keys=True)


class Store:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(str(path),check_same_thread=False)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON');self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)

    def persist(self,s):
        self.db.execute('INSERT INTO runs VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,updated=excluded.updated,state=excluded.state',
                        (s['id'],s['name'],s['created'],time.time(),encode(s['config']),encode(s)))
        self.db.execute("INSERT INTO metadata VALUES ('active_run',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(s['id'],))

    def load(self,identifier):
        row=self.db.execute('SELECT state FROM runs WHERE id=?',(identifier,)).fetchone()
        if not row:raise ValueError('Run not found')
        return json.loads(row['state'])

    def rows(self,sql,args=()):return [dict(r) for r in self.db.execute(sql,args)]

    def add_observations(self,dataset,rows,raw=None):
        raw_id=None
        if raw:
            raw_id=str(uuid.uuid4());self.db.execute('INSERT INTO raw_batches VALUES (?,?,?,?,?)',(raw_id,dataset,raw['received_at'],raw['url'],raw['body']))
        for r in rows:
            self.db.execute('INSERT OR IGNORE INTO observations(dataset_id,timestamp,symbol,price,liquidity,token,pool,raw_id) VALUES (?,?,?,?,?,?,?,?)',
                (dataset,r['timestamp'],r['symbol'],r['price'],r['liquidity'],r.get('token'),r.get('pool'),raw_id))

    def dataset(self,identifier,name,source):
        self.db.execute('INSERT OR IGNORE INTO datasets VALUES (?,?,?,?)',(identifier,name,source,time.time()))

    def backup(self):
        directory=self.path.parent/'backups';directory.mkdir(exist_ok=True)
        path=directory/('paper-bot-'+time.strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6]+'.sqlite3')
        with sqlite3.connect(str(path)) as dest:self.db.backup(dest)
        return str(path)
