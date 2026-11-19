"""Upload already-sealed OCI clinical recovery bundles to the owner's PRIVATE Drive folder.

Uses the existing Google Drive OAuth remote directly, without GitHub Actions
storage, a new database or a second rclone crypt remote. Backups remain
automatically encrypted by clinical_maintenance before leaving OCI.
"""
import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

FOLDER_ID = "1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM"
REMOTE = "nims_cmv_drive"
FILE_RE = re.compile(r"^clinical-([0-9]{8}T[0-9]{6}Z-[0-9a-f]{12})\.tar$")
BUNDLE_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
KEEP_LATEST = 28   # Maximum about 896 MiB at the existing 32 MiB per-bundle cap.
MAX_BUNDLE_BYTES = 32 * 1024 * 1024


def config_path():
    return Path(os.environ.get(
        "RCLONE_CONFIG", str(Path.home() / ".config/rclone/rclone.conf")))


def connection_ready(config=None):
    """Read only config metadata; never return OAuth credentials or tokens."""
    path = config or config_path()
    try:
        path = Path(path)
        if path.stat().st_mode & 0o077:
            return False
        parser = configparser.ConfigParser(interpolation=None)
        with path.open(encoding="utf-8") as file:
            parser.read_file(file)
        return (parser.has_section(REMOTE)
                and parser.get(REMOTE, "type", fallback="").strip() == "drive"
                and parser.get(REMOTE, "root_folder_id", fallback="").strip() == FOLDER_ID
                and bool(parser.get(REMOTE, "token", fallback="").strip()
                         or parser.get(REMOTE, "service_account_file", fallback="").strip()))
    except (OSError, UnicodeError, configparser.Error):
        return False


def _rclone(*args):
    if not shutil.which("rclone"):
        raise RuntimeError("Google Drive backup requires rclone on OCI")
    try:
        result = subprocess.run(
            ["rclone", "--config", str(config_path()), *map(str, args)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=240, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Google Drive backup unavailable") from error
    if result.returncode != 0:
        # Never expose stderr: rclone errors may include credentialed URLs.
        raise RuntimeError("Google Drive transfer/readback failed")
    return result.stdout


def _prune_remote():
    """Delete only our own oldest backup objects, retaining 28 verified copies."""
    items = json.loads(_rclone("lsjson", REMOTE + ":", "--files-only", "--max-depth", "1"))
    if not isinstance(items, list):
        raise RuntimeError("Unexpected Google Drive listing")
    names = sorted(item["Name"] for item in items if isinstance(item, dict)
                   and isinstance(item.get("Name"), str)
                   and FILE_RE.fullmatch(item["Name"]))
    for old in names[:-KEEP_LATEST]:
        _rclone("deletefile", REMOTE + ":" + old)


def sync_latest(private_dir):
    """Return False if OAuth is not configured; never fake a backup receipt."""
    private_dir = Path(private_dir)
    if not connection_ready():
        return False
    manifests = sorted((private_dir / "export").glob("*.json"))
    if not manifests:
        return False
    manifest_path = manifests[-1]
    if not BUNDLE_RE.fullmatch(manifest_path.stem):
        raise RuntimeError("Invalid clinical bundle name")
    manifest = json.loads(manifest_path.read_text())
    if (manifest.get("id") != manifest_path.stem or
            manifest.get("restore_verified") is not True or
            not re.fullmatch(r"[0-9a-f]{64}", manifest.get("sha256", ""))):
        raise RuntimeError("Invalid restored bundle manifest")
    bundle = private_dir / "export" / (manifest["id"] + ".tar")
    if bundle.is_symlink() or not bundle.is_file():
        raise RuntimeError("Missing sealed backup archive")
    if bundle.stat().st_size != manifest.get("size") or bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise RuntimeError("Sealed backup length mismatch")
    digest = hashlib.sha256(bundle.read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        raise RuntimeError("Sealed backup digest mismatch")

    remote_file = REMOTE + ":clinical-" + manifest["id"] + ".tar"
    receipt_dir = private_dir / "backup-state"
    receipt = receipt_dir / "last_success"
    if receipt.is_file():
        parts = receipt.read_text().split()
        if len(parts) == 3 and parts[0] == manifest["stamp"] and parts[1] == digest:
            return True

    _rclone("copyto", bundle, remote_file, "--retries", "3",
            "--low-level-retries", "6")
    # Verify the exact remote bytes, not the local upload status.
    verified = _rclone("cat", remote_file)
    if hashlib.sha256(verified).hexdigest() != digest:
        raise RuntimeError("Google Drive readback hash mismatch")

    reference = f"gdrive:{FOLDER_ID}:clinical-{manifest['id']}.tar"
    line = f"{manifest['stamp']} {digest} {reference}\n".encode()
    receipt_dir.mkdir(mode=0o755, exist_ok=True)
    # Both receipts refer to the same bundle restored in an isolated DB before
    # uploading and independently read back from Drive.
    from ops.clinical_maintenance import atomic
    atomic(receipt_dir / "last_success", line, 0o644)
    atomic(receipt_dir / "last_restore", line, 0o644)
    try:
        _prune_remote()
    except (RuntimeError, ValueError, KeyError, TypeError):
        # Retention is best effort; a valid verified recovery receipt survives.
        pass
    return True
