# Gemini Adapter

Root `AGENTS.md` governs work.

Before project work:
1. Read `AGENTS.md`.
2. Read relevant `.agent/context/`.
3. Read relevant canonical `docs/`.
4. Load relevant `.agent/skills/`.
5. Preserve and repeat the PromptID.

Gemini-specific rules:
- Default to READ-ONLY.
- Require explicit authorization for writes/restarts/config edits/DB changes/network changes/commit/push.
- Never print secret values.
- Re-check live state immediately before authorized writes.
- Use PASS / FAIL / BLOCKED / NOT TESTED precisely.
- Never replace missing evidence with assumptions.
- Separate file/config evidence from live verification.

This adapter must not override `AGENTS.md`.
