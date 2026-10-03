import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ingestion'))
from postgres_store import configured_url,translate,Row,schema_sql
from market_database import SCHEMA
from migrate_local import copy_data


class HostedConfigTests(unittest.TestCase):
    def test_no_local_fallback_or_credential_echo(self):
        with patch.dict(os.environ,{'DATABASE_URL':'not-a-postgres-secret'},clear=True):
            with self.assertRaises(RuntimeError) as caught:configured_url()
            self.assertNotIn('secret',str(caught.exception))

    def test_generated_ids_and_parameterized_upserts(self):
        sql,generated=translate('INSERT INTO fetches(url,retrieved_at,sha256) VALUES (?,?,?)')
        self.assertTrue(generated)
        self.assertIn('RETURNING id',sql)
        sql,generated=translate('INSERT OR IGNORE INTO tokens VALUES (?,?,?)')
        self.assertFalse(generated)
        self.assertIn('ON CONFLICT DO NOTHING',sql)
        self.assertEqual(sql.count('%s'),3)

    def test_schema_and_row_compatibility(self):
        schema=schema_sql(SCHEMA)
        self.assertNotIn('PRAGMA',schema)
        self.assertIn('BYTEA',schema)
        row=Row({'id':7,'label':'x'})
        self.assertEqual(row[0],7)
        self.assertEqual(row['label'],'x')


# Exercise the migration against two independent relational stores without network.
class MigrationTests(unittest.TestCase):
    def test_repeat_copy_remaps_foreign_keys(self):
        import tempfile
        from market_database import connect,record_fetch,ingest_pools,ingest_candles,status
        from test_market_database import pools,candles,POOL,TIME
        from import_gecko import normalize
        import json
        with tempfile.TemporaryDirectory() as directory:
            source=connect(Path(directory)/'source.sqlite3')
            target=connect(Path(directory)/'target.sqlite3')
            try:
                # Force source and destination generated identifiers to differ.
                record_fetch(target,'other',TIME,b'{}')
                fid=record_fetch(source,'pools',TIME,json.dumps(pools()).encode())
                ingest_pools(source,pools(),fid,TIME)
                fid=record_fetch(source,'candles',TIME,candles())
                ingest_candles(source,normalize(candles(),POOL,'minute',15,TIME),fid)
                copy_data(source,target)
                first=status(target)
                copy_data(source,target)
                self.assertEqual(first,status(target))
                self.assertEqual(first['unique_candles'],1)
                self.assertEqual(target.execute('PRAGMA foreign_key_check').fetchall(),[])
            finally:
                source.close();target.close()


if __name__=='__main__':unittest.main()

class FreeStorageTests(unittest.TestCase):
    def test_collection_stops_before_storage_budget(self):
        from postgres_store import PostgresStore
        class Result:
            def fetchone(self):return {'bytes':295_000_000}
        class Connection:
            def execute(self,sql):return Result()
        store=PostgresStore.__new__(PostgresStore)
        store.connection=Connection()
        store.ensure_capacity(1_000_000)
        with self.assertRaisesRegex(RuntimeError,'storage budget'):
            store.ensure_capacity(10_000_000)
