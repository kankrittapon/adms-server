# PromptID Registry

Format: `AIBRAIN-<AREA>-<ACTION>-NNN`.

Areas can include Docker, n8n, Postgres, PrivateAPI, Player, OCR,
Garmin, Cloudflare, Network, Security, Migration, Docs.

Lifecycle actions can include Audit, Plan, Authorize, Execute, Verify,
Close.

Example:

``` text
AIBRAIN-Postgres-ExposureAudit-001
AIBRAIN-Postgres-HardeningPlan-002
AIBRAIN-Postgres-HardeningExecute-003
AIBRAIN-Postgres-HardeningVerify-004
AIBRAIN-Postgres-HardeningClose-005
```

Use `#NotInfra PromptID:` when deliberately outside AI-Brain
infrastructure scope.
