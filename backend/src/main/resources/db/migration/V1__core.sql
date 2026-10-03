CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE tokens (
    id              BIGSERIAL PRIMARY KEY,
    mint_address    TEXT NOT NULL UNIQUE,
    symbol          TEXT,
    name            TEXT,
    creator_wallet  TEXT,
    created_at      TIMESTAMPTZ,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE token_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    token_id        BIGINT NOT NULL REFERENCES tokens(id),
    observed_at     TIMESTAMPTZ NOT NULL,
    price_usd       NUMERIC(38, 18),
    liquidity_usd   NUMERIC(38, 18),
    market_cap_usd  NUMERIC(38, 18),
    holder_count    INTEGER,
    volume_24h_usd  NUMERIC(38, 18),
    safety_score    SMALLINT,
    features        JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (token_id, observed_at)
);

CREATE TABLE wallets (
    id              BIGSERIAL PRIMARY KEY,
    address         TEXT NOT NULL UNIQUE,
    label           TEXT,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    stats           JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE swaps (
    id              BIGSERIAL PRIMARY KEY,
    tx_signature    TEXT NOT NULL UNIQUE,
    token_id        BIGINT NOT NULL REFERENCES tokens(id),
    wallet_id       BIGINT REFERENCES wallets(id),
    wallet_address  TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    amount_token    NUMERIC(38, 18),
    amount_usd      NUMERIC(38, 18),
    price_usd       NUMERIC(38, 18),
    dex             TEXT,
    block_time      TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_swaps_token_time ON swaps (token_id, block_time);
CREATE INDEX idx_swaps_wallet_time ON swaps (wallet_address, block_time);
CREATE INDEX idx_token_snapshots_token_time ON token_snapshots (token_id, observed_at);

CREATE TABLE backtest_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    strategy_config JSONB NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    summary         JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE backtest_trades (
    id              BIGSERIAL PRIMARY KEY,
    run_id          UUID NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
    token_id        BIGINT REFERENCES tokens(id),
    mint_address    TEXT,
    entry_time      TIMESTAMPTZ,
    exit_time       TIMESTAMPTZ,
    entry_price     NUMERIC(38, 18),
    exit_price      NUMERIC(38, 18),
    pnl_pct         NUMERIC(12, 6),
    exit_reason     TEXT,
    signal_details  JSONB NOT NULL DEFAULT '{}'::jsonb
);
