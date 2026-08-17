# Claude Adapter

Use root `AGENTS.md` as authority.

Before project work:
1. Read `AGENTS.md`.
2. Read relevant `.agent/context/`.
3. Read relevant canonical `docs/`.
4. Load relevant `.agent/skills/`.
5. Preserve the supplied PromptID and determine READ-ONLY vs WRITE authorization.

Claude-specific preferences:
- Prefer native Docker/shell/Git inspection over unnecessary scripts.
- Re-query the live target immediately before authorized writes.
- Never expose secret values.
- Do not touch unrelated services.
- Do not call a service healthy merely because its container is `running`; distinguish container state, Docker healthcheck, and application validation.
- Report what was actually checked.

This adapter must not override `AGENTS.md`.
