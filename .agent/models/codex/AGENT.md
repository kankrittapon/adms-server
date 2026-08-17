# Codex Adapter

Use root `AGENTS.md` as authority.

Before editing Compose, scripts, service configuration, SQL, CI, networking, deployment, or source:
- identify PromptID and exact target
- inspect current state
- preserve secrets
- state validation and rollback
- re-check target immediately before write
- stop if state differs materially from the approved plan

Do not modify generated state, Docker volumes, databases, credentials, or unrelated services as collateral cleanup.

Do not commit or push without explicit authorization.

Reports must distinguish source/config changes from runtime changes.

This adapter must not override `AGENTS.md`.
