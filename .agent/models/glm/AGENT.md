# GLM Adapter

Use root `AGENTS.md` as authority.

Before project work:
- load relevant project context/docs
- preserve PromptID exactly
- establish READ-ONLY vs WRITE
- inspect current target before inference
- re-check before any authorized write

GLM-specific preferences:
- Keep scope narrow and explicit.
- Prefer direct evidence over assumptions.
- Preserve exact identifiers and reported values.
- Stop on unexpected drift.
- Never infer Human ↔ Device identity from numbering.

This adapter must not override `AGENTS.md`.
