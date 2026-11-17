#!/usr/bin/env bash
# Encrypted offsite PostgreSQL backup with a verified decrypted hash roundtrip.
# Clinical and staging use different Compose projects, archive names and receipts.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
umask 077

scope=${BACKUP_SCOPE:-staging}
case "$scope" in
  staging)
    compose=(docker compose -f compose.yaml)
    db_expected=nims_ecrf
    archive_prefix=nims-cmv
    : "${BACKUP_REMOTE:=ecrfcrypt:oracle-nims-backups}"
    : "${BACKUP_STATUS_DIR:=$PWD/.backup-state}"
    ;;
  clinical)
    : "${CLINICAL_ENV_FILE:?Set the protected clinical Compose env file}"
    : "${BACKUP_REMOTE:?Set an approved institutional crypt remote for clinical backups}"
    : "${BACKUP_STATUS_DIR:?Set the dedicated clinical receipt directory}"
    [[ "$CLINICAL_ENV_FILE" = /* && -f "$CLINICAL_ENV_FILE" ]] || {
      echo "Clinical environment file must be an existing absolute path" >&2; exit 4;
    }
    [[ "$BACKUP_STATUS_DIR" = /* ]] || {
      echo "Clinical receipt directory must be an absolute path" >&2; exit 4;
    }
    compose=(docker compose --env-file "$CLINICAL_ENV_FILE" -f compose.yaml -f compose.clinical.yaml)
    db_expected=nims_cmv_clinical
    archive_prefix=nims-cmv-clinical
    ;;
  *) echo "Unknown BACKUP_SCOPE: use staging or clinical" >&2; exit 4 ;;
esac

: "${RCLONE_CONFIG:?Set RCLONE_CONFIG to the private rclone config}"
[[ -r "$RCLONE_CONFIG" ]] || { echo "rclone config unreadable" >&2; exit 4; }
command -v rclone >/dev/null || { echo "rclone missing" >&2; exit 4; }
command -v docker >/dev/null || { echo "docker missing" >&2; exit 4; }
[[ "$BACKUP_REMOTE" == ecrfcrypt:* ]] || {
  echo "Refusing unencrypted remote; ecrfcrypt required" >&2; exit 4;
}
rclone listremotes | grep -qx 'ecrfcrypt:' || {
  echo "Encrypted remote ecrfcrypt: not configured" >&2; exit 4;
}
rclone config show ecrfcrypt | grep -Eq '^[[:space:]]*type[[:space:]]*=[[:space:]]*crypt[[:space:]]*$' || {
  echo "ecrfcrypt: is not an rclone crypt backend" >&2; exit 4;
}

# Fail closed if Compose is pointing at the wrong source database.
actual_db=$("${compose[@]}" exec -T db sh -ec 'printf "%s" "$POSTGRES_DB"')
[[ "$actual_db" = "$db_expected" ]] || {
  echo "Database identity mismatch; backup not performed" >&2; exit 4;
}

scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="$archive_prefix-$stamp.dump"
"${compose[@]}" exec -T db sh -ec \
  'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-acl' > "$scratch/$archive"
[[ -s "$scratch/$archive" ]] || { echo "Database backup is empty" >&2; exit 5; }
digest=$(sha256sum "$scratch/$archive" | awk '{print $1}')
rclone copyto "$scratch/$archive" "$BACKUP_REMOTE/$archive" \
  --retries 4 --low-level-retries 8 --checkers 2
roundtrip=$(rclone cat "$BACKUP_REMOTE/$archive" | sha256sum | awk '{print $1}')
[[ "$digest" = "$roundtrip" ]] || {
  echo "Encrypted offsite roundtrip failed; receipt not updated" >&2; exit 5;
}

# Read-only API mount: UTC timestamp, checksum and crypt reference only.
# The API runs as UID 10001 and must be able to read these nonsecret receipts.
install -d -m 0755 "$BACKUP_STATUS_DIR"
temporary=$(mktemp "$BACKUP_STATUS_DIR/.backup.XXXXXXXX")
printf '%s %s %s\n' "$stamp" "$digest" "$BACKUP_REMOTE/$archive" > "$temporary"
chmod 0644 "$temporary"
mv -f "$temporary" "$BACKUP_STATUS_DIR/last_success"
echo "Encrypted $scope backup and SHA-256 roundtrip verified: $stamp"
