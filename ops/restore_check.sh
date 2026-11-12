#!/usr/bin/env bash
# Explicit read/restore verification: never drops or overwrites the live database.
set -euo pipefail
cd "$(dirname "$0")/.."
: "${RCLONE_CONFIG:?Configure protected rclone config first}"
: "${1:?Usage: ops/restore_check.sh YYYYMMDDTHHMMSSZ unique_test_db_name}"
BACKUP_REMOTE="${BACKUP_REMOTE:-ecrfcrypt:oracle-nims-backups}"
ARCHIVE="nims-cmv-${1}.dump"
TEST_DB="${2:-nims_restorecheck}"
[[ "$BACKUP_REMOTE" == ecrfcrypt:* ]] || { echo 'Encrypted remote required' >&2; exit 3; }
[[ "$1" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo 'Invalid backup timestamp' >&2; exit 3; }
[[ "$TEST_DB" =~ ^[a-z][a-z0-9_]{4,49}$ ]] || { echo 'Invalid test database name' >&2; exit 3; }
[[ "$TEST_DB" != nims_ecrf ]] || { echo 'Refusing production DB overwrite' >&2; exit 3; }
umask 077
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT
rclone copyto "$BACKUP_REMOTE/$ARCHIVE" "$TMP_DIR/$ARCHIVE"
# Archive is parsed before any database is created.
docker compose exec -T db sh -ec 'cat >/tmp/restoretest.dump; pg_restore --list /tmp/restoretest.dump >/dev/null' <"$TMP_DIR/$ARCHIVE"
# Target DB name is safely validated and passed as a shell environment value.
docker compose exec -T -e TARGET_DB="$TEST_DB" db sh -ec '
    if psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT datname FROM pg_database" | grep -Fxq "$TARGET_DB"; then echo "Test database already exists; refusing to overwrite" >&2; exit 4; fi
    createdb -U "$POSTGRES_USER" "$TARGET_DB"
    pg_restore -U "$POSTGRES_USER" -d "$TARGET_DB" --no-owner --no-acl /tmp/restoretest.dump
    psql -U "$POSTGRES_USER" -d "$TARGET_DB" -tAc "SELECT count(*) FROM audit_events;"
'
echo "Restore test succeeded in database $TEST_DB; remove it after reviewing its result."
