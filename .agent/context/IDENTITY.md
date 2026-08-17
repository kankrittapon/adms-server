# Identity Context

## Principles

- Human Identity, Device Identity, Device User Identity, and Biometric Identity are separate.
- Never infer Human identity from sequential device IDs or spreadsheet ordering.
- Unmapped events are valid.
- Preserve raw Device Identity independently of Human enrichment.
- Terminal-local user IDs may be recycled.
- Temporal Human mapping should use `[valid_from, valid_to)` when applicable.

Project-specific canonical table/field names should be documented here or in canonical `docs/`.
