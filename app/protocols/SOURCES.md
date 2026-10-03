# Event decoding sources

Pump.fun and PumpSwap schemas use the official Pump public IDLs:
- https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump.json
- https://github.com/pump-fun/pump-public-docs/blob/main/idl/pump_amm.json

PumpSwap BuyEvent and SellEvent prefixes were refreshed on 2026-09-30, through
coin_creator_fee. The worker associates those events with CreatePoolEvent records
observed in this session. Only SOL-quoted pools are normalized into SOL prices.
Unknown pools, unsupported quotes and missed logs have no fabricated price.
These offline decoder tests verify schema handling, not comprehensive live RPC
coverage. Slot-confirmed observations and their timestamps are shown in the UI.

CompletePumpAmmMigrationEvent was added from the official pump.json IDL on
2026-09-30. Recovery requires the observed migration pool to match the traded
pool. Decoder tests and an offline adapter-to-paper integration test cover this
association; they do not establish complete migration coverage on live RPC.

Pool account identities use the official pump_amm.json Pool discriminator and
stable account prefix (base mint, quote mint). The lookup verifies program owner,
account discriminator, non-executable data and SOL quote. It fetches no market
price. Unknown swap pools are resolved in batches capped at 10 every 3 seconds,
with 100 queued pools, 8 buffered events per pool, 500 retry identifiers and RPC
backoff. Clear generations reject in-flight results. Creation observations and
verified pool identities both support the worker mapping; migration cannot
replace an existing verified quote mapping.

fixtures/pumpswap-observed-sell.json records confirmed transaction
2KuTdRmVfCNvGXVYCN9ZyhvTxYMLZVhKX1QDgoUK6dPh5125PZ1EiWRtyy3b1J9vT8hsMrBykT4LQEc2abcTCReC
at slot 452185243 and its verified pool account. This regression exercises real
logs through normalization rather than only generated event layouts.

### On-chain token names (2026-10-01)
- Metaplex metadata account layout and PDA seeds: https://github.com/metaplex-foundation/mpl-token-metadata/blob/main/clients/js/src/generated/accounts/metadata.ts
- Token-2022 JSON-parsed metadata extension: https://github.com/anza-xyz/agave/blob/master/account-decoder/src/parse_token_extension.rs
- `app/fixtures/token-2022-name.json` records a public confirmed mint account and its RPC context slot. Name data is display metadata, not a verified brand identity. No URI content is fetched.

### USD display reference (2026-10-01)
- Public endpoint: https://api.coinbase.com/v2/prices/SOL-USD/spot
- Coinbase's SDK documents the spot-price interface: https://github.com/coinbase/coinbase-python/blob/master/README.rst
- Reference is used for display/recorded USD conversions, an additional signal cap check, and (since October 2) USD-sized paper orders; observed token prices still come from on-chain events.
