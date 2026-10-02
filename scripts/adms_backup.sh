#!/usr/bin/env bash
set -euo pipefail

# Count dumps without failing on an empty directory (ls on an unmatched glob
# exits 2, which under pipefail aborted the run after the dump had already
# succeeded — every run since 2026-09-23 was reported as failed).
count_dumps() {
  find "$1" -maxdepth 1 -name 'adms_*.dump' -type f 2>/dev/null | wc -l
}

# ADMS Backup — pg_dump -Fc with SHA256 and 14d pruning, dual-write to /data
# Target: /data/adms/backups (secondary HDD 98G, UUID 8b0a75c3-9ffd-44f1-9a01-e544f44d2c21) + fallback /home/kanfullbuster/adms-server/backups on root
# Prune: 14d retention (user confirmed 7-day dual-write grace → prune root after 14d, keep secondary 14d as well)
# Scheduling: systemd timer adms-backup.timer daily 02:15 (see systemd unit)

BACKUP_ROOT_PRIMARY="/home/kanfullbuster/adms-server/backups"
BACKUP_ROOT_SECONDARY="/data/adms/backups"
BACKUP_ROOT="$BACKUP_ROOT_PRIMARY"

# Prefer secondary if mounted and writable
if mountpoint -q /data 2>/dev/null && [ -d "$BACKUP_ROOT_SECONDARY" ]; then
  BACKUP_ROOT="$BACKUP_ROOT_SECONDARY"
  mkdir -p "$BACKUP_ROOT"
else
  echo "[WARN] /data not mounted or $BACKUP_ROOT_SECONDARY missing — falling back to primary $BACKUP_ROOT_PRIMARY" >&2
  mkdir -p "$BACKUP_ROOT_PRIMARY"
fi

# Also ensure primary exists for dual-write grace period (first 7 days write both)
mkdir -p "$BACKUP_ROOT_PRIMARY"
if [ "$BACKUP_ROOT" != "$BACKUP_ROOT_PRIMARY" ]; then
  mkdir -p "$BACKUP_ROOT_SECONDARY"
fi

TS=$(date +"%Y%m%d_%H%M%S")
TMP_IN_CONTAINER="/tmp/adms_${TS}.dump"
LOGFILE_PRIMARY="$BACKUP_ROOT_PRIMARY/backup.log"
LOGFILE_SECONDARY="$BACKUP_ROOT_SECONDARY/backup.log"
LOGFILE="$LOGFILE_PRIMARY"
if [ "$BACKUP_ROOT" = "$BACKUP_ROOT_SECONDARY" ]; then
  LOGFILE="$LOGFILE_SECONDARY"
fi

echo "[$(date -Is)] BACKUP start TS=$TS ROOT=$BACKUP_ROOT" | tee -a "$LOGFILE_PRIMARY" >> "$LOGFILE_SECONDARY" 2>/dev/null || tee -a "$LOGFILE" >/dev/null

# 1. pg_dump -Fc inside adms_postgres (43h uptime proven)
if ! docker exec adms_postgres pg_dump -U adms -d adms -Fc -f "$TMP_IN_CONTAINER" 2>>"$LOGFILE"; then
  echo "[$(date -Is)] pg_dump FAILED" | tee -a "$LOGFILE" >&2
  exit 1
fi

# 2. Copy out (avoids volume permission drift)
PRIMARY_FILE="$BACKUP_ROOT_PRIMARY/adms_${TS}.dump"
SECONDARY_FILE="$BACKUP_ROOT_SECONDARY/adms_${TS}.dump"

# Copy to primary first
docker cp "adms_postgres:$TMP_IN_CONTAINER" "$PRIMARY_FILE" 2>>"$LOGFILE"
# Also copy to secondary if dual-write (first 7 days grace — always dual-write for safety until manually disabled)
if [ "$BACKUP_ROOT" != "$BACKUP_ROOT_PRIMARY" ] && [ -d "$BACKUP_ROOT_SECONDARY" ]; then
  cp "$PRIMARY_FILE" "$SECONDARY_FILE" 2>>"$LOGFILE" || docker cp "adms_postgres:$TMP_IN_CONTAINER" "$SECONDARY_FILE" 2>>"$LOGFILE"
fi
# Use secondary as canonical if available
CANONICAL_FILE="$PRIMARY_FILE"
if [ -f "$SECONDARY_FILE" ]; then
  CANONICAL_FILE="$SECONDARY_FILE"
fi

# Cleanup temp inside container
docker exec adms_postgres rm -f "$TMP_IN_CONTAINER" 2>/dev/null || true

# 3. SHA256
sha256sum "$PRIMARY_FILE" > "$PRIMARY_FILE.sha256" 2>>"$LOGFILE"
if [ -f "$SECONDARY_FILE" ] && [ "$PRIMARY_FILE" != "$SECONDARY_FILE" ]; then
  cp "$PRIMARY_FILE.sha256" "$SECONDARY_FILE.sha256" 2>>"$LOGFILE" || sha256sum "$SECONDARY_FILE" > "$SECONDARY_FILE.sha256"
fi

# 4. Sanity: pg_restore -l (do not restore, just list)
if ! docker exec -i adms_postgres pg_restore -l < "$CANONICAL_FILE" >/dev/null 2>>"$LOGFILE"; then
  echo "[$(date -Is)] pg_restore -l sanity FAILED $CANONICAL_FILE" | tee -a "$LOGFILE" >&2
  exit 1
fi

# 5. Prune 14d (both locations, but never delete all)
for DIR in "$BACKUP_ROOT_PRIMARY" "$BACKUP_ROOT_SECONDARY"; do
  [ -d "$DIR" ] || continue
  # Count before
  CNT_BEFORE=$(count_dumps "$DIR")
  find "$DIR" -maxdepth 1 -name "adms_*.dump" -type f -mtime +14 -print -delete 2>>"$LOGFILE" | tee -a "$LOGFILE" >/dev/null || true
  find "$DIR" -maxdepth 1 -name "adms_*.dump.sha256" -type f -mtime +14 -print -delete 2>>"$LOGFILE" || true
  CNT_AFTER=$(count_dumps "$DIR")
  echo "[$(date -Is)] PRUNE $DIR before=$CNT_BEFORE after=$CNT_AFTER retention 14d" | tee -a "$LOGFILE" >/dev/null
done

# 6. Report
SIZE=$(du -h "$CANONICAL_FILE" | cut -f1)
CHECKSUM=$(cut -d' ' -f1 "$CANONICAL_FILE.sha256")
CNT_PRIMARY=$(count_dumps "$BACKUP_ROOT_PRIMARY")
CNT_SECONDARY="0"
if [ -d "$BACKUP_ROOT_SECONDARY" ]; then
  CNT_SECONDARY=$(count_dumps "$BACKUP_ROOT_SECONDARY")
fi
echo "[$(date -Is)] BACKUP ok $CANONICAL_FILE $SIZE SHA256 $CHECKSUM primary_count $CNT_PRIMARY secondary_count $CNT_SECONDARY" | tee -a "$LOGFILE" | tee -a "$LOGFILE_PRIMARY" >/dev/null

# 7. Disk pressure log
df -hT "$BACKUP_ROOT_PRIMARY" 2>&1 | tail -n 1 | tee -a "$LOGFILE" >/dev/null
if mountpoint -q /data 2>/dev/null; then
  df -hT /data 2>&1 | tail -n 1 | tee -a "$LOGFILE" >/dev/null
fi

exit 0
