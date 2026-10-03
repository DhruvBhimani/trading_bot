# Live paper trading

Restart the server from the project folder with `python3 app/server.py`, refresh
http://127.0.0.1:8765, and click **Start live paper** on **Live paper trading**.
Startup and restart always pause new entries. No wallet or signing is involved.

Two independent accounts compare momentum and verified post-migration recovery.
Each starts with 10 virtual SOL, buys 0.1 SOL per entry and permits two positions.
The scanner requires fresh, mapped PumpSwap SOL trades, verified mint/freeze
authority metadata, sufficient observed reserves, activity and buy participation.
Recovery additionally requires a matching observed migration event, a dip and
subsequent rebound. Bonding-curve launches are watched but not traded by this
first paper model. The dashboard explains skipped coins and displays positions,
costs, conservative equity and closed trades.

Entries and exits wait for a later trade observation after a delay. A constant
product reserve approximation includes modeled fees, price impact and slippage.
It is not an executable quote. Adverse entries expire/reject; blocked or stale
exits retain inventory. Missing/stale marks count as zero until fresh evidence
arrives. Pause entries keeps exit management running. Open/pending positions
survive live-cache clearing and prevent their coins from being discarded.

Edit `config/live-paper.json` to change experimental rules. Restart and use
**New comparison run** to apply them. Existing runs preserve their settings and
version fingerprint. New runs and clearing require paused accounts without open
or pending positions; use **Request paper exit** and wait for a fresh trade first.

Raw live data stays in capped RAM and expires. Compact paper checkpoints,
decisions, trades, versions and later outcome labels persist in
`data/local/live-paper.sqlite3`. The SQLite file has a roughly 50 MiB page limit,
with retention of at most 10,000 decisions and 5,000 closed trades; retention
tightens near the limit. The paper panel shows allocated/used size and provides
export and clear controls. It does not clear wallet records or other databases.

Labels at 30, 120 and 600 seconds use later fresh observations; missed windows
are marked unavailable. These records support future learning, but no model is
trained or promoted automatically yet. Holder concentration, bundler connections
and lifetime/global fees remain unknown. Observed session fees are partial.
Scores describe experimental ranking, not rug probabilities or expected profit.

Offline tests cover adapters through entry/exit, costs, failed exits, restart,
cache protection, retention, versioning, labels and HTTP controls. Live RPC
coverage, browser appearance and execution accuracy still need a live trial.

## Pool-screening fix — 2026-09-30

Known launches now gain their pool mapping from observed migration events.
Mint metadata lookups prioritize pools behind pinned/open-position coins.
Up to 100 of the 200 cache slots are reserved for recent pools; unused pool slots
remain available to launches. This keeps the total bound while protecting pool
observation windows from launch bursts. The worker also retains pool mappings
under launch pressure.

The paper page displays current pool candidates rather than frozen audit rows.
Scores and window statistics refresh even if the screening reason is unchanged;
audit decisions keep their original features. Non-pool launches are counted above
the table and remain visible in Live tokens. Missing decimals, absent mapped
trades and stale trades have separate explanations. Entries remain paused until
Start live paper is clicked; feed counters show whether usable trades are arriving.

Active pools created before startup can now be discovered from incoming swaps.
The worker verifies their pool account identity and replays a small bounded
buffer of actual observed trades. This is identity metadata, not a price snapshot.
Recovery still requires matching observed migration proof; discovering an older
active pool alone cannot establish migration or invent an earlier dip.

## Stale values, route checks, analysis and memory guard

Positions show a fresh conservative mark separately from the last observed mark
and its age. Stale marks still contribute zero to conservative equity. Feed gaps
and inactive/unknown trade coverage are distinguished; neither proves a rug or
loss of liquidity. Restart preserves the last observation when one was recorded.
Open positions keep their original pool identity if another pool for that mint
is discovered. Pending exits continue receiving observations.

A separate worker requests quote-only Jupiter Swap V2 routes without a taker,
wallet, signature or submission. It compares the current reserve model with sell
quotes and, when possible, a pending or recent entry quote. Quotes expire in the
UI after 15 seconds; attempts per target are spaced by 30 seconds and all requests
by at least 3 seconds. Provider errors, unavailable routes, different pools,
minimum output and price impact remain visible. Quotes are diagnostic comparisons,
not fills, guaranteed executions or proof that a token is safe. Model output
includes its configured network cost; provider network/rent estimates may differ.
The worker cannot change cash, inventory or fill accounting. Requests without an
API key succeeded during development; failures do not interrupt paper exits.
Reference: https://github.com/jup-ag/docs/blob/main/docs/swap/order-and-execute.mdx

Closed-trade details show modeled pool fees, price impact, slippage and network
cost; holding and order delay times; observed best/worst returns; blocked fill
attempts; and version. Current-run summaries report retained trade counts, win
rate, average wins/losses and holding times, costs with coverage, and exit reasons.
Older trades without the new breakdown are marked unknown, not reconstructed.
These observations do not identify a causal explanation for every loss.

The live SQLite cache now has a 32 MiB page ceiling. It trims trades more
aggressively above 24 MiB usage, reserves recent position history, and keeps
existing count/age limits. Actual server and worker RSS are sampled every ten
seconds when available. Server >256 MiB or worker >192 MiB activates pressure
cleanup: unpinned data is cleared, new admissions and paper entries pause, pending
buys cancel, and positions/pins/exits survive. Admissions recover below 192/128
MiB respectively; paper entries require an explicit restart via Start live paper.
The memory panel shows measurements, guard status and cache limits. These are
soft guards on process RSS, not a hard cap on Python, Node or browser memory.
A process may briefly spike before a sample. The 32 MiB ceiling covers the live
SQLite database, excluding temporary query/runtime overhead. Manual exports can
also temporarily allocate additional memory. Quote retention is capped at 500
compact records within the existing 50 MiB paper database; no raw disk archive.

## Current continuous-scanner behaviour (supersedes memory-pause section)

Cache pressure no longer pauses entries or admissions. The worker uses a lighter
runtime and bounded rotation: 64 active/migrated pools, 16 near-migration watches,
plus pins and open/pending positions. Ordinary early launches are counted and
released. Near migration means observed remaining/virtual token reserves <=10%,
not a promised migration; paper execution still requires an observed SOL pool.
Candidates rotate after observation, rejected addresses have a bounded cooldown,
and older active pools are discovered from swaps. Canonical Pump.fun pool PDA
verification allows older migrated pools to qualify without witnessing migration;
recovery uses subsequent observations, not invented historical prices.

A failed or persistently oversized feed worker reconnects automatically; paper
state remains. Network gaps can still temporarily prevent fresh-data fills.
Live cards are hidden by default. Scan counters and current candidates remain on
the paper page. Trade history there now uses the same current run as its analysis;
earlier runs remain exportable. A three-minute full-path trial kept entries enabled
throughout with cache under 1 MiB and worker RAM around 150 MiB. This is evidence
of the fix, not proof of unlimited fault-free uptime.
