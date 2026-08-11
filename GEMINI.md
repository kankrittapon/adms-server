# Gemini CLI --- AI-Brain Instructions

`AGENTS.md` governs AI-Brain work.

-   Read `AGENTS.md` and relevant `docs/`.
-   Preserve and repeat `# PromptID:`.
-   Default to READ-ONLY.
-   Require explicit authorization for writes/restarts/config
    edits/secret rotation/DB changes/network changes/commit/push.
-   Never print secret values.
-   Keep `ai-brain` and `mds` separate.
-   Do not modify unrelated Sailfish/Minecraft/Audio Reader/NotebookLM
    services without dependency verification and authorization.
-   Re-check live state immediately before authorized writes.
-   Use PASS/FAIL/BLOCKED/NOT TESTED precisely.
-   Never replace missing evidence with assumptions.
-   End with `FINAL`.

Also follow `docs/GEM_RESPONSE_STYLE.md`.
