# Legacy Root Rules Migration Note

The previous root-level files were:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `CODEX.md`

Their reusable safety rules were consolidated into the new root `AGENTS.md`.

Model-specific behavior from Claude/Gemini/Codex was moved into `.agent/models/`.

The previous supplied `AGENTS.md` was AI-Brain-specific and included service boundaries such as
n8n_zort, paddle_ocr, garmin_api, private_api/private_postgres, player_api/player_postgres,
adminer, and exclusions for unrelated services.

Those AI-Brain-specific service names are intentionally NOT hard-coded into the new universal
root policy. If this repository still requires those boundaries, place them in a project-specific
context document under `.agent/context/` or canonical `docs/`, not in model adapters.
