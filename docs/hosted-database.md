# Hosted PostgreSQL research database

The collector now uses hosted PostgreSQL by default. There is no automatic SQLite
fallback. The old SQLite file is retained solely to preserve the initial download
and support migration. The Neon project `solitary-credit-06176932` is linked on branch `production`.
The project is on the Free plan, in AWS US East 2 (Ohio).

## Free-only setup

The budget is $0. Use the Neon Free plan; do not add billing details or upgrade.
Its published allowance is 0.5 GB database storage per project (checked 2026-09-28).
The collector checks PostgreSQL database size and stops near a conservative 300 MB
application budget, allowing extra room for writes. This check is approximate and
is not a billing control: remain on the provider's Free plan. It does not account
for every provider quota, retained history, or concurrent external writer.
No automatic upgrade or data deletion is implemented.

Sign-in is open at https://console.neon.tech. Once signed in, create a Free project
named `db-bot`, choose a nearby region, and obtain its direct PostgreSQL connection
URL. Account sign-in and credential entry must be completed by the account owner.
Save the URL without showing it in terminal history:

```bash
research/.venv/bin/python research/ingestion/configure_database.py
```

Then use the status and migration commands below. Provider account setup and CLI login are complete. `neon deploy` succeeded with
no infrastructure changes and PostgreSQL as the only utilized service.

## Connect an account you control

Create a PostgreSQL database with a managed provider, or use an existing one.
Use a direct or session-mode connection URL, not transaction pooling: collection
coordination uses a session advisory lock. The account needs permission to create
and use a dedicated `market_research` schema. Existing Java tables in `public`
are not touched. SSL is required by the client.

The CLI has already written `.env.local` (ignored by Git). For a manual setup,
put a direct connection string into a project-root `.env` file:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require
```

The example is a placeholder. Do not paste credentials into chat or commit them.
Use the existing virtual environment, which has psycopg installed:

```bash
research/.venv/bin/python research/ingestion/collect_market.py status
research/.venv/bin/python research/ingestion/migrate_local.py --inspect
research/.venv/bin/python research/ingestion/migrate_local.py
research/.venv/bin/python research/ingestion/collect_market.py run --target-tokens 1000 --days 7
```

The migration reads the previous SQLite file without modifying it, preserves raw
responses and timestamps, remaps fetch identifiers, and inserts into hosted tables.
Repeated migration reuses matching source evidence instead of duplicating it. It
uses the same database lock as collection. Previous local process logs are not
copied; market data and queued collection jobs are.

Connection variables were pulled by Neon into the ignored `.env.local` file.
The collector prefers `DATABASE_URL_UNPOOLED` for schema work and session locking.
See [setup summary](neon-setup-summary.md) for the final migration verification status.
Production migration is verified: 999 candles, 20 pools, and 14 discovered base
tokens. The bulk-download process is not running.

## Storage and future scale

PostgreSQL is the database engine; local versus hosted is the deployment choice.
Hosting does not automatically make individual queries faster. For the intended
shared, persistent research system, hosted PostgreSQL is the initial choice.
Place the collector near the database when deployed; batched candle inserts avoid
one application round trip per row.

The initial research schema preserves raw bytes and candle revisions. With larger
history, measure query latency and storage consumption before choosing time-based
partitioning or an analytics engine. Raw responses and full-resolution event
archives can eventually move to object storage, keeping their hashes and locations
in PostgreSQL. This is future architecture, not implemented infrastructure.

For comparison, 1,000 tokens over 30 days produce up to 2.88 million 15-minute
bars or 43.2 million one-minute bars (before gaps and revisions). Transaction-level
data can be much larger. No free hosting tier should be assumed to hold unlimited
history. Choose provider capacity after measuring row/index/archive sizes.

A hosted database does not make the collector run when your Mac is off. A hosted
worker and schedule would be a separate deployment. No cloud worker, paid service,
or automatic schedule has been created.

References:
- [PostgreSQL partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [Psycopg installation and Python compatibility](https://www.psycopg.org/psycopg3/docs/basic/install.html)
- [Neon connection guidance](https://neon.com/docs/get-started-with-neon/connect-neon)

- [Neon Free plan limits](https://github.com/neondatabase/website/blob/main/content/docs/introduction/plans.md)
