# AI-Brain Agent Operating Rules

## Purpose

Operate the `ai-brain` Docker/infrastructure environment conservatively,
preserve service boundaries, and produce reproducible reports.

## Authority order

Read: `AGENTS.md` → relevant `docs/` → current `promptID/` task → latest
relevant report. A task prompt does not silently override a safety
boundary.

## PromptID

Every substantial infrastructure task uses
`# PromptID: AIBRAIN-<AREA>-<ACTION>-NNN`. For unrelated work use
`#NotInfra PromptID: <ID>`. Repeat the ID in the report.

## Default mode

Default is **READ-ONLY**. Explicit write authorization is required for
restarts/recreates, configuration edits, network exposure changes,
secret rotation, database writes/migrations, deletion/pruning,
Cloudflare/Tailscale changes, commit, or push.

## Secrets

Never print, copy into reports, or commit passwords, API keys, tokens,
encryption/signing keys, database credentials, Garmin
credentials/tokens, Telegram secrets, or Cloudflare credentials. Report
variable names/set-state only. Use `.env`, Docker secrets, or secret
management.

## Service boundaries

Primary scope: `n8n_zort`, `n8n_zort_postgres`, `n8n_zort_cloudflared`,
`paddle_ocr`, `garmin_api`, `private_api`, `private_postgres`,
`player_api`, `player_postgres`, `adminer`.

Sailfish, Minecraft, Audio Reader, and NotebookLM are outside default
modification scope. `mds` is a separate host/scope.

## Database/network safety

Before database changes identify the exact container/database/operation.
No destructive SQL, migration, restore, volume deletion, or credential
change without explicit authorization and rollback/backup planning.

Do not broaden public exposure. Prefer Docker-internal networking,
localhost, Tailscale, or controlled access.

## Write protocol

1.  State PromptID and authority.
2.  Record live state.
3.  Identify exact target/change and rollback.
4.  Re-check immediately before write.
5.  Make only the authorized change.
6.  Validate health/connectivity.
7.  Report exact changes.
8.  Do not commit/push unless separately authorized.

If live state materially differs from the approved plan, STOP before
write.

## Reporting

Use `YES`, `NO`, `PASS`, `FAIL`, `BLOCKED`, `NOT TESTED`, `N/A`,
`UNKNOWN` precisely. Separate live evidence, file evidence, inference,
recommendation, and untested assumptions. End execution/audit tasks with
`FINAL`.
