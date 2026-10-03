# Continuous paper learning — October 2, 2026

## Implemented

New paper allocations target **$50 of SOL at queue time**, using a fresh public SOL/USD reference. The SOL amount freezes on the order; fees and price movement still affect the result. Missing USD reference blocks new USD-sized entries, never exits. The 1% pool allocation and daily-loss limits still apply. Timed holding exits are disabled by default (`max_hold_seconds: 0`); stops, profit target and trailing stop remain active. Existing v1 checkpoints migrate these requested settings on restart while retaining balances, positions and prior entry-version attribution.

The learning dataset now includes skipped coins:

1. Record a compact census of decoded creation/pool/migration events before shortlist admission. No card or trade is required. Keep at most 10,000 recent token records; a bounded 2,048-item queue reports overflow. This is the observed feed, not every token on every Solana venue.
2. For each tracked pool with usable observations, save up to three feature frames per retained coin/version, spaced at least 30 seconds apart. Frames include activity, observed age, volume, buy participation, pool depth, momentum, estimated FDV, migration evidence and observed unique buyers/buyer arrival rate. These wallet counts describe only seen trade events, not unique humans. Creator history, holder concentration and bundler links remain unknown.
3. Follow each frame for an observed **+25% before −12% within 60 seconds**. Target first is positive; stop first or a covered timeout is negative. Crossing order uses received trade events. A gap over 10 seconds, eviction, disconnected feed or restart censors the record; it is never silently labeled a rug. Timeout return is the last observation within 10 seconds of the deadline, not a fabricated exact-time price. The 60-second label horizon is separate from actual paper exits.
4. The first classifier needs **200 usable outcomes across 80 coins**, including skipped coins, with known modeled round-trip cost. It does not need 200 executed trades. Current-version examples only; no fabricated outcomes for old closed trades. This is a research floor, not proof of an edge. Read at most 500 terminal frames. Incomplete paths are excluded and their counts remain visible; this still creates coverage bias.
5. Split chronologically into 60% fitting / 20% calibration / 20% test. Purge boundary-overlapping outcomes and shared coin identities. Require at least 80 fit examples/40 coins, 30 calibration examples/15 coins and 30 test examples/15 coins. Fit 48 shallow XGBoost classification trees, then regularized sigmoid calibration on the separate calibration set. Subsequent attempts reserve fresh outcomes for the test. No random split.
6. Convert estimated target probability to a conservative scenario value: probability × 25% plus failure probability × assumed loss minus modeled cost. Failure loss is at least 12%, or the worse calibration-period average non-target loss; this is an assumption, not guaranteed executable expected value. Require a fixed 2% estimated advantage to select. Validation must beat the unfiltered sample, remain positive after an extra 1 percentage point cost, improve Brier score against the calibration-period prevalence baseline, and show positive stressed returns in both chronological test halves. Require 20 selected examples/10 coins, at least eight selections per half. Reliability bins and calibration metrics are saved; fitted calibration does not prove real-world probabilities are accurate.
7. Passing frozen candidates enter independent prospective paper comparison against a fresh control, with equal virtual funds/start time/exclusions/risk/costs. Both exclude all fitting/calibration/test coins. The first opportunity classifier adds a filter to momentum rules; it does not replace the risk screen or invent an unrestricted strategy. Migration recovery remains a separate baseline. A stable 5% hash sample of model-rejected coins may explore in the candidate paper account, at most one exploratory position/order at a time. All base signal and risk checks remain. Each exploratory outcome is marked. No per-tick rerolling.
8. Retrain at most hourly after 50 new usable outcomes. One trainer and one comparison at a time. Compare up to 24 hours of entries, or until both arms close 50 trades after at least one hour; archive only when active inventory/orders have finished or been explicitly retired as paper write-offs. **No automatic promotion to the main strategy or real wallet.**

The previous regression/filter research versions remain readable/exportable. They are not mixed into the new classifier's label contract.

## Unresolved positions and loss review

After three minutes without a fresh token observation while other pools continue to provide a healthy live feed, an unresolved position is automatically retired as a **zero-recovery paper write-off**. A feed outage resets that timer. The dashboard also offers manual retirement for stale positions. Neither path submits or invents a sale, refunds cash, assigns an exit MC, or claims a verified rug. Remaining virtual quantity and entry evidence are retained in the record; recovery is not automatically credited later. This deliberately conservative paper accounting frees active scanning/position slots. Write-offs count toward the daily loss budget and net equity; realized sale P&L remains separate.

The collapsed loss breakdown groups closed-trade and write-off results by observed age, pool depth, score, exit reason and exploration status. Holder concentration is explicitly unknown. These are associations, not causal diagnoses. Unresolved write-offs are available for analysis; they are not inserted as verified rug or observed-price barrier labels.

## Resources and restart

- Raw live events stay in the existing capped, ephemeral RAM cache. ML does not persist the raw stream.
- Read at most 500 terminal opportunity records per fit. One training child, one compute thread, 48 trees of maximum depth 3. CPU soft/hard limits 30/35 seconds; wall timeout 60 seconds; sampled RSS watchdog 512 MiB. Watchdog runs every two seconds, not an instantaneous OS memory ceiling. Failed jobs do not pause the scanner.
- Live trading imports no NumPy or XGBoost. Its small Python predictor must match native XGBoost within 1e-6 before a model is saved. Native JSON is retained for reproducibility; no pickle loading.
- Models and comparisons use the existing **50 MiB capped** `data/local/live-paper.sqlite3`: latest six models plus an older active model if needed, bounded strategy attempt records and 20 comparison summaries. Census limit: 10,000; completed frames: 6,000 plus at most 512 pending; write-offs: 1,000. Under database pressure the census/frame retention reduces further. Active model/accounts are checkpointed. Existing trade/decision limits still apply.
- Installed dependencies occupy approximately **154 MiB on disk** in ignored `research/.venv-ml`. This is a fixed environment, not growing market history. Temporary training files are removed on completion/graceful stop. An abrupt OS/process kill may leave a small OS-temp directory.
- Graceful shutdown stops training and saves models/comparison balances. Raw live cache disappears. No scanning, learning or position management runs while stopped. Restart restores progress and positions with entries paused; click Start bot. Interrupted fitting retries on schedule. Missed market events are not invented.
- **Clear paper results deletes models, comparisons, opportunity memory and write-offs too.** Clear live-token cards is separate. Export before clearing paper results if you want to keep learned versions.

## Running

Restart the existing server with `python3 app/server.py`, refresh and click Start bot. Open Learning lab to see eligible counts, fitting state and comparison progress. ML account cards appear only after enough evidence and passing validation. No profitable model is claimed or preloaded.

Pinned packages: `research/requirements-ml.txt`. This workspace has isolated Python 3.9 with XGBoost 2.1.4, NumPy 1.26.4 and SciPy 1.13.1. macOS also needed OpenMP. A local copy came from Homebrew's arm64 Sequoia libomp 23.1.2 bottle, SHA-256 `a90f9ec48553a39f420c26600239df24b4c1cd30202d93a53128854afb6ff9fb`, verified before extraction. No Homebrew/global installation was made. License: `research/.venv-ml/lib/OPENMP-LICENSE.TXT`. The local XGBoost dylib received relative rpath `@loader_path/../../../..` and an ad-hoc signature to find `research/.venv-ml/lib/libomp.dylib`. Rebuilding the environment requires a compatible OpenMP runtime; see [official installation instructions](https://xgboost.readthedocs.io/en/stable/install.html).

## Remaining work

Coverage bias remains: early launches get a census record, but full frames need mapped pool observations. Evicted, quiet or disconnected tokens may lack usable outcomes. A calibrated classifier on covered paths is not a calibrated rug detector. Creator history, verified holder concentration and bundle evidence need additional data before they can become model inputs.

Then: longer forward comparisons; executable-route calibration of fill assumptions; feed/entry latency and missed-opportunity coverage; market regimes and stronger statistical/cost tests; explicit paper promotion and rollback criteria. Learned exits and wider strategy families come later. Longer runtime cannot guarantee profit or eliminate mistakes.

User decisions remain risk budget, allowed markets and eventual promotion policy. Apart from the requested $50 sizing and removal of timed exits, existing risk limits stay fixed; no manual tuning is needed to start collecting. Real-money deployment is a separate decision after validating execution and sustained out-of-sample performance.

## Verification

Tests cover time/mint separation, fresh validation windows, missing features, rejection on losing holdouts, native/portable parity, subprocess training, persistence/retry, memory watchdog, independent balances, training-coin exclusion, exits/protection, restart/clear and model failure isolation. Synthetic test profitability only proves the plumbing learns an intentionally planted signal; it does not demonstrate market profitability.

Calibration reference: [scikit-learn calibration guide](https://scikit-learn.org/stable/modules/calibration.html) describes why fitting and calibration data must be disjoint. No scikit-learn dependency was added; local sigmoid fitting uses the already-installed SciPy.
