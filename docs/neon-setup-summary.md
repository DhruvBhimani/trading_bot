# Neon setup — change log

## Account and project

- Reused the user's Neon project `solitary-credit-06176932` (`DB bot`), branch
  `production` (`br-twilight-water-b4sfv1ya`), on the Free plan in AWS US East 2.
- Installed the official global Neon CLI, version 6.3.0, and completed CLI login
  with the user's browser authorization.
- No paid plan, payment method, AI gateway, auth service, bucket, function or
  collection schedule was added.

## Workspace files and tooling

- Installed eight official agent skills into `.agents/skills/` and recorded them
  in `skills-lock.json`: neon, neon-ai-gateway, neon-auth, neon-functions,
  neon-object-storage, neon-postgres, neon-postgres-branches,
  neon-postgres-egress-optimizer.
- Fetched and followed https://neon.com/.well-known/agent-skills/neon/SKILL.md;
  its contents matched the installed Neon overview skill.
- The existing global Codex configuration had no Neon server. Added only the
  missing project-scoped MCP entry in `.codex/config.toml`, pinned to this project
  and configured for OAuth. Existing global configuration was left in place.
  MCP still requires the client to load the project config and authenticate on
  first use; CLI login does not establish an authenticated MCP session.
- Linked `.neon` to the existing project and `production` branch.
- Pulled DATABASE_URL, DATABASE_URL_UNPOOLED and NEON_BRANCH into ignored
  `.env.local`; connection values are not included in this report.
- Created root `package.json` and `package-lock.json` with `@neon/config` and
  `@neon/env`. Created `neon.ts` with exactly the requested empty config:

```typescript
import { defineConfig } from "@neon/config/v1";

export default defineConfig({});
```

- `neon config plan` and `neon deploy` succeeded: no infrastructure changes,
  utilized service Postgres only.
- `.gitignore` excludes `.neon`, `node_modules/`, environment files and temporary
  private setup files. `.env.local` permissions are restricted to the owner.

## Research database changes

- Collector supports hosted PostgreSQL without falling back to SQLite. It reads
  Neon-generated `.env.local` and prefers the unpooled URL for session state.
- Added raw-response storage, tokens/pools, liquidity snapshots, candle versions,
  resumable collection jobs, status/coverage/export commands and an idempotent
  local-to-hosted migration.
- Batched candle/migration inserts to reduce network round trips.
- Added a conservative 300 MB collection storage check for the $0 budget.
  Provider Free-plan limits remain authoritative; this is not a billing control.
- Existing Java/backend files and earlier uncommitted work were preserved.
- 34 offline tests pass. The temporary migration-check branch is set to expire
  automatically at 2026-09-29 05:00 UTC and uses 0.25 CU.

## Live data verification

The migration passed on the temporary test branch and on `production`:

- 14 distinct discovered base tokens across 20 pools.
- 999 historical price candles for one token (SOL/USDC pool).
- 19 usable current-liquidity snapshots (20 source snapshot records total).
- 2 original provider responses, stored with source metadata and hashes.
- Every migrated candle value matches the local source.
- Repeating the migration leaves counts unchanged.

The 1,000-token collection is not running. Historical liquidity and tradability
are still missing; execution-ready token count remains zero. This setup stores
real data but does not establish a profitable or validated strategy.

Added helper scripts: `scripts/finish-database-setup.sh` and
`scripts/verify-hosted-database.py`, plus a hidden-input environment configurator.
The normal collector uses saved production credentials without displaying them.
