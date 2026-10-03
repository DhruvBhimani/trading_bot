"""Research database (hosted PostgreSQL by default). Raw provider evidence and price history remain separate."""
import hashlib
import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS raw_responses (
 sha256 TEXT PRIMARY KEY, body BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS fetches (
 id INTEGER PRIMARY KEY, url TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 sha256 TEXT NOT NULL REFERENCES raw_responses(sha256)
);
CREATE TABLE IF NOT EXISTS tokens (
 address TEXT PRIMARY KEY, first_seen_at TEXT NOT NULL, classification TEXT NOT NULL DEFAULT 'unclassified'
);
CREATE TABLE IF NOT EXISTS pools (
 address TEXT PRIMARY KEY, base_token TEXT NOT NULL REFERENCES tokens(address),
 quote_token TEXT NOT NULL REFERENCES tokens(address), name TEXT, dex TEXT,
 created_at TEXT, first_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS discoveries (
 pool TEXT NOT NULL REFERENCES pools(address), fetch_id INTEGER NOT NULL REFERENCES fetches(id),
 PRIMARY KEY(pool, fetch_id)
);
CREATE TABLE IF NOT EXISTS pool_snapshots (
 pool TEXT NOT NULL REFERENCES pools(address), fetch_id INTEGER NOT NULL REFERENCES fetches(id),
 retrieved_at TEXT NOT NULL, liquidity_usd REAL, price_usd REAL,
 PRIMARY KEY(pool, fetch_id)
);
CREATE TABLE IF NOT EXISTS candle_versions (
 pool TEXT NOT NULL REFERENCES pools(address), token TEXT NOT NULL REFERENCES tokens(address),
 interval_seconds INTEGER NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL,
 open REAL NOT NULL, high REAL NOT NULL, low REAL NOT NULL, close REAL NOT NULL,
 volume REAL NOT NULL, fetch_id INTEGER NOT NULL REFERENCES fetches(id),
 PRIMARY KEY(pool, interval_seconds, start, fetch_id)
);
CREATE INDEX IF NOT EXISTS candle_lookup ON candle_versions(token, interval_seconds, start);
CREATE TABLE IF NOT EXISTS jobs (
 pool TEXT NOT NULL REFERENCES pools(address), interval_seconds INTEGER NOT NULL,
 start_epoch INTEGER NOT NULL, end_epoch INTEGER NOT NULL, before_epoch INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', pages INTEGER NOT NULL DEFAULT 0,
 error TEXT, updated_at TEXT NOT NULL,
 PRIMARY KEY(pool, interval_seconds, start_epoch, end_epoch)
);
CREATE TABLE IF NOT EXISTS collection_runs (
 id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
 config_json TEXT NOT NULL, error TEXT
);
CREATE VIEW IF NOT EXISTS latest_candles AS
 SELECT pool,token,interval_seconds,start,"end",open,high,low,close,volume,fetch_id FROM (
 SELECT c.*, ROW_NUMBER() OVER (
 PARTITION BY pool,interval_seconds,start ORDER BY f.retrieved_at DESC,c.fetch_id DESC
 ) AS revision FROM candle_versions c JOIN fetches f ON c.fetch_id=f.id
 ) AS versions WHERE revision=1;
'''


def connect(path=None):
    if path is None:
        from postgres_store import PostgresStore, configured_url
        return PostgresStore(configured_url(),SCHEMA)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db=sqlite3.connect(str(path),timeout=30)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript(SCHEMA)
    return db


def record_fetch(db, url, retrieved_at, raw):
    if hasattr(db,'ensure_capacity'):
        db.ensure_capacity(len(raw)*4)
    digest=hashlib.sha256(raw).hexdigest()
    with db:
        db.execute('INSERT OR IGNORE INTO raw_responses VALUES (?,?)',(digest,raw))
        cursor=db.execute('INSERT INTO fetches(url,retrieved_at,sha256) VALUES (?,?,?)',(url,retrieved_at,digest))
    return cursor.lastrowid


def finite_or_none(value):
    import math
    try:
        number=float(value)
    except (ValueError,TypeError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def ingest_pools(db, payload, fetch_id, retrieved_at):
    rows=payload['data']
    if not isinstance(rows,list):
        raise ValueError('Expected a list of pools')
    with db:
        for row in rows:
            attrs,rel=row['attributes'],row['relationships']
            def token(role):
                identifier=rel[role]['data']['id']
                if not identifier.startswith('solana_'):
                    raise ValueError('Expected a Solana token')
                return identifier[len('solana_'):]
            base,quote=token('base_token'),token('quote_token')
            pool=attrs['address']
            for address in (base,quote):
                db.execute('INSERT OR IGNORE INTO tokens(address,first_seen_at) VALUES (?,?)',(address,retrieved_at))
            existing=db.execute('SELECT base_token,quote_token FROM pools WHERE address=?',(pool,)).fetchone()
            if existing and (existing['base_token'],existing['quote_token']) != (base,quote):
                raise ValueError('Provider changed pool token mapping')
            db.execute('INSERT OR IGNORE INTO pools VALUES (?,?,?,?,?,?,?)',
                       (pool,base,quote,attrs.get('name'),rel.get('dex',{}).get('data',{}).get('id'),attrs.get('pool_created_at'),retrieved_at))
            db.execute('INSERT OR IGNORE INTO discoveries VALUES (?,?)',(pool,fetch_id))
            db.execute('INSERT OR IGNORE INTO pool_snapshots VALUES (?,?,?,?,?)',
                       (pool,fetch_id,retrieved_at,finite_or_none(attrs.get('reserve_in_usd')),finite_or_none(attrs.get('base_token_price_usd'))))
    return len(rows)


def ingest_candles(db, normalized, fetch_id, start_epoch=0, end_epoch=float('inf'), commit=True):
    from import_gecko import epoch
    pool=normalized['pool']
    row=db.execute('SELECT base_token FROM pools WHERE address=?',(pool,)).fetchone()
    if not row or row['base_token'] != normalized['token']:
        raise ValueError('OHLCV token does not match discovered pool base token')
    values=[]
    for bar in normalized['bars']:
        if epoch(bar['interval_start']) < start_epoch or epoch(bar['interval_end']) > end_epoch:
            continue
        values.append((pool,bar['token'],normalized['interval_seconds'],bar['interval_start'],bar['interval_end'],
                       bar['open_usd'],bar['high_usd'],bar['low_usd'],bar['close_usd'],bar['volume_usd'],fetch_id))
    with (db if commit else nullcontext()):
        db.executemany('INSERT OR IGNORE INTO candle_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)',values)
    return len(values)



def status(db):
    def scalar(sql):return db.execute(sql).fetchone()[0]
    return dict(discovered_base_tokens=scalar('SELECT COUNT(DISTINCT base_token) FROM pools'),
                discovered_pools=scalar('SELECT COUNT(*) FROM pools'),
                tokens_with_candles=scalar('SELECT COUNT(DISTINCT token) FROM candle_versions'),
                unique_candles=scalar('SELECT COUNT(*) FROM latest_candles'),
                liquidity_snapshots=scalar('SELECT COUNT(*) FROM pool_snapshots WHERE liquidity_usd IS NOT NULL'),
                raw_responses=scalar('SELECT COUNT(*) FROM raw_responses'),
                jobs={r['status']:r['n'] for r in db.execute('SELECT status,COUNT(*) n FROM jobs GROUP BY status')},
                historical_liquidity_rows=0, execution_ready_tokens=0,
                latest_run=dict(db.execute('SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1').fetchone() or {}))


def export_prices(db, pool, interval_seconds):
    rows=db.execute('SELECT c.*,f.retrieved_at FROM latest_candles c JOIN fetches f ON c.fetch_id=f.id WHERE pool=? AND interval_seconds=? ORDER BY start',
                    (pool,interval_seconds)).fetchall()
    if not rows:raise ValueError('No stored candles for that pool and interval')
    return dict(schema_version='market-bars-v1',synthetic=False,source='Stored GeckoTerminal archive',
                pool=pool,token=rows[0]['token'],interval_seconds=interval_seconds,
                quality=dict(execution_backtest_ready=False,blockers=['Historical liquidity missing','Tradability unknown','Historical availability unknown','Universe selection bias']),
                bars=[dict(token=r['token'],pool=pool,interval_start=r['start'],interval_end=r['end'],
                           open_usd=r['open'],high_usd=r['high'],low_usd=r['low'],close_usd=r['close'],volume_usd=r['volume'],
                           retrieved_at=r['retrieved_at'],fetch_id=r['fetch_id'],liquidity_usd=None,tradable=None,historical_available_at=None) for r in rows])


def coverage(db):
    """Report actual price coverage, not simply tokens found in a listing."""
    return [dict(row) for row in db.execute("""
        SELECT p.address AS pool, p.base_token AS token, p.name, p.dex,
               COUNT(c.start) AS candles, MIN(c.start) AS first_candle,
               MAX(c.end) AS last_candle, c.interval_seconds
        FROM pools p LEFT JOIN latest_candles c ON c.pool=p.address
        GROUP BY p.address,c.interval_seconds ORDER BY candles DESC,p.address
    """)]
