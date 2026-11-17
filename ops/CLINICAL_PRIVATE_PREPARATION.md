# Automatic private clinical configuration preparation

Reviewed deployments and subsequent pull-timer cycles run
ops/prepare_clinical.py on the VM as its existing deployment user. It prepares
~/.local/share/nims-cmv-clinical/clinical.env and allocation.key privately,
with a mode-0700 directory and mode-0600 files, outside the Git checkout.
Owner/app DB passwords are independently generated; the 32-byte allocation
encryption key does not generate or approve a randomization sequence.

Existing regular files are preserved and never rotated. Invalid existing
configuration needs operator review. Passwords, keys and configuration values
are never returned in status responses or printed into deployment logs.

This step does not start another database or web server, copy staging records
or accounts, enable clinical mode, assert institutional approval/UAT, sign
release documents, configure cloud OAuth or claim a successful backup/restore.
The clinical Compose file remains a separate, explicit deployment pathway.

The operations page reports only file/tool/configuration presence. A crypt
configuration entry is not proof that its credentials work or that restoration
succeeded. Inaccessible or encrypted configuration reports an unknown state.
After the first upgrade, the next five-minute timer cycle performs preparation
even when no further release is pending.

Deploy/rollback pass APP_COMMIT as an explicit Docker build argument because
sudo may strip exported environment variables. This takes effect when the
updated deploy script is the one executing a subsequent release.
