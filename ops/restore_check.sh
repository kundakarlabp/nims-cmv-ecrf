#!/usr/bin/env bash
# Test a crypt-protected offsite backup by restoring to a disposable DB only.
# Never overwrite or drop a live clinical/staging database.
set -Eeuo pipefail
cd "$(dirname "$0")/.."
umask 077

: "${RCLONE_CONFIG:?Set protected rclone configuration}"
: "${1:?Usage: ops/restore_check.sh YYYYMMDDTHHMMSSZ disposable_database_name}"
stamp=$1
test_db=${2:-nims_restorecheck}
[[ "$stamp" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || { echo "Invalid backup timestamp" >&2; exit 3; }
[[ "$test_db" =~ ^[a-z][a-z0-9_]{4,49}$ ]] || { echo "Invalid disposable database name" >&2; exit 3; }
[[ "$test_db" != nims_ecrf && "$test_db" != nims_cmv_clinical ]] || {
  echo "Refusing to overwrite staging or clinical database" >&2; exit 3;
}

scope=${BACKUP_SCOPE:-staging}
case "$scope" in
  staging)
    compose=(docker compose -f compose.yaml)
    expected_db=nims_ecrf
    prefix=nims-cmv
    : "${BACKUP_REMOTE:=ecrfcrypt:oracle-nims-backups}"
    : "${BACKUP_STATUS_DIR:=$PWD/.backup-state}"
    ;;
  clinical)
    : "${CLINICAL_ENV_FILE:?Set protected absolute clinical env file}"
    : "${BACKUP_REMOTE:?Set approved institutional clinical crypt remote}"
    : "${BACKUP_STATUS_DIR:?Set separate absolute clinical receipt directory}"
    [[ "$CLINICAL_ENV_FILE" = /* && -f "$CLINICAL_ENV_FILE" ]] || {
      echo "Clinical env file must exist at an absolute path" >&2; exit 3;
    }
    [[ "$BACKUP_STATUS_DIR" = /* ]] || {
      echo "Clinical receipt directory must be an absolute path" >&2; exit 3;
    }
    compose=(docker compose --env-file "$CLINICAL_ENV_FILE" -f compose.clinical.yaml)
    expected_db=nims_cmv_clinical
    prefix=nims-cmv-clinical
    ;;
  *) echo "Unknown BACKUP_SCOPE" >&2; exit 3 ;;
esac
[[ "$BACKUP_REMOTE" == ecrfcrypt:* ]] || { echo "Crypt remote required" >&2; exit 3; }
command -v docker >/dev/null && command -v rclone >/dev/null || {
  echo "docker and rclone are required" >&2; exit 3;
}
rclone config show ecrfcrypt | grep -Eq '^[[:space:]]*type[[:space:]]*=[[:space:]]*crypt[[:space:]]*$' || {
  echo "Remote is not an encrypted rclone crypt backend" >&2; exit 3;
}
actual_db=$("${compose[@]}" exec -T db sh -ec 'printf "%s" "$POSTGRES_DB"')
[[ "$actual_db" = "$expected_db" ]] || {
  echo "Wrong Compose database for selected restore scope" >&2; exit 3;
}
archive="$prefix-$stamp.dump"
scratch=$(mktemp -d)
trap 'rm -rf "$scratch"' EXIT
rclone copyto "$BACKUP_REMOTE/$archive" "$scratch/$archive"
[[ -s "$scratch/$archive" ]] || { echo "Retrieved backup empty" >&2; exit 5; }
digest=$(sha256sum "$scratch/$archive" | awk '{print $1}')

# A failed pg_restore, verification query, database deletion or cleanup MUST NOT
# produce a success receipt. Extra tests of restored data are part of site UAT.
"${compose[@]}" exec -T -e TARGET_DB="$test_db" db sh -ec '
  tempfile=$(mktemp /tmp/nims-restore.XXXXXXXX)
  created=0
  cleanup() {
    rm -f "$tempfile"
    if [ "$created" -eq 1 ]; then
      dropdb -U "$POSTGRES_USER" "$TARGET_DB" || echo "WARNING: disposable DB cleanup failed" >&2
    fi
  }
  trap cleanup EXIT
  cat > "$tempfile"
  pg_restore --list "$tempfile" >/dev/null
  if psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT datname FROM pg_database" | grep -Fxq "$TARGET_DB"; then
    echo "Disposable database exists; refusing overwrite" >&2; exit 4
  fi
  createdb -U "$POSTGRES_USER" "$TARGET_DB"
  created=1
  pg_restore --exit-on-error -U "$POSTGRES_USER" -d "$TARGET_DB" --no-owner --no-acl "$tempfile"
  psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$TARGET_DB" -tAc "SELECT count(*) FROM audit_events" >/dev/null
  dropdb -U "$POSTGRES_USER" "$TARGET_DB"
  created=0
' < "$scratch/$archive"

install -d -m 0755 "$BACKUP_STATUS_DIR"
temporary=$(mktemp "$BACKUP_STATUS_DIR/.restore.XXXXXXXX")
printf '%s %s %s\n' "$(date -u +%Y%m%dT%H%M%SZ)" "$digest" "$BACKUP_REMOTE/$archive" > "$temporary"
chmod 0644 "$temporary"
mv -f "$temporary" "$BACKUP_STATUS_DIR/last_restore"
echo "Isolated $scope backup restore verified and disposable DB removed: $stamp"
