# NIMS CMV trial workflow readiness

Grant IIRPIG(NAG)-I-2026-01-0634-F2; provisional repo protocol v5.0 / draft CRF v3.0. This implementation must still be reconciled against the final signed documents. The 552-field reference dictionary is provisional.

## Implemented for synthetic staging

- Screening: consent version/date, donor/recipient CMV IgG, donor type, rATG, eligibility attestation, unique screening ID and actor audit.
- Enrollment: PI-only confirmation of eligibility and consent, unique subject ID, signed PCR anchor attestation, seven coded CMV PCR worklist entries at months 1,2,3,4,6,9 and 12.
- PCR: collection with accession ID, structured detection category and IU/mL, assay QC, revision conflict controls, independently verified results and justified repeat specimens.
- Pharmacy: lot receipt and stock, signed paper prescription reference, renal assessment and external allocation reference, unique MSS dispensing code, atomic decrement, returned-tablet log and nonautomatic restock.
- Users: individual invitations with seven-day one-time activation tokens and 90-day named access renewal/revocation; users select their own passwords, optional TOTP authenticator setup, repeated-password failure lockout, role-specific views.
- Backup: six-hour timer template, encrypted rclone Drive uploads with SHA-256 roundtrip, isolated restore-test script, success receipt and freshness monitor.

## Clinical go-live blockers: MUST be cleared before identifiable records

1. Validate all consent, inclusion/exclusion, safety, renal-dose and follow-up fields against signed NIEC/ICMR/CTRI protocol, CRF and amendments. The existing screening endpoint is NOT a replacement for the detailed eligibility checklist.
2. Import and validate an independently generated, concealed, stratified randomization allocation list; currently the entered external allocation reference is not independently checked and cannot justify medication dispensing.
3. Complete a separate prescribing/renal-adjustment validation and pharmacist countersignature. The dose-preview API is not a prescription.
4. Deploy versioned schema migrations with restricted DB roles and tamper-evident append-only audit; no automatic schema creation in production.
5. Complete named-user MFA enrollment, delegated permission audit, revocation, password recovery, multiuser conflict/load test and signed UAT.
6. Obtain institutional written approval for outside-host data storage, encrypted identity vault, personal versus institutional Drive use, data retention and incident response.
7. Configure Oracle-side encrypted Google Drive OAuth and scheduled backups; prove successful independent restoration, monitor failures and store a second recovery copy. Scripts alone do not establish working backups.
8. Verify Oracle deployment pull timer, correct image version, HTTPS, database readiness, release rollback and 15 concurrent-user workflows.
9. Keep real patient data blocked until signed PI, administration, ethics and data governance release verification.

## Access design

PI: enrollment confirmation, review, clinical authorization, staff invitations.
Consultant: screening, clinical review and prescriptions, but not PI-only enrollment.
Scientist: screening/data management/follow-up and independent review.
Nurse: follow-up and sample collection.
Technician/microbiology: sample collection and PCR result entry, no self-review.
MSS pharmacist: lot, issue and return; no randomization assignment.
Monitor/CRA: pseudonymous review without names or CR numbers.
PG: clinical entries only. IT admin: account/system support without clinical enrollment privileges.

Never issue shared role passwords. Each named staff member receives a separately authorized invitation and sets their own password and authenticator. No actual accounts are provisioned until identity is verified in the live server.

## Synthetic-only technical gate

CLINICAL_DATA_ENABLED defaults false: TEST- CR numbers and Synthetic-prefixed names are required. If it is enabled the app requires MFA_REQUIRED true and a protected clinical signoff file at CLINICAL_GOLIVE_ATTESTATION_PATH, and disables automatic table creation. A file alone does not establish institutional approval. Do not reuse synthetic data as clinical records.


## CRF v3.0 account and form upgrade (16 November 2026)

Source-aligned CRF A/B eligibility and source-link metadata, typed sections C–L, autosave/review and staff expiry controls are described in `ops/CRF_V3_IMPLEMENTATION_MATRIX.md`. This does not eliminate the independent randomization, institutional authorization, server backup and signed UAT gates. Account access validity defaults to 90 days after activation; initial invite tokens last seven days.
