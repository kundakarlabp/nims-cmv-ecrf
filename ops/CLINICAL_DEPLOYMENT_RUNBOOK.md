# Clinical patient-entry deployment — controlled release

## Why the screenshot still says staging

The current Oracle URL is **synthetic-only staging**. Its existing database and accounts are not automatically a valid clinical trial production environment. Do not enter real patient names or hospital CR identifiers there. A GitHub merge does not change institutional release status.

A new, **standalone** compose.clinical.yaml provisions the nims-cmv-clinical project with an independent clinical_postgres_data volume and dedicated Caddy volumes. Do **not** combine it with staging compose.yaml or import test subjects/accounts. The former staging auto-deploy timer is NOT authorized to activate the clinical project.

## Release requirements

- Institutional/PI/IEC data-hosting and clinical release authorization, signed UAT, final approved protocol and consent forms; signed go-live file and its SHA-256 fingerprint remain outside GitHub.
- Separately provisioned PostgreSQL nims_cmv_clinical with nims_clinical_owner and a restricted nims_clinical_app role, initialized only by a human-authorized one-time command. App cannot make schema changes during clinical runtime.
- Active named staff and initial admin with authenticator MFA; each staff account is valid 90 days after activation, individually renewable/revocable.
- Independently approved four-stratum concealed sequence, protected randomization key (separate from DB) and signed original sequence SHA-256.
- Encrypted offsite backup on an **approved** institutional destination, successful verified upload and isolated full-restore drill, separate recovery key backup and alerting.
- Domain approved for patient records, TLS, source verification, audit review, pharmacy and lab UAT, incident response and written ownership of recovery.

## Dedicated schema and staff provisioning

1. Prepare one private **0600** clinical Compose env file with distinct owner/app passwords, outside GitHub and chat. Verify that `docker compose --env-file /secure/private/nims-cmv-clinical.env -f compose.clinical.yaml config --quiet` succeeds and that `nims-cmv-clinical` and `clinical_postgres_data` are the selected project/volume. A single VM cannot run both staging and clinical Caddy on ports 80/443; use a separate approved instance or a planned cutover without deleting staging volumes.
2. Start **only** clinical PostgreSQL, provision an empty schema once, and set up the initial administrator via the dedicated one-time services. App services are not started or granted clinical write access during setup:

   ```bash
   cd /home/ubuntu/nims-cmv
   export CLINICAL_ENV_FILE=/secure/private/nims-cmv-clinical.env
   docker compose --env-file "$CLINICAL_ENV_FILE" -f compose.clinical.yaml up -d db
   docker compose --env-file "$CLINICAL_ENV_FILE" -f compose.clinical.yaml --profile provision run --rm schema-bootstrap
   docker compose --env-file "$CLINICAL_ENV_FILE" -f compose.clinical.yaml --profile provision run --rm admin-bootstrap
   docker compose --env-file "$CLINICAL_ENV_FILE" -f compose.clinical.yaml --profile provision run --rm admin-bootstrap python /srv/clinical_admin_mfa.py
   ```

   The schema provisioner refuses existing tables. It stamps a checked structural fingerprint, creates a least-privilege application role and protects the audit table. The first admin chooses a private password and confirms an authenticator interactively. No default account or shared trial password is created. DO NOT copy passwords, authenticator secrets or private configuration into chat. The neutral clinical Compose placeholders intentionally allow DB-only setup before signing release; they **do not** let the API start as clinical until every actual authorization and recovery check passes.
4. Set up and escrow the randomization Fernet key. The independent statistician/custodian prepares the signed allocation sequence; never import a synthetic test sequence as the official assignment list.
5. Configure the approved encrypted cloud destination on the VM (never in Git). Clinical backups **must** use BACKUP_SCOPE=clinical, a protected absolute CLINICAL_ENV_FILE, an institutional ecrfcrypt: BACKUP_REMOTE, and a separate absolute BACKUP_STATUS_DIR, not staging defaults. Use the following operations after verifying the new database and source data authorization:

   ```bash
   cd /home/ubuntu/nims-cmv
   export BACKUP_SCOPE=clinical
   export CLINICAL_ENV_FILE=/secure/private/nims-cmv-clinical.env
   export RCLONE_CONFIG=/secure/private/rclone.conf
   export BACKUP_REMOTE=ecrfcrypt:approved-nims-cmv-clinical
   export BACKUP_STATUS_DIR=/secure/state/nims-cmv-clinical
   bash ops/backup_to_drive.sh
   STAMP=$(awk '{print $1}' "$BACKUP_STATUS_DIR/last_success")
   bash ops/restore_check.sh "$STAMP" nims_restoretrial
   ```

   Replace example paths with actual protected paths on the authorized host. A successful backup now proves crypt-backend type and decrypted SHA-256 roundtrip. Restore verifies a **separate disposable database** and cleans it up before creating a receipt. Check actual app-readable receipts, at most eight hours old for last_success and thirty days for last_restore. Receipt files contain only timestamp/hash/crypt reference and are mode 0644 within a 0755 directory mounted READ ONLY for API UID 10001. They do not contain patient data or cloud secrets. Keep a second independent encrypted copy and escrow the key.
6. Record the actual signed release document; calculate its SHA-256. Set institutional and UAT release flags to verified ONLY after approval. The clinical app then checks all release conditions, schema fingerprint and absence of DDL privileges at startup. It refuses startup if these checks fail.
7. Use the authenticated /api/system/mode endpoint to confirm mode=clinical and clinical_registration_enabled=true. Independently validate registration, enrollment, PCR, pharmacy, randomization, audit and recovery with authorized nonpatient test vectors. Only then commence enrolling real study participants.

## Safe behavior

The ordinary staging project cannot accept non-synthetic patient records. The clinical app pauses clinical writes if the verified offsite backup receipt is too old or the isolated restore evidence expires; read-only review/login remain possible. User interfaces show the backend's actual mode rather than just changing a banner.

A baseline schema bootstrap is not an Alembic upgrade framework. All subsequent schema changes require explicit reviewed migrations and rollback. The application is not yet certified as a validated GCP EDC merely by passing GitHub CI, and clinical release requires human institutional authority and real Oracle operational verification.
