# Backup setup — synthetic staging only

The repository contains `ops/backup_to_drive.sh` and `ops/restore_check.sh`. **They are not connected to Google Drive automatically.** This timer file provides a repeatable six-hour schedule only after an approved external destination, encrypted rclone credentials, and a restore drill have been configured.

## Before enabling anything

1. Obtain the NIMS/institutional data-hosting decision **in writing**. Do not put identifiable patient information in a personal Google Drive account without the required authorization. Keep the staging database synthetic-only.
2. On the OCI VM, install rclone from a trusted source and configure a Google Drive remote in an interactive shell controlled by the owner. Configure a separate `crypt` remote named `ecrfcrypt:` using a separately escrowed, strong crypt password and salt. Keep `~/.config/rclone/rclone.conf` mode 0600. Do not send OAuth tokens, rclone configuration, private keys, or backup dumps through chats, GitHub or email.
3. Confirm the crypt remote's **actual type** (not just its name), the authorized Drive folder, upload quota, user access, and API costs. Encrypt data before leaving the VM.
4. The examples assume source at `/home/ubuntu/nims-cmv` and Docker access by the `ubuntu` user. Check the actual owner and Docker permissions before installing the units.

## Setup on OCI

```bash
cd /home/ubuntu/nims-cmv
export RCLONE_CONFIG=/home/ubuntu/.config/rclone/rclone.conf
chmod 600 "$RCLONE_CONFIG"
rclone listremotes
rclone config show ecrfcrypt | grep -E '^type *= *crypt$'
bash ops/backup_to_drive.sh
sudo install -m 0644 ops/nims-cmv-backup.service /etc/systemd/system/
sudo install -m 0644 ops/nims-cmv-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nims-cmv-backup.timer
sudo systemctl list-timers nims-cmv-backup.timer
sudo systemctl status nims-cmv-backup.service --no-pager
sudo journalctl -u nims-cmv-backup.service -n 40 --no-pager
```

The backup script performs a `pg_dump` to a temporary file with permissions 0600, uploads using rclone crypt, downloads a decrypted stream and checks its SHA-256 hash, then removes its local temporary copy. A successful **backup hash check is not a restore drill**.

## Restore drill

After generating a backup, extract the timestamp from the script's completion message, and run:

```bash
export RCLONE_CONFIG=/home/ubuntu/.config/rclone/rclone.conf
bash ops/restore_check.sh YYYYMMDDTHHMMSSZ nims_restorecheck
```

The script creates a separate database (it will not overwrite `nims_ecrf`). After independently validating the schema and synthetic records, remove the disposable test database using a reviewed command. Perform monthly restore drills and keep a second independent encrypted copy, with a recovery key protected separately from the server.

**Monitoring required:** examine the timer and journal daily, alert when the most recent success is older than 8 hours, track available OCI disk and Drive quota, and test recovery after server loss. A systemd timer alone does not provide reliable off-host monitoring, RPO/RTO guarantees, or authorization for PHI.

**Do not enable a live-patient backup schedule until security, governance, and go-live checks are signed off.** 
