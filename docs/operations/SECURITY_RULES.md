# AI-Brain Security Rules

-   Never store secrets in Git, reports, prompts, or agent instructions.
-   Prefer `.env`, Docker secrets, or secret management.
-   Do not expose PostgreSQL publicly.
-   Restrict Adminer to localhost/Tailscale/VPN/controlled access.
-   Separate credentials across n8n, Private, Player, Sailfish, and
    other services.
-   Treat Cloudflare Tunnel credentials as secrets.
-   Back up the correct PostgreSQL database before destructive
    operations.
-   Keep personal/financial Telegram commands behind owner/user guards.
-   Never weaken authentication, TLS, firewall, Tailscale, proxy, or
    Cloudflare controls merely to pass a test.
