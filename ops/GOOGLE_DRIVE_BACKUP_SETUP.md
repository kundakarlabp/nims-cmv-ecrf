# NIMS CMV — recover the encrypted Google Drive clinical backup

OCI clinical data and the randomization key stay on the existing host. The
existing backup procedure makes an encrypted archive, verifies a disposable
PostgreSQL restore, then uploads the **ciphertext only** to the designated
private Drive folder and reads those exact bytes back before writing receipts.

Target folder: `1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM`.

**Do not disable** the eight-hour backup freshness gate or fabricate receipts
to permit enrollment. The clinic can remain read-only while the backup is stale.

## Option A: existing trusted interactive OCI setup (no Google secret in GitHub)

On OCI as the unprivileged deployment user, after signing in privately:

    cd /home/ubuntu/nims-cmv
    python3 ops/connect_google_drive.py

Complete Google authorization as the approved Drive owner, name the remote
`nims_cmv_drive`, and set `root_folder_id` to the exact folder above. Rclone
config is stored privately at `~/.config/rclone/rclone.conf` with mode `0600`.
The helper checks access and upload/download SHA-256 verification. The OCI
maintenance timer keeps subsequent copies current.

## Option B: GitHub Actions repair (requested by project owner)

This requires a **one-time Google authorization on a trusted personal device**
and an SSH identity already authorized on OCI. GitHub cannot invent a Drive OAuth
refresh token or SSH identity from the ChatGPT Google Drive connection.

The private GitHub repository must have these three Actions **repository
secrets**, entered by the owner in GitHub Settings → Secrets and variables →
Actions. Do not commit them, attach them to issues, or paste them into chat.

1. `OCI_SSH_PRIVATE_KEY`: dedicated SSH private key authorized for the OCI
   `ubuntu` deployment account. Prefer a scoped deployment key rather than a
   personal master key. Noninteractive runners cannot prompt for a passphrase.
2. `OCI_SSH_KNOWN_HOSTS`: the actual OCI server public host-key line for
   `152.70.77.77`, verified independently from an owner-managed connection.
   Never rely on `StrictHostKeyChecking=no` or blindly trust
   a key collected inside the Actions runner.
3. `CMV_DRIVE_RCLONE_CONFIG_B64`: base64 encoding of a **single remote section**
   obtained privately from successful owner-authorized `rclone config`:
   `[nims_cmv_drive]`, `type = drive`, exact `root_folder_id` above, and
   a refreshable JSON `token` containing a `refresh_token`. Do not include
   unrelated rclone remotes or clinical databases in this secret. Encoded
   configuration is still a secret.

Run **Actions → Repair OCI Google Drive clinical backup → Run workflow** on
`main`, or let it run after a successful reviewed release. The job uses
fixed SSH commands, a pinned host key and protected Actions secrets. The
credential crosses to OCI through encrypted SSH stdin and is merged into the
deployment user's existing rclone configuration; unrelated remotes are
preserved. It never uploads archives, clinical tables or recovery keys to the
GitHub runner.

The host repair command acquires both maintenance and deployment locks, creates
a **fresh** encrypted archive, checks an isolated database restore, uploads the
sealed archive to the exact Drive folder, downloads it, verifies size and
SHA-256, and finally checks the app-readable freshness receipts. Public
`/readyz` verification must report clinical write readiness before the action
succeeds.

If the action reports **missing Actions secrets** or **SSH authentication**
failure, provide the three secrets privately through GitHub Settings. If
**Google authentication fails**, reauthorize `nims_cmv_drive` on a trusted
device and replace its secret. The runner never logs actual credentials.

OCI independently owns scheduled follow-up backups and rclone token refresh.
Keep a tested recovery-key escrow outside OCI. The Drive folder must be
approved for encrypted trial recovery under institutional governance; a
personally owned account alone does not establish institutional approval.

## How completion is verified

Check NIMS CMV OCI operations after the action finishes:

- Google Drive configuration present and offsite receipt fresh (under 8 hours).
- Current isolated-restore proof (under 30 days).
- Clinical write readiness true, database reachable, no backup blocker.
- OCI running/deployed/approved application commits reconciled.

Successful GitHub CI, workflow creation, or an OAuth configuration file alone
does **not** prove that an offsite recovery copy exists. Do not mark the repair
complete until runtime checks pass.

Retention is limited to the 28 latest correctly named recovery archives. The
existing uploader does not delete unrelated Drive files.
