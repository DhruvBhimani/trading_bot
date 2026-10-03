# Execution direction and reference review

Reviewed 2026-09-29. User priority: actual liquidity-pool execution, Phantom wallet,
local storage, free infrastructure where possible. Cached market snapshots are not
an execution feed. No code from these repositories was installed or copied.

- https://github.com/trading-toolkit/zerosniper — useful terminal/feed/status ideas.
  Its README describes cached market endpoints and snapshot-based calculations;
  do not mistake its WebSocket relay for a direct on-chain trade feed.
- https://github.com/DoradoDevs/solana-wallet-pnl-tracker — useful transaction
  checkpoints, pre/post token-balance reconciliation and FIFO accounting design.
  Read-only tool; not an execution backend. Wallet-wide PnL remains future work.
- https://github.com/mrarindam/TokenSight-Ai — useful separation of pool liquidity,
  identity, risk evidence and swap controls. Uses Jupiter swaps. Scores are not
  guarantees or a validated strategy.
- https://docs.gmgn.ai/index/cooperation-api-integrate-gmgn-solana-trading-api
  now directs integration to GMGN OpenAPI. Do not depend on older undocumented
  website endpoints. Axiom/GMGN are possible future adapters; neither is integrated.
- https://www.youtube.com/watch?v=5SF-Fdmx6kA — transcript reviewed for product
  workflow: discovery → checks → entry → positions → exits. Its performance,
  audit, latency and protection claims were not independently verified.
- https://pumpsnipe.org/ redirected to Google in the web fetch. No software or
  wallet integration from this site was used.

Implemented execution path: Jupiter Swap V2 aggregator pool route → Phantom
signature → unchanged-message/signature validation → RPC simulation → submit →
RPC status and balance-change receipt, persisted locally. Live read-only routing
was verified; no real-wallet transaction was signed or submitted. Current server
submission defaults off. The manual path is not an unattended sniper bot.

Remaining infrastructure before that workflow is complete:
1. Continuous Solana pool/trade event subscriptions with reconnect, gap recovery,
   deduplication, raw event retention and decoded trades; build short candles from
   those trades. No fallback that silently substitutes synthetic data.
2. Wallet token inventory and actual fill/cost-basis reconciliation, including
   transfers and unknown outcomes. Receipts exist; full portfolio accounting does not.
3. Token/pool discovery and broader mint support, including explicit handling of
   launch bonding curves versus migrated pools and unsupported token extensions.
4. User-reviewed real-wallet round trip. Submission/signing stays user-controlled.
5. Separate authorization/signing design for unattended orders; Phantom connect
   alone is not permission or a mechanism for automatic signatures.

Existing strategy placeholders remain separate in app/strategy.py. No strategy
optimization, copy-trading dependence or profitability claims are included.

Implementation update: finalized RPC transaction collector and dashboard added.
Verified against an actual Whirlpool address: 20 signatures and two full receipts
retrieved through public RPC. Six new tests cover deduplication, multi-page recovery,
checkpoint persistence, explicit history gaps, retry and receipt storage. Remaining:
WebSocket latency, protocol-aware swap decoding and discovery of newly created pools.
