# Claude Code --- AI-Brain Instructions

Follow `AGENTS.md` as primary policy.

For AI-Brain work, read `AGENTS.md` and relevant `docs/`, preserve the
supplied PromptID, and establish READ-ONLY vs WRITE authorization before
commands.

Prefer native Docker/shell/Git inspection over unnecessary scripts.
Never expose secret values. Never touch unrelated containers or `mds`.
Re-query the live target immediately before authorized writes and stop
on unexpected drift.

Do not call a service healthy merely because its container is `running`;
distinguish container state, Docker healthcheck, and application
validation.

Report what was actually checked and end with `FINAL`.
