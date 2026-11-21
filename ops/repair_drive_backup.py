#!/usr/bin/env python3
"""One-shot, owner-authorized repair of OCI Google Drive backup configuration.

A GitHub Actions secret supplies only the nims_cmv_drive rclone remote through
SSH stdin. No credential, archive, SQL row, token or recovery key is printed.
The repository and GitHub Actions never receive patient data or backup bytes.
"""
import configparser
import fcntl
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.clinical_gate import backup_fresh, restore_verified
from ops import clinical_maintenance as maintenance
from ops import drive_offsite
from ops import operations_status

MAX_REMOTE_CONFIG_BYTES = 65536
MAX_EXISTING_CONFIG_BYTES = 1048576


def parse_supplied_remote(raw: bytes):
    if not raw or len(raw) > MAX_REMOTE_CONFIG_BYTES:
        raise ValueError("bad_remote_size")
    try:
        document = raw.decode("utf-8")
        config = configparser.ConfigParser(interpolation=None, strict=True)
        config.read_string(document)
        if config.sections() != [drive_offsite.REMOTE]:
            raise ValueError("wrong_remote_section")
        remote = config[drive_offsite.REMOTE]
        if (remote.get("type", "").strip() != "drive"
                or remote.get("root_folder_id", "").strip() != drive_offsite.FOLDER_ID):
            raise ValueError("wrong_drive_folder")
        # Only a refreshable OAuth token is imported. A service account file
        # path supplied from a GitHub runner would not exist on OCI.
        token = json.loads(remote.get("token", ""))
        if not isinstance(token, dict) or not isinstance(token.get("refresh_token"), str) or not token["refresh_token"]:
            raise ValueError("nonrefreshable_oauth")
        return dict(remote)
    except (UnicodeError, configparser.Error, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("invalid_drive_remote") from exc


def install_remote(raw: bytes, config_file: Path):
    """Preserve unrelated host remotes. Never overwrite a usable Drive OAuth token."""
    provided = parse_supplied_remote(raw)
    config_file = Path(config_file)
    parent = config_file.parent
    if parent.is_symlink() or config_file.is_symlink():
        raise ValueError("symlinked_rclone_config")
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    parent.chmod(0o700)
    current = configparser.ConfigParser(interpolation=None, strict=True)
    if config_file.exists():
        if not stat.S_ISREG(config_file.stat().st_mode):
            raise ValueError("nonregular_rclone_config")
        if config_file.stat().st_size > MAX_EXISTING_CONFIG_BYTES:
            raise ValueError("oversized_existing_config")
        with config_file.open(encoding="utf-8") as source:
            current.read_file(source)

    os.environ["RCLONE_CONFIG"] = str(config_file)
    if drive_offsite.connection_ready():
        try:
            drive_offsite._rclone("lsf", drive_offsite.REMOTE + ":")
            return False
        except RuntimeError:
            # A dead/expired credential can be replaced by the newly approved
            # GitHub secret, but no other remote will be changed.
            pass

    if current.has_section(drive_offsite.REMOTE):
        current.remove_section(drive_offsite.REMOTE)
    current.add_section(drive_offsite.REMOTE)
    for key, value in provided.items():
        current.set(drive_offsite.REMOTE, key, value)
    output = io.StringIO()
    current.write(output)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=".rclone-drive-", dir=parent)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as dest:
            dest.write(output.getvalue())
            dest.flush()
            os.fsync(dest.fileno())
        os.replace(temporary, config_file)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
    if not drive_offsite.connection_ready():
        raise ValueError("installed_drive_metadata_invalid")
    return True


def lock_file(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    for _ in range(240):
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return handle
        except BlockingIOError:
            time.sleep(0.5)
    handle.close()
    raise RuntimeError("host_maintenance_busy")


def run():
    os.umask(0o077)
    if os.geteuid() == 0:
        raise RuntimeError("must_use_unprivileged_deployment_account")
    if not shutil.which("rclone"):
        raise RuntimeError("rclone_not_installed_on_oci")
    if not (maintenance.STATE / "clinical-active").is_file():
        raise RuntimeError("clinical_service_not_active")
    raw = sys.stdin.buffer.read(MAX_REMOTE_CONFIG_BYTES + 1)
    # Do not read/print rclone config until the exact clinical/deploy locks
    # are held. Do not interrupt the five-minute maintenance job.
    with lock_file(maintenance.STATE / "clinical-maintenance.lock"):
        with lock_file(maintenance.STATE / "deploy.lock"):
            install_remote(raw, Path.home() / ".config/rclone/rclone.conf")
            if not drive_offsite.connection_ready():
                raise RuntimeError("drive_configuration_not_ready")
            drive_offsite._rclone("lsf", drive_offsite.REMOTE + ":")
            # Fresh sealed archive and isolated disposable DB restore, not a
            # reused/expired receipt. Never dump patient data to Actions.
            maintenance.backup_and_restore(maintenance.docker(), force=True)
            if not drive_offsite.sync_latest(maintenance.PRIVATE):
                raise RuntimeError("drive_readback_not_verified")
            state = maintenance.PRIVATE / "backup-state"
            env = {"CLINICAL_BACKUP_RECEIPT_PATH": str(state / "last_success"),
                   "CLINICAL_RESTORE_RECEIPT_PATH": str(state / "last_restore")}
            if not backup_fresh(env) or not restore_verified(env):
                raise RuntimeError("fresh_backup_or_restore_receipt_missing")
    # Re-publish sanitized status without sending config data to GitHub.
    operations_status.write_status(attempt_result="success")
    print("OCI Drive configuration, sealed backup, isolated restore and remote SHA-256 readback verified.")


if __name__ == "__main__":
    try:
        run()
    except Exception:
        # No underlying exception text: provider/SSH failures can contain
        # credential values or temporary URLs.
        print("OCI Drive repair did not pass. Examine the private host diagnostic codes.", file=sys.stderr)
        raise SystemExit(1)
