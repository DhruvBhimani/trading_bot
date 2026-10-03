"""Copy the existing SQLite research data into hosted PostgreSQL without deleting it."""
import argparse
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from market_database import connect, status

TABLES=('raw_responses','tokens','pools','fetches','discoveries','pool_snapshots','candle_versions','jobs')


def open_source(path):
    db=sqlite3.connect('file:'+quote(str(Path(path).resolve()))+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    return db


def inspect_source(source):
    return {table:source.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in TABLES}


def copy_data(source,target):
    """Idempotent evidence-based fetch mapping; never overwrite remote records."""
    mapping={}
    with target:
        if hasattr(target,'ensure_capacity'):target.ensure_capacity()
        for table in ('raw_responses','tokens','pools'):
            rows=source.execute('SELECT * FROM '+table).fetchall()
            if rows:
                placeholders=','.join('?' for _ in rows[0])
                target.executemany('INSERT OR IGNORE INTO '+table+' VALUES ('+placeholders+')',[tuple(row) for row in rows])
        for row in source.execute('SELECT * FROM fetches ORDER BY id'):
            existing=target.execute('SELECT id FROM fetches WHERE url=? AND retrieved_at=? AND sha256=? ORDER BY id LIMIT 1',
                                   (row['url'],row['retrieved_at'],row['sha256'])).fetchone()
            if existing:
                mapping[row['id']]=existing['id']
            else:
                mapping[row['id']]=target.execute('INSERT INTO fetches(url,retrieved_at,sha256) VALUES (?,?,?)',
                                                  (row['url'],row['retrieved_at'],row['sha256'])).lastrowid
        for table in ('discoveries','pool_snapshots','candle_versions','jobs'):
            rows=source.execute('SELECT * FROM '+table).fetchall()
            if not rows:continue
            columns=','.join('"'+name+'"' for name in rows[0].keys())
            placeholders=','.join('?' for _ in rows[0])
            batch=[]
            for row in rows:
                values=dict(row)
                if 'fetch_id' in values:values['fetch_id']=mapping[values['fetch_id']]
                batch.append(tuple(values.values()))
            target.executemany('INSERT OR IGNORE INTO '+table+' ('+columns+') VALUES ('+placeholders+')',batch)
        if hasattr(target,'ensure_capacity'):target.ensure_capacity()
    return inspect_source(source)


def main():
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=root/'data/processed/market.sqlite3')
    parser.add_argument('--inspect',action='store_true',help='Show source counts only; no remote connection or writes')
    args=parser.parse_args()
    source=open_source(args.source)
    try:
        if args.inspect:
            print(json.dumps(inspect_source(source),indent=2));return
        target=connect()
        try:
            with target.collector_lock():
                copied=copy_data(source,target)
            print(json.dumps({'source_records':copied,'hosted_database':status(target)},indent=2))
        finally:target.close()
    except RuntimeError as exc:
        parser.error(str(exc))
    except Exception:
        parser.error('Migration failed. Source data is preserved; check the database schema and access. No credentials are printed.')
    finally:source.close()


if __name__=='__main__':main()
