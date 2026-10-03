CREATE TABLE paper_accounts (
    id              BIGSERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    cash_usd        NUMERIC(38, 18) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE paper_positions (
    id              BIGSERIAL PRIMARY KEY,
    account_id      BIGINT NOT NULL REFERENCES paper_accounts(id),
    token_id        BIGINT NOT NULL REFERENCES tokens(id),
    mint_address    TEXT NOT NULL,
    entry_time      TIMESTAMPTZ NOT NULL,
    entry_price     NUMERIC(38, 18) NOT NULL,
    quantity_usd    NUMERIC(38, 18) NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('open', 'closed')),
    exit_time       TIMESTAMPTZ,
    exit_price      NUMERIC(38, 18),
    pnl_pct         NUMERIC(12, 6),
    exit_reason     TEXT,
    signal_details  JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX idx_paper_positions_account_status ON paper_positions (account_id, status);

CREATE TABLE signal_events (
    id              BIGSERIAL PRIMARY KEY,
    token_id        BIGINT REFERENCES tokens(id),
    mint_address    TEXT NOT NULL,
    observed_at     TIMESTAMPTZ NOT NULL,
    action          TEXT NOT NULL CHECK (action IN ('BUY', 'SELL', 'WATCH', 'SKIP', 'BLOCK')),
    score           SMALLINT NOT NULL,
    breakdown       JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons         JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX idx_signal_events_time ON signal_events (observed_at DESC);
