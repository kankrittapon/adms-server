# AI-Brain Agent Pack

Portable instructions for Claude Code, Gemini CLI/Gem, Codex, and other
agents working with AI-Brain infrastructure.

Start with `AGENTS.md`.

For a Gemini Gem, paste `docs/GEM_RESPONSE_STYLE.md` into the Gem custom
instructions. Keep the repository files as the operational authority
when the Gem is used on this project.

## Adminer Access

After network hardening (Checkpoint: `AIBRAIN-Infra-HardenNetwork-002`), Adminer is intentionally bound strictly to host loopback:

`127.0.0.1:8080`

To access Adminer securely from an authorized management workstation, open an SSH port forwarding tunnel:

```powershell
ssh -L 8080:127.0.0.1:8080 kanfullbuster@192.168.1.248
```

Then open the following URL in your web browser:

`http://localhost:8080`

### Operational Notes:
- The SSH terminal session must remain active while using Adminer.
- Adminer is intentionally NOT published to external LAN (`192.168.1.248`) or Tailscale (`100.68.88.63`) host interfaces.
- PostgreSQL main database port `5432` is not published on host interfaces.
- Adminer connects to PostgreSQL databases (`n8n_zort_postgres`, `private_postgres`, `player_postgres`) over the Docker internal network (`n8n-zort_default`) using container service names (`postgres:5432`, `private-postgres:5432`, `player-postgres:5432`).

