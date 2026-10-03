# Saved implementation checkpoint — 2026-09-29

User requested stop at 10% remaining in the five-hour Codex window. Check usage
before continuing. Do not use reset credits. Current work is saved in local files;
no Git commit or external deployment was made.

## Implemented today

- Direct confirmed Solana WebSocket discovery for official Pump.fun CreateEvent
  and PumpSwap CreatePoolEvent. Decodes program-scoped events, stores raw event data
  in SQLite, deduplicates signatures/event indices, reconnects, and shows live cards.
- Wallet management: Phantom/watch-only addresses and encrypted local bot wallets;
  create/import, add/remove, passphrase unlock, lock, recovery-key download.
- Bot signing sessions: explicit automation enable; restart locked; one-hour expiry;
  $5 trade cap and $25 cumulative input budget per unlock, plus fees. Signed queue
  jobs use existing quote validation, signature guard, simulation and submission.
  Lock/pause is checked before submission reservation. Already submitted transactions
  cannot be cancelled. Outcomes are reconciled without blind resubmission.
- On-chain SOL and SPL/Token-2022 balance reads, app-order counts/fees and limited
  known-cost SOL-pair cash-flow P&L. External history is not indexed. Unrealized/USD
  P&L remains explicitly unavailable, not fabricated.

## Validation

39 Python tests pass. Node: 7 vault crypto checks, 6 event decoder/provenance checks,
4 transaction-message/signature checks pass. Node syntax and diff whitespace checks
pass. Live public WebSocket subscriptions received actual token and pool creations,
verified in the UI. No funded wallet was imported, no real trade signed/submitted,
and no real-user vault passphrase handled by the agent.

## Runtime

`python3 app/server.py`, http://127.0.0.1:8765, real swaps OFF. Node 22+ required
for native WebSocket. Optional SOLANA_WS_URL and SOLANA_RPC_URL are process env vars.
Public RPC worked in testing, but availability and throughput are not guaranteed.
SQLite: data/local/paper-bot.sqlite3. Live discovery runs while the server runs.
Closing the browser does not stop it. All signing sessions restart locked.

## Remaining, in priority order

1. Real-wallet end-to-end buy/sell verification performed by user, after reviewing
   the signer path. Do not claim production safety or audited security.
2. Confirmed live swap decoding, short candles and continuously updated pool reserves.
   Current discovery shows creation events; it does not follow token prices.
3. Discovery gap backfill and protocol-version coverage tests; current WebSocket
   downtime is disclosed and not silently backfilled. Only two protocols supported.
4. Full wallet indexing, transfer-aware FIFO basis, reliable marks/unrealized P&L.
5. Strategy→order producer and automatic exits: queue/signer are implemented,
   but no live strategy automatically trades newly discovered tokens.
6. Risk checks and supported-token extension handling before broadening the small
   trading allowlist. New discoveries are displayed, not automatically tradable.
7. Independent security review; four moderate transitive SDK advisories were present
   before this turn. No guarantees of rug protection or profitability.

## Secret handling

AES-256-GCM ciphertext with scrypt-derived key is stored in SQLite. Passphrase
exists in server memory while unlocked; Python does not guarantee secure RAM erasure.
Recovery download is intentionally plaintext and user-initiated. Remove clears the
current encrypted key and locks/cancels queued work; SQLite/WAL/older backups may
retain ciphertext. Export recovery before funding/removal. Phantom connect never
provides a signing key to this app. Bot wallet import is a separate explicit choice.

## 2026-09-30 continuation

Implemented `app/market.py` and Pump.fun TradeEvent decoding. Live tokens now have
View live trades controls with 1/5/10/60-second observed OHLC candles, trade links,
SOL/token prices and last observed real reserves. Mint decimals come from RPC;
non-SOL quotes, unknown decimals and zero-size trades are not assigned fake prices.
The stream records trades for up to 100 recently created/selected mints; opening a
chart follows that mint. Chart reads use the most recent 3,000 recorded trades and
120 occupied candle buckets, leaving gaps empty. The decoder now discards events
from failed nested calls. Candles are confirmed observations, not finalized history;
downtime gaps and reorg reconciliation remain future work. PumpSwap trade decoding
is not yet implemented (pool creation is).

Signer hardening: queued jobs are bound to the unlock session that created them;
a later unlock cannot authorize old queued jobs. No funded signing was tested.

Validation: 45 Python tests, 8 event/provenance checks, 7 vault crypto checks and
4 signature checks passed. A live read-only probe decoded four real trades,
verified six mint decimals through RPC, and generated a 1-second candle.

## Strategy direction and token-card metrics — 2026-09-30

Read docs/strategy-direction.md before further strategy work. It preserves the
user's fee/valuation, low-SOL holder, bundler and wallet-graph hypotheses and
prioritizes verified post-migration recovery. config/research-direction.json is a
research-only configuration, not executable trading rules. Model improvements
require time-ordered paper validation; no automatic live promotion.

Cards now include SOL-denominated estimated cap/FDV, observed volume, buy/sell counts,
protocol/creator fees and real SOL reserves, plus GMGN token-chart links. Values use
on-chain events; lifetime totals, circulating market cap and USD marks are unknown.
The launch decoder retains initial raw supply for FDV. market.py stores deduplicated
running metrics and versioned feature-memory records for future paper-learning data.
It is not a trained model. Restart starts fresh metrics for earlier records that
predate the new aggregation; coverage is shown from first aggregated observation.

Validation for token-card metrics: 48 Python tests and 8 decoder checks passed;
frontend JavaScript syntax and diff whitespace checks passed. Live UI verification
was blocked because the user declined the server restart. The old process was
already stopped. Start `python3 app/server.py` to load the changes; real swaps remain
off by default. Do not claim the new metrics UI was visually verified this turn.
Last usage: five-hour 51% remaining, weekly 14% remaining. Stop threshold is 10%.

## Paused at usage cutoff — 2026-09-30

Latest usage: five-hour 17% remaining, weekly 9% remaining. Stopped to respect
user's repeated 10% cutoff. No implementation changes for this latest request.
Local data directory measured approximately 47 MB; existing data was not deleted.
IMPORTANT: current live collector still persists market/launch/feature data to
SQLite. User now explicitly requests no ongoing bulk local market-data storage.
Next session must address this first: use bounded in-memory live market state,
preserve wallet keys and required execution audit records, and explain that the
running process must reload changes before disk writes stop. Do not claim storage
is already disabled. User prefers to run/verify dashboard themselves; no browser
verification or unsolicited dashboard restart.

Pending UI requests from latest screenshot:
- Compact chart layout, readable current SOL price and estimated cap/FDV.
- Compress inactive candle intervals, clearly label compressed time; do not invent
  trades or imply uninterrupted observations.
- Load new tokens appends highlighted cards and scrolls to newly appended end.
- View live trades scrolls back to the chart.
- Clear cards starts a fresh live feed without repopulating historical API events.
- Add explicit Pin/Unpin controls without moving other cards.
- Keep strategy work deferred during these fixes.

## Session cache and live UI implementation — cutoff stop

User clarified cutoff applies to FIVE-HOUR allowance. Latest reading: 9% remaining;
stopped immediately after syntax checks, before functional/browser testing.
Changes saved: app/live_store.py RAM-only SQLite cache, 200 launches/12,000 trades,
200 metadata/receipts caps, no feature-history accumulation, startup cleanup of
legacy live-cache tables (VACUUM), persistent wallet/paper records preserved.
server.py wires Chain/Discovery/Market to LiveStore and adds discovery/clear.
Frontend adds Clear, Pin/Unpin (10 cap), 120-card trimming on Load new,
new-arrival highlight/scroll, chart selection scroll, compressed observed candles,
responsive SVG coordinates, price/FDV headline, zoom/earlier/latest buttons.
Syntax: node --check and Python py_compile passed. No runtime tests or restart.
No process listening on 8765 was returned by lsof at final check.
IMPORTANT follow-up before claiming fully tested:
- Clear currently clears DB but does not reset Node tracked-mint set; old followed
  mints can refill trades after clear. Add reset command and stale-event barrier.
- Pruning removed cache metadata may cause unavailable FDV for old cards; surface
  expiry accurately. Pinned cards only retain UI, not perpetual backend history.
- Verify refresh/clear race behavior, card cap and chart controls with user screenshots.
- Existing backup DBs are untouched; startup cleanup targets active DB only.
- Usage cutoff prevented retention and endpoint regression tests.

## Pinned tab, session cleanup and valuation coverage — 2026-09-30

Implemented latest request. Pins move cards to separate Pinned coins tab (10 max).
Clear preserves pinned cards/data, removes unpinned cards/cache and pauses/reset
session chain watches. Unpin returns card to normal feed; subsequent Clear removes
it. Pins remain session-only and disappear when server exits. Frontend caps normal
cards at 120 and pending arrivals at 200; backend retains 200 recent mints + pins,
12,000 trades, 200 chain receipts. Feature-history accumulation stays disabled.
Generation barriers reject queued events and in-flight metadata results after
Clear; Node reset keeps only pins and their pool mappings. Worker exits on parent
stdin closure, bounds its outgoing queue and reports dropped-event gaps.

Custom live SVG chart and zoom buttons removed per user's allowed fallback.
GMGN chart links remain, plus live detail price/FDV and recent trade list. Full
TradingView chart was NOT implemented. Cards update every two seconds without
replacing action buttons; all retained coins' metrics are included, not just 80.
Pinning protects tracking and prioritizes missing token metadata lookups.
Verified mint supply/decimals batch RPC unlocks missing FDV/price. PumpSwap SOL
Buy/Sell event prefixes and session pool mapping added from official IDL. Values
are SOL-denominated last observed trades, with age and partial-session coverage.
No price is claimed for no-trade, unsupported-quote or unobserved-pool cases.
Metadata RPC failure/backoff status is visible; no snapshot-price provider added.

Validation: 58 Python tests passed (including actual temporary HTTP pin/clear
routes, stale event/RPC barriers, retention and wallet-record-preserving cleanup).
Node session reset/pin/retention, AMM normalization/decoding and eight existing
creation/provenance checks passed. JS syntax passed; static literal element refs
all resolve. An existing duplicate connect-wallet HTML id remains outside this
change's scope. Browser/UI not inspected or server restarted per user preference.
Current data/local size measured 304 KB. Source changes require server restart.
Legacy live-cache tables in the active SQLite DB are removed/compacted at startup;
wallet/paper records and historical backups remain untouched. No funded trades.

## RAM lifecycle controls — 2026-09-30
Added per-card Discard + discovery/discard API: deletes mint cache rows, drops
worker tracking/pool mappings, rejects late observations (bounded 1,000-address
recent-discard set). Pins must be unpinned before discard. Maintenance expires
unpinned launches after 15 minutes, even without incoming events. Existing caps
remain 200 recent + 10 pinned mints and 12,000 trades. Live cache panel displays
used/allocated SQLite pages and zero disk bytes; explicitly NOT total process RAM.
Clear-unpinned retains pins; shutdown clears RAM. No temporary disk DB introduced:
existing bounded memory cache avoids crash-leftover files and disk growth.
11 cache lifecycle tests and Node session tests passed; JS syntax and whitespace
checks passed. Dashboard not restarted or visually inspected. No strategy exists
to automatically decide rejections yet; future strategy should call discard.
Recent discard suppression is capped at 1,000 mint identifiers, not permanent.

## Pause new cards — 2026-09-30
Added session-only Pause new cards / Resume new cards toggle. Blocks initial
unpinned admission and Load new tokens while paused; existing metrics and backend
scanning continue. Pending discoveries remain bounded at 200 and expired entries
are removed. Resume enables manual loading without forcing cards or scroll.
Pins still survive normal retention; pause alone does not defeat memory expiry.
No strategy/auto-entry behavior added: the current backend scans, but is not an
autonomous opportunity-selection strategy. JS syntax and whitespace checks passed.
UI not opened/restarted, per user's preference.

## Live paper selection and execution — 2026-09-30

Implemented autonomous screening into separate momentum and migration-recovery
virtual accounts. Fresh mapped PumpSwap SOL trades and verified mint/freeze
authorities are required; recovery also needs matching observed migration, dip
and rebound. Bonding curves are monitored but not simulated for trading yet.
Delayed subsequent-event fills include reserve-based price impact, fees and
slippage. Failed/stale exits retain positions; entry pause continues exits.
Open/pending coins are protected from Clear, discard and worker retention.
Restart restores positions and pool context with new entries paused.

Dashboard adds balances, screening reasons, positions, exits, closed trades,
frozen config, new runs, export and guarded clear. Defaults are 10 virtual SOL
per strategy, 0.1 SOL size and two positions each. Compact records use a separate
SQLite file capped near 50 MiB, with bounded decision/trade/version/run retention;
raw live observations remain capped RAM. No automatic training or promotion.

Validation: 77 Python tests passed, including offline adapter-to-paper entry/exit
and HTTP controls; Node decoder/session tests and frontend syntax checks passed.
Additional pool-map pressure regression preserves protected position mapping.
No browser opened, server restarted or real wallet trade sent. User should restart
with python3 app/server.py, refresh and click Start live paper. Live RPC coverage
and UI appearance still need user verification. See docs/live-paper.md for model
limits and storage controls.

## Missing scores / inactive candidate screen — 2026-09-30

User screenshots show paused entries and unknown scores with no pool observations.
Fixed known-token migration promotion into pool context, pool-first metadata
lookups and bounded pool reservation against launch bursts in both adapters and
worker tracking. Existing other-pool mappings cannot inherit migration evidence.
Candidate view now uses fresh features instead of unchanged frozen audit rows;
bonding-curve launches are summarized separately so they do not bury pools.
Added feed counters, last evaluation, metadata status, prominent paused reminder
and separate decimals/no-trade/stale reasons. Scores remain unavailable until
observed data exists; no fabricated prices or forced trades.

81 Python tests passed; Node session pressure/migration regressions and frontend
syntax checks passed. No browser opened or server restarted. Attempted read-only
localhost diagnosis found no server listening, so live feed remains unverified.
Restart server, refresh UI, click Start live paper; user supplies screenshots.

## Active-pool discovery gap — 2026-09-30

User screenshot showed one migration, no mapped trades and entries enabled.
Confirmed a real PumpSwap transaction decodes successfully; previously the worker
rejected unknown pools unless their creation was seen in the current session.
Added capped on-chain pool identity resolution for incoming swaps; verifies owner,
discriminator and SOL quote, then normalizes buffered observed trades. Prices
remain event-derived; no price snapshot provider. Migrations no longer overwrite
an existing pool quote mapping (including native-SOL sentinel mismatch).
Lookup queues and retries are bounded with generation barriers and RPC backoff.
Existing pools are identified as observations, not newly created tokens.

Real-chain fixture tests cover decoding, verified identity, normalized sell,
quote preservation, wrong owner/discriminator, Clear race and queue/backoff caps.
A 25-second isolated read-only worker test observed 14 launches, 72 pool identities
and 482 trade events, exit 0, no worker errors. This includes bonding-curve trades;
it is not a full funded execution or dashboard check. Dashboard server was not
started/restarted. Restart server, refresh and enable paper entries to load fix.

## Stale reporting, read-only quotes, trade analysis and memory — 2026-09-30

Implemented separate last-observed/conservative values with age and feed-health
classification; no stale-equals-rug claim. Current positions preserve their pool
mapping. Added an independent quote-only Jupiter worker (no taker, signing or
submission) with validated mint/amount/minimum output, expiration, rate limits,
small sanitized response records and 500-record retention. Compares reserve
model with entry/sell routes without altering paper balances or fill accounting.
Quote-only SOL/USDC call succeeded keylessly; no wallet supplied or funds used.
Added modeled cost breakdown, hold/delay/best/worst/failed exit details and current
run aggregate analysis; streams records instead of retaining another JSON history.

Live-cache hard page ceiling 32 MiB, pressure trimming above 24 MiB, reserved
position trades, plus server/worker RSS soft guards with hysteresis. At high RSS
clears unpinned data, pauses admission/entries and cancels buys; open positions,
pins and exits remain. Runtime/browser overhead is outside the hard cache cap;
process measurements may be unavailable or briefly spike between samples.
Worker pool map also remains bounded under repeated pools for protected mints;
lookup/stream response sizes and pressure queues are capped.

Validation: full Python suite 91 tests passed; an additional alternate-pool
protection regression and its 17-test cache suite passed after that. Node real
fixture/resolver and session/pressure/bounds checks passed; JS syntax and diff
whitespace passed. No browser opened or dashboard restarted. User should restart
python3 app/server.py and refresh. Machine-learning training remains future work.

## Continuous scanner redesign — quota stop at 10% remaining

Latest user rejected the memory pause: screenshot showed cache 0.1 MiB, Python
44 MiB, Node 233 MiB. Replaced RSS-based entry/admission pause with continuous
bounded candidate rotation. Removed wallet SDK/native fetch stack from scanner,
using bs58, ws with 256 KiB payload cap/no compression, bounded node:https RPC,
and --max-old-space-size=96. Existing dependencies promoted to direct dependencies
in package.json/lock (offline npm lock attempt missed cache; no install required).
Worker automatically reconnects after failure, restoring generation, pins and
protected pool mappings. Sustained RSS >384 MiB recycles worker, not paper state.
Python pressure trims cache but never latches entries off. Feed gaps remain
possible; indefinite flawless operation is not a guarantee.

Focused worker skips early launch storage, watches up to 16 near-migration
candidates from SOL TradeEvent remaining/virtual token reserve ratio <=10%
(heuristic, not guaranteed migration), and 64 active/migrated pools plus protected
positions/pins. Candidates have 60-second observation leases and rotate after
120 seconds; rejection cooldown 60 seconds, bounded 256 identifiers. Paper hard
rejections and prolonged missing data release cache/worker tracking. Existing
pools are discovered from incoming swaps, including those predating startup.
Canonical migrated pools are verified by owner/discriminator + standard Solana
PDA derivation for Pump.fun pool-authority and PumpSwap index-0 pool. Recovery for
an older verified pool begins its observed dip/rebound window at discovery;
actual historical migration time is not invented. Canonical proof tested against
real-chain fixture and invalid creator/address; uses lightweight noble curves.

Event payloads compacted, per-token trade retention 180, global pruning amortized
for trades. Telemetry reconciles backend candidates with the worker, with clear
generation protection. Optional live-card tab hidden and startup card fetch
removed; main UI shows continuous scan counters. Closed-trade table now filters
to current run, matching summary; old runs remain in exports.

Verification: 95 Python tests passed, Node decoder/real-chain pool/rotation tests
passed including 10,000-candidate churn. Lightweight worker broad-feed soak ran
180s, RSS settled ~153 MiB. Focused full-path scanner + temporary virtual paper
account soak ran 180s: running stayed true, worker ~150.5 MiB, cache <=0.91 MiB,
34,713 pool events and 7,683 curve trades screened, 74 early creations skipped,
39 rotations, 155 rejection/rotation releases, 1 closed paper trade and 1 open,
no errors. Tests used temporary isolated records; no dashboard/server restart or
wallet trades. Canonical-pool proof and amortized pruning were added after that
soak started and covered by offline tests. Automatic subprocess restart still
needs a deliberate fault-injection test in a later session. User should restart
python3 app/server.py and enable live paper once. Browser verification remains
with user. Stopped at exactly 90% used of 5h allowance. Sources saved locally.

## 2026-10-01 — trade details, token names, valuation visibility

- Closed-trade DOM rows now use run ID + trade ID and are reused across polls. An expanded details panel stays open for unchanged polls, new arrivals, and name updates; user collapse remains respected. Retained rows stay bounded by the 40-trade response. Details text wraps.
- Paper positions show entry/current MC / FDV and fill/current trade prices. Closed trades show entry/sold MC / FDV outside the details panel, with fill prices inside. All valuations are in SOL and use observed trade price × verified total supply, **not circulating market cap**. Entry and exit estimates are frozen when filled. Stale current estimates are unavailable with last-known valuation separately labelled. Older records without valuation fields remain unavailable; no historical cap is fabricated from today's supply.
- Names/symbols resolve from verified Metaplex metadata PDA accounts or Token-2022 mint metadata. Owner, mint, type/discriminator and lengths are checked; no token URI is fetched. Launch names remain usable. Name resolution also covers the most recent 40 closed records after live-cache eviction; only identity fields are updated, not trade features/results. Cache and retry maps cap at 256 each, lookups batch at 20 with 60-second failed-lookup backoff. No new dependencies.
- Supply/decimals enrichment refreshes verified supply rather than preserving launch fallback forever. Paper features include supply observation time.
- Candidate rows show estimated cap. Coverage reports fresh valuation range, unavailable count, and counts above 1K / 10K SOL FDV. These are reporting buckets, not new trading filters. Existing strategies have no cap ceiling, but only observe supported PumpSwap SOL pools; Raydium/Orca/all-market coverage is NOT added. No profitability claim or strategy parameter changes.
- Validation: full 102-test Python suite passed after initial implementation, then additional real Token-2022 and context tests plus affected suites passed (4 name, 8 market, 21 live-cache tests; paper suite 25). DOM harness covers repeated refreshes, arrivals, metadata changes, user collapse and bounded row retention. JS syntax and diff whitespace checks passed. Public read-only mainnet fixture verified Super Accelerationism (s/acc); metadata PDA derivation also matched the installed Solana SDK. No dashboard/browser launched and no running user server restarted.
- User must restart server and refresh browser to apply backend + UI changes; Start live paper resumes entries. Existing rules/results are preserved. User performs visual screenshot verification.

## 2026-10-01 — simplified dollar desk and signal entry ceiling

UI now defaults to equal-size strategy summaries, compact open-position cards (strategy, entry/current dollar MC, USD P&L, exit plan), compact closed trades (entry/exit MC, USD profit), and scanner counters. Strong candidates (top eight, score >=65 or eligible) and recent skipped/waiting decisions are collapsed. System/model explanations are collapsed. All trade rows and position cards use keyed DOM updates; details remain open across polls. SOL is shown only as aggregate strategy P&L on the main desk.

`app/usd_reference.py`: free public Coinbase SOL/USD spot reference, 30s polling, 90s freshness, strict response/amount checks, 16KiB response and 5s timeout. Separate background worker; no token snapshot prices. New entry/exit caps freeze dollar values when a fresh reference exists; USD P&L is SOL trading profit converted at mark/exit reference, excluding SOL/USD movement. Older missing USD fields may be converted at the current reference and prefixed ≈. Stale reference never silently used. Entry/exit/price data remains available in exported records even though hidden from the default UI.

Scanner/execution changes:
- Paper evaluation wakes from a bounded Event on incoming trades, coalesced 200ms; idle timer <=700ms. Existing next-event execution delay, stale data, allocation and cost guards remain. Pruning amortized to five seconds.
- Mint verification wakes on discoveries and prioritizes recently active pools; names run separately so slow cosmetic RPC cannot block decision metadata.
- Unknown-pool resolver no longer moves repeatedly active pools to the back. Batches prioritize activity/freshness and handle up to 20 pools; request cadence remains 3s. Pending buffer stays <=100, 8 events/pool; high-activity candidates survive queue overflow preferentially.
- Qualifying signal anchors survive account waits and entry rejection. A pending paper buy must still pass its strategy and cannot exceed 110% of the original signal price (observed and modeled effective fill), SOL FDV, or USD FDV where both references exist. Existing adverse-fill limit may be stricter. Continued same signal cannot reset its anchor upward after a rejection. Reset only when conditions cease qualifying or candidate is released. These are bounded per-current-candidate records, not unbounded history.
- Entry execution policy recorded as `signal-ceiling-v1-10pct`; strategy configs/history remain otherwise unchanged. New records keep signal-to-entry seconds and entry move %. No funded execution added. The ceiling can cause skips, not guaranteed fills or profits.

Validation: full 109 Python tests passed, followed by affected paper tests after pruning optimization. Node pool priority/bounds tests, candidate/session tests, full USD renderer against real HTML IDs, details preservation, JS syntax and diff checks passed. Public Coinbase endpoint verified read-only. No user dashboard opened/restarted. No post-change live throughput/latency benchmark performed; user should restart server, refresh, Start bot and inspect new timing records. Coverage still PumpSwap SOL pools; this is not an all-DEX or zero-latency guarantee.

Learning remains future work: retained compact decisions/results -> versioned candidate rules/model -> chronological out-of-sample paper validation -> controlled promotion and rollback. Existing logs do not mean a self-training model exists. Before real funds, measure feed/entry latency and modeled-fill realism and validate wallet execution/recovery.

## 2026-10-01 — live verification and first learning observer
User authorized using beyond the usual 10%-remaining cutoff for THIS allowance only. Future sessions retain the 10% stop rule.

Added reproducible `scripts/check_scanner_live.py`: isolated temporary paper DB + real public WS/RPC, 180 seconds, own worker terminated halfway. Completed with no errors, worker recovery true, paper enabled throughout; 10 closed + 1 open temporary trades. Worker RSS 108.2–114.3 MiB, live cache peak 4.27 MiB. Tick computation median 40.9ms / p95 52.1ms (NOT chain-to-fill latency). Closed-trade signal-to-entry times: nine ~1.25–2.72s and one 12.74s. That slow entry still needs investigation; no uniform latency promise. Report `/tmp/db-bot-scanner-check.json`. No actual user server, wallet or existing DB touched.

Added `app/paper_learning.py`: bounded 300-record training window, minimum 40 trades/20 coins per strategy and matching baseline version/execution policy; simple score/liquidity filters only. Creates frozen research versions when subset evidence qualifies. Evaluates later-entered, unseen-mint trades only, records progress and avoids double counting. Max20 versions inside existing capped paper DB; exported and included in Clear results. UI collapsed Learning lab. Does NOT alter active strategy, rerun counterfactual portfolio fills, auto-promote, or train a general model. Closed-trade selection bias / open losses remain limitations. A coverage warning is saved if records exceed its retained evaluation window. Different coin/time checks and frozen versions passed unit tests; 29 paper tests and complete UI renderer also passed. Full suite was NOT rerun after learning additions. Added learner job independent of name-lookup failure (runs from existing background thread with 60s throttle). No external packages.

User follow-up asks what remains for continuous training, decisions they must make, and behavior on server stop. Explain: compact trades/checkpoint/learning versions persist; raw cache gone, no offline learning/market capture; entries restart paused and learning resumes automatically after server restart, versions remain. Next: prospective candidate portfolio simulation with costs, chronological validation incl open/stale positions, selection/execution latency and outcome diagnostics, configurable bounded risk and paper-only promotion/rollback. Profitability cannot be promised. User controls risk/markets/paper auto-promotion/live deployment; routine fitting should be automatic. Continue after quota renewal, preserve old 10% cutoff except explicitly authorized current allowance.

After allowance renewed (3% used), normal 10% cutoff reinstated. Added entry timing breakdown (signal-to-queue, queue-to-fill, event-to-evaluation) and compact UI details; prior 12.74s example cannot be retroactively attributed because it lacked the breakdown. Research errors now show in Learning lab and cannot pause paper trading; retries throttled60s. Added persistent database restart test and anti-recounting test for learner. **Full113 Python tests passed**, along with complete USD UI renderer and diff/syntax checks. `docs/continuous-learning.md` covers working observer, remaining prospective portfolio/validation/promotion work, user controls and server-stop persistence. User server remains untouched and needs restart to load changes. No active learning version auto-applies trading changes.

## 2026-10-01 — XGBoost training and independent paper comparisons
User authorized implementing the learning layer. Normal stop-at-10%-remaining rule applies; last quota check87% used/13% remaining. Stop now rather than crossing the threshold. No user server/browser restarted; no wallet execution enabled.

Implemented app/ml_model.py (bounded portable predictor), train_paper_model.py (native XGBoost subprocess), ml_research.py (scheduling, persistence, validation and watchdog); integrated with LivePaper and a separate two-second server learning thread. UI Learning lab shows eligible progress, model state and comparisons. Only signal_features captured at queue time from new baseline trades train the model; older fill-only features do not qualify. Frozen candidate + fresh baseline control have independent balances, same start/exclusions/risk/costs; at most4 accounts/8positions total. All fitting/holdout coins excluded from both arms. ML is an extra entry filter, not learned exits or automatic promotion. Models survive restart; entries restart paused. Clear paper results removes model history too and confirmation now says so.

Training:200trades/80coins minimum per baseline version, last500 source rows; chronological70/30 split, embargo overlapping outcomes, disjoint coins, fresh holdout on subsequent attempts; minimum120/50 train and40/20 validation. Fixed2% predicted-return filter, selected>=20trades/10coins, positive under extra1% cost and higher average than unfiltered holdout. Shallow48trees depth3, one compute thread. Retrain hourly after50new outcomes. One process, CPU30/35sec, wall60sec, sampled512MiB RSS guard; failures do not pause scanner. Independent prospective comparisons last<=24h entries or50closed perarm after1h; never discard unresolved inventory; archive onlyflat. Six latest models plus active version,20comparison summaries in existing50MiB DB cap. Baseline-only closed-trade training selection bias remains; prospective outcomes for skipped opportunities, promotion/rollback, broader strategies and real execution calibration remain future work.

Dependencies installed locally in ignored research/.venv-ml (154MiB):xgboost2.1.4,numpy1.26.4,scipy1.13.1. Mac libomp from checksum-verified Homebrew public bottle copied inside venv, local XGBoost dylib relative rpath and ad-hoc signature applied; no global/Homebrew install. License and reproducibility details in docs/continuous-learning.md. No heavy model imports in live process. Native/portable predictions verified<=1e-6, including float32 split threshold correction.

Final verification: full127Python tests passed with2native-only tests skipped in system Python; all9ML tests passed in venv, including the2native tests. Actual subprocess training tested on synthetic data. Complete UI DOM/render tests, JS syntax, Python syntax and git diff whitespace checks passed. No live market profitability claim or post-change live soak. Next user step: restart server, refresh, Start bot, watch Learning lab gather new eligible signal records. Candidate appears only when data and validation pass. Docs fully updated. Preserve unrelated pre-existing workspace changes; no commit made.

## 2026-10-02 — skipped-coin outcomes, calibrated classifier, $50 paper entries
User requested broader learning data, careful labels/calibration/time validation, gated promotion, paper exploration, loss review, $50 entries, removal of forced max-hold exits, and resolution of stale/untradeable paper positions. Implemented locally; actual user server/dashboard/database not restarted or modified by tests. Restart required. No real swaps enabled.

Config/live-paper.json now rules-v2 / paper_policy_revision2, size_usd50, max_hold_seconds0, unresolved_after_seconds180, exploration_fraction.05. New order SOL principal =50/fresh SOLUSD, frozen at queue; network cost additional. Entry size/pool/risk guards retained. Existing checkpoints migrate requested settings once, preserve balances/history/open positions, annotate prior entry version, cancel obsolete max-time pending exits, and finish old comparison arms without new entries. Do not scale old positions retroactively. USD absence blocks new order sizing, not exits.

Added app/opportunities.py: census before Node shortlist admission (creation/pool/migration), bounded2048 queue/overflow counters/128char strings. Up to10000 seen tokens. Priceable tracked pools get up to3 frames/version spaced30sec. Record immutable decision-time features and follow +25% before-12% over60sec. Targets positive; stops/covered timeouts negative. Receipt gaps>10sec, disconnects, eviction and restart censor outcomes. No quiet-token=rug inference. Frames begin AFTER capture, excluding already-known late block events; gaps after deadline cannot invalidate earlier covered horizon. Labels based on observed paths, not executable fills. Queue/capture errors visible; SAVEPOINT rollback isolates observation failures from paper evaluation. Terminal6000 +pending512 frame cap, pressure lowers retention. Existing50MiB paper DB cap; raw events remain RAM-only.

Added app/train_opportunity_model.py: XGBoost binary classifier with separate chronological60/20/20 fit/calibration/test, purged overlaps and disjoint mints, fresh test data on retrains. Regularized sigmoid calibration via existingSciPy; saved reliability bins/Brier metrics. Gate requires200usable outcomes/80coins (NOT200executed trades), postpurge80/40fit,30/15cal,30/15test. Expected scenario value p*.25+(1-p)*conservative failure loss minus modeled current cost; fixed2% selection threshold. Holdout must improve Brier vs calibration prior, selected mean vs baseline, survive1% extra cost and positive results in both later halves (>=8selected each, >=20total/10coins). Classifier risk is observed target chance, not calibrated rug probability or guaranteed executableEV. 500-source-frame training bound, existingresource watchdogs. Regression versions readable; new live schedule uses opportunity classifier. Candidate remains additive to momentum rules; recovery baseline remains separate. No automatic promotion or wallet execution.

Added observed unique buyers and10sec buyer-arrival rate from decoded trade user identities, retained in capped raw cache and compact frames. These are observed addresses, not humans; creator history/holder concentration/bundle evidence remain unavailable. ML candidate explores a stable5% hash sample of rejected model signals, max1exploration position/pending atonce, all base/risk guards apply, no per-tick reroll. Corrected worker protected-mint cap4->8 for fourpaper accounts.

Stale positions: after180continuous seconds of healthy feed elsewhere with nofresh token trade, retire as zero-recovery unresolved PAPER write-off. Globalfeedgap resets timer. Manual stale-only Retire as paper loss also provided. No sale/noexitprice/no cashrefund; quantity/evidence retained in writeoffs table(max1000), conservative loss hitsdaybudget; netequity consistent, realizedsales separate. Releaseactive slot/protection, do not feedasverifiedruglabel. UI hascollapsed unresolvedlosses andlossbreakdown (age/pool/score/exitreason/exploration; holdersunknown). $50newentrylabel andNo time limit replacecountdown. LegacyAPI records/models exports includeopportunities,census,writeoffs; Clear paper results removesall; Clear livecards separate.

Validation: full145tests passed in MLvenv (including native classifier/regression, no skips), Node session/8protected andUI tests passed. Subsequently added2time-boundary opportunitytests +capture-failure isolation: all8opportunitytests and44paper tests passed, UI passed again. Python AST/JS syntax and whitespace checks passed before those small final edits; no syntax issues in imported/tested files. Two-minute isolated real feed soak: noerrors,reconnect recovered,paper remained enabled,$50configured,5closed+1open virtualtrades,521seen coins,210frames,10barrierlabels,154censored,46pending,0queue drops. WorkerRSS106.5–112.2MiB/cache<=4.3MiB, tickcompute median41.55ms/p9555.68ms (notchain-to-fill). Mostqueuedfills1.03–1.43sec;one12.4sec signal-to-fill included11.36sec prequeuewait. Report /tmp/db-bot-learning-scan-check.json; tempDBremoved. This test is notprofitability evidence and excludedpaths exposecoverage limitations. Soak preceded last two label-boundary fixes/capture-savepoint; those gotoffline targetedtests. UserserverneedsrestartthenrefreshStartbot; no manualdatasetimportneeded.

Docs/continuous-learning.md rewritten forcurrent pipeline/limits/restartsemantics; sources updatedUSDreference nowpaper-sizing too. Futurework: broader reliablecoverage, independentlyverifiedwallet/rugfeatures, longerprospectivecomparisons/explicitpromotionandrollback, learnedexits,realexecutioncalibration. RLremainsdeferred. Do not claim infiniteRAMstability,instanttraining,all-DEXcoverage orprofitability.
