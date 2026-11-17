# Clinical activation and recovery

The owner authorized activation on 17 November 2026. The exact instruction is
recorded in `clinical-authorization.json`; it is not an institutional signature
or a claim that a human performed UAT. Automated PostgreSQL, application,
permission, MFA, ciphertext identity and actual restore checks run before release.

The existing five-minute VM timer maintains a separate clinical PostgreSQL
database and restricted application role. Only named accounts, password hashes,
MFA enrollment and staff authorizations migrate. Staging participant records and
sessions are not imported. Existing staging volumes are retained. The uniquely
identified owner administrator also receives explicit PI authorization; ordinary
IT administrators do not acquire clinical or allocation privileges.

Mandatory MFA supports a ten-minute first-use enrollment session that cannot
read records or use clinical endpoints. Enrollment revokes every old session;
the owner signs in again with both factors. Repeated wrong codes lock attempts
for fifteen minutes. Secrets are displayed privately to the account holder.

Every two hours, maintenance encrypts a PostgreSQL custom-format dump and
restores the exact decrypted archive into a separate, uniquely named disposable
database, verifies its baseline and queries, then removes that disposable DB.
It never restores into the live database. The separate backup and allocation
keys are also age-encrypted to the owner's existing SSH public key recipients.
**Retain the original owner SSH private key outside the VM**: ciphertext and
an encrypted recovery-key envelope cannot recover themselves after VM loss.
The CI check tests this complete recovery process with its own disposable key.

A private GitHub Actions workflow runs every three hours and after an approved
release. Its short-lived OIDC identity is restricted to this exact private
repository, owner ID, main branch and workflow. The service permits only
ciphertext download and acknowledgment. After private artifact upload, GitHub
downloads the artifact again and compares its SHA-256 before acknowledging it.
Only then does the host issue an offsite receipt. Backups have two-day private
artifact retention, twenty-four-hour local ciphertext retention, and a 32 MiB
encrypted bundle limit. No paid resources are automatically enabled. Larger
databases or exhausted Actions quota require a reviewed capacity adjustment.

The first cutover waits for both an isolated restore and offsite readback. Once
the clinical marker is set, every later deployment stays on the clinical stack,
including application rollback. No automatic fallback to the staging database
is allowed. Clinical writes pause if a backup receipt is over eight hours old;
sign-in and read-only review remain available.

The protocol v5 sequence is **not automatically generated during deployment**.
The investigator appoints a person who does not determine eligibility and
invites that person under the `randomization_custodian` role. After named login
and MFA enrollment, that person imports a separately prepared signed sequence,
or personally supplies the final specification reference and prespecified
variable block sizes to generate and permanently lock it in the interface.
All four strata have capacity for the whole trial; future allocations remain
encrypted and are never displayed. Only the PI releases the next allocation
after consent, eligibility, stratification and enrollment checks. Ordinary
registration/screening/data capture do not require a randomization sequence.

Public `/readyz` exposes service mode, database reachability, clinical entry
availability, source fingerprint and only enum-valued transition diagnostics.
It exposes no records, usernames, keys, raw logs or server commands. GitHub
release verification uses this public health surface only.
