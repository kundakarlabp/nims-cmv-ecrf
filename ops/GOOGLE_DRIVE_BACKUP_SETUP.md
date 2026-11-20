# OCI to Google Drive clinical recovery (no GitHub backup storage)

The source implementation is ready for review. Production backup is NOT verified
until OCI has a working Google Drive OAuth connection.

## Verified destination

Private owner-only folder:
https://drive.google.com/drive/folders/1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM

Google Drive reports owner kundakarlabp@gmail.com and shared=false. The PI
must confirm that institutional data-governance permits this personally owned
destination before exporting identifiable trial records.

## One-time OCI setup

After the next CI-approved deployment, open a private interactive terminal on
the existing OCI VM, signed in as the deployment user (`ubuntu`), and run:

```sh
cd /home/ubuntu/nims-cmv
python3 ops/connect_google_drive.py
```

This helper reuses an already-authorized `nims_cmv_drive` remote, or launches
the normal Google authorization wizard if absent. Select the exact private
folder ID below. It protects the config, verifies real Drive access, uploads
only the newest **already encrypted and isolated-restore-verified** archive,
downloads that exact object and checks its size and SHA-256 before writing
recovery receipts. It never handles patient-level application records or
prints credentials. Do not run the interactive wizard under `sudo` or in
GitHub Actions; it must use the OCI deployment user's protected config.

The CI/release workflow deploys this helper but deliberately cannot create
Google OAuth authorization or remotely read tokens. A consent step with the
Drive owner is unavoidable. See current rclone guidance for a headless OAuth
authorization and a dedicated Google OAuth client ID when necessary.

If the host has no `rclone`, install it from the operating system's verified
package repository before running the helper. The existing five-minute OCI
maintenance timer will continue automatic copies after the initial consent.

The ChatGPT Google Drive connection does NOT authenticate rclone on the Oracle
instance. Never paste Google OAuth tokens, config, or private keys in GitHub
or chat.

1. On OCI as the deployment owner run: rclone version; rclone listremotes
2. If a Google Drive remote is already configured for the correct owner,
   use rclone config, COPY that remote to name nims_cmv_drive, EDIT it and set
   the advanced root_folder_id to 1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM.
   If none exists, run rclone config and create the drive remote under that
   name and root folder ID, then authorize it in your Google browser.
3. Protect the private file: chmod 600 ~/.config/rclone/rclone.conf
4. Test on OCI: rclone lsf nims_cmv_drive:
5. Test from the deployed repository:
   python3 -c 'from ops.drive_offsite import connection_ready; print(connection_ready())'
   It must output True. Do not display the OAuth token or configuration file.
6. The existing OCI five-minute deployment/maintenance timer handles recovery
   transfers. It creates a new clinical PostgreSQL archive around every six
   hours, verifies an isolated restoration, uploads the already sealed bundle,
   checks downloaded bytes, and writes verified backup/restore receipts.
7. The administrator can see Drive-configured and Drive-receipt states on
   /operations. Check the actual patient entry readiness separately.

## Storage and protections

The existing clinical recovery archive is sealed AUTOMATICALLY on OCI before
upload; you do not need to set up another rclone crypt remote or key. A direct
Google Drive remote and HTTPS transport are used. No backup is uploaded into
GitHub Actions, releases, issues or Supabase. Only this folder is targeted.

The 28 latest recovery objects are retained (at the existing 32 MiB cap,
under approximately 900 MiB total). Only precisely matched old recovery
objects are pruned. No other files on Drive are deleted.

A source-code release or remote configuration alone is NOT proof of an actual
Drive backup. Completion requires remote readback/sha256 and a successful
disposable-PostgreSQL restore. Keep the owner-held SSH private key used for
the existing recovery-key escrow outside OCI.

Normal public GitHub code CI and OCI release workflow remain. The failing
GitHub clinical-backup workflow and release-triggered dispatch are retired.

If backup freshness passes eight hours without a verified copy, clinical
writes may pause while login and read access remain available. Verify Drive
quota and renewal of the OAuth connection during ongoing operations.
