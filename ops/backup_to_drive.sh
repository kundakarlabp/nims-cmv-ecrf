#!/usr/bin/env bash
# Always encrypt to rclone's crypt remote before remote storage. No plaintext retained.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${BACKUP_REMOTE:=ecrfcrypt:oracle-nims-backups}"
: "${RCLONE_CONFIG:?Set RCLONE_CONFIG to a protected rclone config file}"
command -v rclone >/dev/null || { echo 'rclone missing' >&2; exit 4; }
command -v docker >/dev/null || { echo 'docker missing' >&2; exit 4; }
if [[ "$BACKUP_REMOTE" != ecrfcrypt:* ]]; then echo 'Refusing backup: set dedicated crypt remote ecrfcrypt:' >&2; exit 4; fi
if ! rclone listremotes | grep -qx 'ecrfcrypt:'; then echo 'Encrypted rclone remote ecrfcrypt: not configured' >&2; exit 4; fi
umask 077
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
ARCHIVE="nims-cmv-$STAMP.dump"
# Custom format supports pg_restore, compressed internally; no real record names in archive filename.
docker compose exec -T db sh -c 'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' >"$TMP_DIR/$ARCHIVE"
test -s "$TMP_DIR/$ARCHIVE"
HASH=$(sha256sum "$TMP_DIR/$ARCHIVE" | awk '{print $1}')
rclone copyto "$TMP_DIR/$ARCHIVE" "$BACKUP_REMOTE/$ARCHIVE" --retries 4 --low-level-retries 8 --checkers 2
# Check actual encrypted Drive round-trip: decrypt stream and compare the original bytes.
REMOTE_HASH=$(rclone cat "$BACKUP_REMOTE/$ARCHIVE" | sha256sum | awk '{print $1}')
if [[ "$HASH" != "$REMOTE_HASH" ]]; then echo 'REMOTE RESTORE HASH FAILURE' >&2; exit 5; fi
printf 'Backup completed and remote content verified: %s %s\n' "$STAMP" "$HASH"
