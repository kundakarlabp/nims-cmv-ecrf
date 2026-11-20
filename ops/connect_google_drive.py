#!/usr/bin/env python3
"""One-time owner-side Google Drive authorization and ciphertext-only backup verification.

Runs on the existing OCI VM as its deployment user, never in GitHub Actions.
Does not read clinical SQL, decrypt recovery archives, or print OAuth credentials.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ops import drive_offsite

PRIVATE = Path.home() / ".local/share/nims-cmv-clinical"


def setup(private_dir=PRIVATE, *, interactive=None):
    """Return a nonzero exit code until exact remote readback succeeds."""
    private_dir = Path(private_dir)
    if not (private_dir / "export").is_dir():
        print("No OCI clinical recovery export directory; run existing maintenance first.")
        return 3
    if not shutil.which("rclone"):
        print("rclone is not installed on OCI; the backup remote cannot be configured.")
        return 4
    if os.geteuid() == 0:
        print("Run as the OCI deployment user, not root, to protect its OAuth configuration.")
        return 5

    config = drive_offsite.config_path()
    if interactive is None:
        interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not drive_offsite.connection_ready():
        if not interactive:
            print("Google authorization is required on OCI. Open an interactive SSH/Cloud Shell session and run: python3 ops/connect_google_drive.py")
            return 2
        print("In the rclone wizard, configure or edit nims_cmv_drive as a Google Drive remote.")
        print("Set root_folder_id to " + drive_offsite.FOLDER_ID + ".")
        print("Complete Google authorization privately; do not paste OAuth tokens into chat or GitHub.")
        config.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            done = subprocess.run(["rclone", "--config", str(config), "config"], check=False)
        except OSError:
            print("Google Drive authorization wizard could not start.")
            return 4
        if done.returncode != 0 or not config.is_file():
            print("Google Drive authorization was not completed.")
            return 2
        config.chmod(0o600)
        if not drive_offsite.connection_ready():
            print("Drive configuration is incomplete or targets a different folder.")
            return 2

    try:
        # No listing or OAuth details are printed. Verify actual Drive access,
        # not just the presence of a cached token or local backup receipt.
        drive_offsite._rclone("lsf", drive_offsite.REMOTE + ":")
        if not drive_offsite.sync_latest(private_dir):
            print("No verified OCI archive or configured remote is available.")
            return 6
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        # Do not print exception contents: an underlying provider may include
        # temporary URLs, bearer tokens or remote names in its messages.
        print("Google Drive access, upload, or independent readback did not pass.")
        return 6
    print("OCI encrypted recovery archive: Drive upload/readback verified; receipts updated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(setup())
