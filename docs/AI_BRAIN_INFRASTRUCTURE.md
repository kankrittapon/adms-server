# AI-Brain Infrastructure Baseline

Baseline source: audit dated 10 August 2026.

## ai-brain

-   Tailscale IP: `100.68.88.63`
-   SSH user: `kanfullbuster`
-   Project: `/home/kanfullbuster/n8n-zort`
-   Compose: `/home/kanfullbuster/n8n-zort/docker-compose.yml`
-   Public entry: n8n through Cloudflare Tunnel

## mds

Separate host/scope at `100.75.200.54`, SSH user `mds`.

## Primary map

``` text
Internet/Telegram -> Cloudflare Tunnel -> n8n_zort
  -> n8n_zort_postgres
  -> paddle_ocr
  -> garmin_api
  -> private_api -> private_postgres
  -> player_api -> player_postgres
  -> ZORT ETL/reporting

adminer -> PostgreSQL administration
```

## Recorded attention items

-   `sailfish_collector` unhealthy, but outside primary scope.
-   `private_postgres` and `adminer` lacked healthchecks.
-   Main PostgreSQL `5432` and Adminer `8080` were published on all
    interfaces.
-   Cloudflare Tunnel token handling should move away from runtime
    command exposure and be rotated if exposed.
-   Multiple PostgreSQL instances require explicit database
    identification.
-   `running` without a healthcheck does not prove application health.

This is a historical baseline, not proof of current live state.
