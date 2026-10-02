#!/usr/bin/env bash
set -euo pipefail

# PRM-ADMS-004: Scheduled Business Hours Write Window — Host automation
# Calls POST /api/v1/write-session/auto-window?action=open|close via loopback
# Gated by ADMIN bearer token; respects system_configurations.enabled

ACTION="${1:-open}"
if [[ "$ACTION" != "open" && "$ACTION" != "close" ]]; then
  echo "Usage: $0 [open|close]" >&2
  exit 2
fi

BASE_URL="${ADMS_API_URL:-http://192.168.1.248:8081}"
LOGFILE="/data/adms/logs/auto_session.log"

# Ensure log dir (dual-write: /data is primary mounted HDD, fallback to /home if not mounted)
if mountpoint -q /data 2>/dev/null && [ -d "/data/adms/logs" ]; then
  LOGFILE="/data/adms/logs/auto_session.log"
else
  LOGFILE="/home/kanfullbuster/adms-server/logs/auto_session.log"
  mkdir -p "$(dirname "$LOGFILE")"
fi
mkdir -p "$(dirname "$LOGFILE")" 2>/dev/null || true
touch "$LOGFILE" 2>/dev/null || true
chmod 640 "$LOGFILE" 2>/dev/null || true

# Credentials: optional EnvironmentFile-style file (chmod 600) overrides unit env.
CRED_FILE="${ADMS_SCHEDULER_ENV:-/home/kanfullbuster/adms-server/.adms_scheduler.env}"
if [ -r "$CRED_FILE" ]; then
  # shellcheck disable=SC1090
  set -a; . "$CRED_FILE"; set +a
fi
ADMIN_USER="${ADMS_ADMIN_USER:-admin}"
ADMIN_PASS="${ADMS_ADMIN_PASSWORD:-}"

if [ -z "$ADMIN_PASS" ]; then
  echo "[$(date -Is)] ERROR auto-window $ACTION: ADMS_ADMIN_PASSWORD not set (unit env or $CRED_FILE)" | tee -a "$LOGFILE" >&2
  exit 1
fi

# Always log in fresh: session tokens expire within hours, so a cached token
# would be stale by the next 09:00/18:00 run.
LOGIN_BODY=$(jq -cn --arg u "$ADMIN_USER" --arg p "$ADMIN_PASS" '{username:$u,password:$p}')
LOGIN_CODE=$(curl -s -o /tmp/adms_auto_login.json -w "%{http_code}" -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" -d "$LOGIN_BODY" || echo "000")
TOKEN=$(jq -r '.token // empty' /tmp/adms_auto_login.json 2>/dev/null || true)
rm -f /tmp/adms_auto_login.json

if [ -z "$TOKEN" ]; then
  echo "[$(date -Is)] ERROR auto-window $ACTION: login failed HTTP $LOGIN_CODE as $ADMIN_USER" | tee -a "$LOGFILE" >&2
  exit 1
fi

# Call auto-window endpoint (supports query ?action= or JSON body)
HTTP_CODE=$(curl -s -o /tmp/adms_auto_window.json -w "%{http_code}" -X POST "$BASE_URL/api/v1/write-session/auto-window?action=$ACTION" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" 2>&1 || echo "000")
BODY=$(cat /tmp/adms_auto_window.json 2>/dev/null || echo "{}")
rm -f /tmp/adms_auto_window.json

# Log with timestamp
echo "[$(date -Is)] auto-window $ACTION HTTP $HTTP_CODE $BODY" | tee -a "$LOGFILE"

# 200/201 = success, 409 = already active (idempotent), 200 no-op when scheduler disabled
if [[ "$HTTP_CODE" =~ ^(200|201|409)$ ]]; then
  exit 0
else
  exit 1
fi
