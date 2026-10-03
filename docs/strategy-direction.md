# Research direction — user notes, 2026-09-30

This is durable project context. Preserve these hypotheses and priorities when
continuing the bot. They are not validated rules, safety guarantees or instructions
to trade real funds. Keep learning/paper evaluation separate from live deployment.

## User's preferred opportunities

1. Prioritize migrated tokens that survive an initial selloff and show recovery,
   possible second/third/fourth waves, with sustained liquidity and participation.
2. Study pre-migration entries and exits separately: sell pressure around migration
   and the minority that continue rising. Do not assume every migration sells off.
3. Treat very early / low valuation launches as a separate, higher-uncertainty cohort.
   Do not accept the user's illustrative '99% rugs' or launch counts as measured data.

A new PumpSwap pool alone is not proof that a token migrated from Pump.fun. Join
verified migration events and token identities before assigning migration stages.

## Requested rug-risk hypotheses

- High valuation relative to cumulative fees: investigate valuation/fee and volume/fee
  ratios, age-normalized, with coverage, venue and fee-schedule context. User examples
  were roughly 5, 6 or 10 SOL of fees against a high valuation. These are observations
  to test, not hard labels. Bots pay transaction fees; low fees do not prove bots.
  Distinguish chain transaction fees, priority fees/tips, protocol fees and creator
  fees. Current UI provides only observed protocol and creator fees on SOL trades.
- Low-funded holders: measure the fraction of actual holder-owner wallets with SOL
  below 0.02/0.03, plus wallet age/activity and common funding links. Exclude pools,
  programs, custodians and token accounts; report sampled coverage. Low SOL alone
  does not establish a bot, malicious control or a future rug.
- Bundlers: investigate same-transaction/slot buys, funding relationships, coordinated
  behavior and allocation concentration. Same-slot activity alone is not a proven
  bundle or common beneficial ownership.
- Bubblemap-style connections: funding/transfer graphs and concentrations can help,
  but exchanges, routers and deliberate obfuscation confound attribution. Missing
  links are not proof of independent wallets. No current graph/bundle detector exists.

## Live-first learning plan

No purchased comprehensive historical dataset is required to start. Collect live
launches, migrations, swaps, available risk observations and paper decisions now;
that collection becomes our historical dataset. Include skipped tokens and failures,
not just profitable trades. Keep actual fills distinct from hypothetical fills.

Persist: event identity/time and receipt time; raw evidence and feature version;
coverage/missingness; model/rule version and reason for each decision; simulated
execution assumptions, fees/slippage/delay/failed exits; later outcomes at predefined
horizons and outcome timestamps. Never attach a later-known feature to an earlier
trade decision. Feature memory is implemented; decision/outcome training pipeline
is not yet complete.

Start with interpretable baseline rules, then evaluate a simple supervised model
(e.g. calibrated logistic regression or gradient-boosted trees) if data supports it.
Use time-ordered train/validation/test windows, token-group separation and walk-forward
paper evaluation. Measure net returns, drawdowns, rug recall, false rejections,
calibration and coverage. Compare to fixed baselines and account for fees and latency.
Keep a fixed incumbent model; proposed updates run in shadow/paper mode and must
pass held-out checks before explicit promotion. Never self-modify live risk limits.

Memory enables evaluation; it is not sufficient for profitability. Markets change,
labels can be biased, new samples may add noise, and optimization can overfit.
There is no guaranteed $10/day starting point, monotonic improvement or eventual
perfect model. Optimize validated risk-adjusted results, not a promised daily income.

## Current boundaries

Cards: estimated SOL-denominated FDV from last observed trade × launch supply,
observed SOL volume, buy/sell counts, observed protocol/creator fees, last real
SOL reserves, and direct GMGN chart links. Circulating market cap and USD marks are
not invented. Only supported Pump.fun SOL trades are aggregated; downtime and
tracking limits mean partial coverage. These numbers are not lifetime/global fees.

Earlier next step: verified migration tracking and PumpSwap swap decoding, then paper decisions
and delayed labels, then holder/funding/bundle evidence. Do not call the current
feature-memory table a trained model or claim autonomous improvement.

Sources for distinctions:
- https://solana.com/docs/core/fees
- https://github.com/pump-fun/pump-public-docs


## User clarification: global fees and learning

The user means cumulative token-level **global fees relative to market cap**, as
shown by their trading terminal, not low base transaction fees. Their example is
"400 MC with only 3–7 SOL global fees"; the MC unit and terminal's precise fee
formula are not yet specified. Preserve this as a priority hypothesis and do not
substitute our partial observed protocol/creator totals for the global metric.
Compare like-for-like token ages, stages, venues, fee schedules and capture coverage.
Low ratios can be informative without proving all holders are bots or guaranteeing
that the token will rug. Calibrate against outcomes rather than hard-code certainty.

Why bots fail: weak/decayed signal, biased data and leakage, overfitting, execution
costs/delay/failed exits, adverse selection, position sizing and operational failures.
Lack of retained experience prevents diagnosis, but memory alone is not the main
universal cause and accumulating data alone cannot guarantee improvement.

Learning loop: store decision-time evidence including skipped tokens → paper trade
with realistic execution → attach delayed outcome labels → analyze error cohorts →
train candidate model on older periods → test on unseen later periods → shadow
compare against the incumbent → promote only if predefined net-return/drawdown and
calibration criteria pass. Retain versions and rollback; never automatically relax
risk limits. Model training, outcome labeling and promotion remain unimplemented.

UI verification preference: the user will manually check the dashboard and provide
screenshots. Avoid browser-driven verification/restarts unless requested. Current
card layout uses stable slots, appends new cards below, and retains up to 200 cards
until the user explicitly loads the latest cards. Hover/focus pauses card redraws.

## Continuous improvement requirement (user reaffirmed)

Keep learning after profitability: preserve every model/rule version, its training
window, feature definitions, evaluation results and promotion/rollback history.
Analyze recurring and novel error patterns, propose candidates continuously, and
retain successful incumbents. A single loss does not establish a mistaken decision;
require repeated evidence and unseen-data improvement. Operational failures need
engineering fixes; model updates alone cannot remove liquidity or execution risk.

UI follow-up: selected token now has an independent pinned header/chart; new arrivals
queue behind a counter. Loading new tokens appends up to 40 and never clears existing
cards or changes selection. Pending buffer is capped at 200 recent arrivals; database
history is unaffected. Chart now includes price-axis grid, volume bars and OHLC hover
labels. User provides screenshot verification; no browser/restart requested.

## Live paper milestone — 2026-09-30

Supersedes the earlier next-step and chart notes: the custom chart is removed;
GMGN links remain. Migration events and mapped PumpSwap swaps now feed two
independent experimental paper accounts (momentum and migration recovery).
Decision-time features, frozen rule versions and later outcome labels are saved
in a separate capped paper database; raw live data stays in expiring RAM.
Holder/bundler checks and lifetime global fees remain unknown. Continuous model
training, unseen-data evaluation and automatic promotion are not implemented.
See [current controls and limitations](live-paper.md).
