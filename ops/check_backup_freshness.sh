#!/usr/bin/env bash
# Fails if verified encrypted offsite backup is older than eight hours.
set -euo pipefail
cd "$(dirname "$0")/.."
STATE_DIR="$PWD/.backup-state"
if [[ -v BACKUP_STATUS_DIR ]]; then STATE_DIR="$BACKUP_STATUS_DIR"; fi
MAX_AGE_SECONDS=28800
if [[ -v BACKUP_MAX_AGE_SECONDS ]]; then MAX_AGE_SECONDS="$BACKUP_MAX_AGE_SECONDS"; fi
STATE="$STATE_DIR/last_success"
[[ -r "$STATE" ]] || { echo "BACKUP ALERT: no verified cloud-backup marker" >&2; exit 2; }
read -r STAMP HASH REMOTE <"$STATE"
[[ "$STAMP" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo "BACKUP ALERT: bad marker timestamp" >&2; exit 2; }
[[ "$HASH" =~ ^[0-9a-f]{64}$ ]] || { echo "BACKUP ALERT: marker checksum invalid" >&2; exit 2; }
[[ "$REMOTE" == ecrfcrypt:* ]] || { echo "BACKUP ALERT: remote is not crypt-labelled" >&2; exit 2; }
BACKUP_UNIX=$(date -u -d "$STAMP" +%s)
NOW_UNIX=$(date -u +%s)
AGE=$((NOW_UNIX-BACKUP_UNIX))
if ((AGE < 0 || AGE > MAX_AGE_SECONDS)); then
  echo "BACKUP ALERT: last verified upload age is $AGE seconds; threshold $MAX_AGE_SECONDS seconds" >&2
  exit 3
fi
echo "Latest verified encrypted upload $AGE seconds ago: $STAMP"
