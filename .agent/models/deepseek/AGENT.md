# DeepSeek Adapter

Use root `AGENTS.md` as authority.

Before project work:
- load relevant project context/docs
- preserve PromptID exactly
- establish READ-ONLY vs WRITE
- verify exact target before mutation

DeepSeek-specific preferences:
- Separate verified evidence from inference.
- Do not broaden implementation scope.
- Default to READ-ONLY when authorization is ambiguous.
- Preserve Git/database/device safety boundaries.
- Stop instead of guessing when live state is uncertain.

This adapter must not override `AGENTS.md`.
