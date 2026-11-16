# Clinical patient-entry deployment — controlled release

## Why the screenshot still says staging

The current Oracle URL is **synthetic-only staging**. Its existing database and accounts are not automatically a valid clinical trial production environment. Do not enter real patient names or hospital CR identifiers there. A GitHub merge does not change institutional release status.

A new Compose override called compose.clinical.yaml provisions a separate project named nims-cmv-clinical and a separate clinical_postgres_data volume, with no staging test-record migration. The former staging auto-deploy timer is NOT authorized to activate the clinical project.

## Release requirements

- Institutional/PI/IEC data-hosting and clinical release authorization, signed UAT, final approved protocol and consent forms; signed go-live file and its SHA-256 fingerprint remain outside GitHub.
- Separately provisioned PostgreSQL nims_cmv_clinical with nims_clinical_owner and a restricted nims_clinical_app role, initialized only by a human-authorized one-time command. App cannot make schema changes during clinical runtime.
- Active named staff and initial admin with authenticator MFA; each staff account is valid 90 days after activation, individually renewable/revocable.
- Independently approved four-stratum concealed sequence, protected randomization key (separate from DB) and signed original sequence SHA-256.
- Encrypted offsite backup on an **approved** institutional destination, successful verified upload and isolated full-restore drill, separate recovery key backup and alerting.
- Domain approved for patient records, TLS, source verification, audit review, pharmacy and lab UAT, incident response and written ownership of recovery.

## Dedicated schema and staff provisioning

1. Keep a private 0600 clinical configuration and passwords outside GitHub/chat. Verify that both Compose files resolve to the nims-cmv-clinical project and a distinct clinical data volume. On a single VM, the staging and clinical web front ends cannot simultaneously bind ports 80/443. Use a separately approved hostname/instance or a planned cutover with staging protected.
2. Start ONLY the new clinical PostgreSQL container while its API is stopped. On an empty database, use a separate protected bootstrap environment file to run python /srv/clinical_schema_bootstrap.py as the **database owner**, with CLINICAL_SCHEMA_BOOTSTRAP=true, CLINICAL_DATA_ENABLED=false, and the separately supplied app-role password. The script refuses any existing tables, records a model schema fingerprint, creates a restricted app role and protects the audit table from UPDATE/DELETE.
3. Under the **application** DB role in explicit bootstrap mode, run python /srv/bootstrap_admin.py, then python /srv/clinical_admin_mfa.py interactively to configure the initial admin authenticator. Do not transmit passwords or OTP setup codes through ChatGPT.
4. Set up and escrow the randomization Fernet key. The independent statistician/custodian prepares the signed allocation sequence; never import a synthetic test sequence as the official assignment list.
5. Configure approved encrypted cloud backup credentials on the VM (never in Git), run ops/backup_to_drive.sh and then ops/restore_check.sh on a disposable restore database. Ensure .backup-state/last_success is within eight hours and last_restore within thirty days. The mounted evidence must be readable by API UID 10001 and protected from modification by that user.
6. Record the actual signed release document; calculate its SHA-256. Set institutional and UAT release flags to verified ONLY after approval. The clinical app then checks all release conditions, schema fingerprint and absence of DDL privileges at startup. It refuses startup if these checks fail.
7. Use the authenticated /api/system/mode endpoint to confirm mode=clinical and clinical_registration_enabled=true. Independently validate registration, enrollment, PCR, pharmacy, randomization, audit and recovery with authorized nonpatient test vectors. Only then commence enrolling real study participants.

## Safe behavior

The ordinary staging project cannot accept non-synthetic patient records. The clinical app pauses clinical writes if the verified offsite backup receipt is too old or the isolated restore evidence expires; read-only review/login remain possible. User interfaces show the backend's actual mode rather than just changing a banner.

A baseline schema bootstrap is not an Alembic upgrade framework. All subsequent schema changes require explicit reviewed migrations and rollback. The application is not yet certified as a validated GCP EDC merely by passing GitHub CI, and clinical release requires human institutional authority and real Oracle operational verification.
