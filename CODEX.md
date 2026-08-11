# Codex --- AI-Brain Instructions

Use `AGENTS.md` as authority.

Before editing Compose, scripts, service configuration, SQL, CI,
networking, or deployment files: identify PromptID and exact target,
inspect current state, preserve secrets, state validation/rollback, and
stop if state differs materially from the approved plan.

Do not modify generated state, Docker volumes, databases, credentials,
or unrelated services as collateral cleanup. Do not commit or push
without explicit authorization.

Reports must distinguish source/config changes from runtime changes and
end with `FINAL`.
