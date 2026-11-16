# Controlled randomization SOP — NIMS ICMR CMV, Protocol v5.0

Grant IIRPIG(NAG)-I-2026-01-0634; D+/R+ kidney transplant trial, nominal valganciclovir 450 mg OD versus 900 mg OD for three months. The application remains **synthetic-only staging** until full clinical validation.

## Approved scheme
1. Computer-generated 1:1 randomization with **variable permuted blocks**.
2. Four strata: rATG induction yes/no crossed with donor living/deceased.
3. The final block-size specification is NOT stated numerically in protocol v5.0; an independent statistician must predefine, date, sign, and lock it before the first real enrollment. The offline generator supports 4 and 6 as **examples**, not as signed approved sizes.
4. Conceal future allocations from investigators, pharmacist and monitors. Only released individual arms may be disclosed (open-label treatment). Do not show accumulated arm-balance summaries to recruiters, because they can aid prediction near a block boundary.
5. Statistician/custodian must be independent from eligibility confirmation. Sequentially numbered opaque envelopes are an independently prepared contingency, not an uncontrolled second allocation mechanism.

## Sequence setup (independent custodian; once only)

1. Independent statistician signs the final block sizes, capacity, four strata, custody process and a sequence fingerprint.
2. On a separately encrypted workstation, run the offline helper at ops/prepare_statistician_sequence.py with a **secure local output file** and explicit signed specification/reference. Example command:
   python ops/prepare_statistician_sequence.py --out /secure-volume/CMV-sealed-sequence.json --slots-per-stratum 120 --block-sizes 4,6 --statistician-reference STAT-SIGNED-2026-001 --signed-specification-reference FINAL-SPEC-2026-001
3. No signed sequence is committed to GitHub, sent through chat, ordinary email, or unencrypted shared Drive. Package content contains future treatment allocations; restrict custody.
4. IT configures RANDOMIZATION_FERNET_KEY in a protected secrets file separate from DB and Git. Escrow its recovery copy securely: losing the key makes existing allocations unreadable.
5. Admin creates an independent named randomization_custodian account. PI cannot create or impersonate a custodian. Staff activate individual 90-day credentials with MFA.
6. Custodian uploads the signed package in the dashboard. API verifies SHA-256, all four strata, contiguous positions, balanced variable blocks, then encrypts each future arm at rest. A database uniqueness rule prevents importing a second plan.
7. For eventual clinical activation, RANDOMIZATION_APPROVED_SHA256 must match the official signed fingerprint, and RANDOMIZATION_ENABLED must be true after signed UAT, migration, approved data governance and demonstrated full backup restoration. **Never set these flags simply to bypass validation.**

## Patient flow
1. Screen a prospective D+/R+ participant; verify signed ICF and protocol v5.0 eligibility/exclusions, ANC/platelets/Hb and Cockcroft–Gault CrCl.
2. PI approves enrollment within protocol window. The seven scheduled CMV PCR milestones are anchored to transplant date: months 1, 2, 3, 4, 6, 9, 12.
3. PI selects an eligible enrolled subject, confirms stratification and signed source, and requests irreversible **Randomize**. The server atomically claims the earliest available sealed slot in the correct stratum. No user can select an arm or rerandomize.
4. After allocation, the PI sees unique code and nominal arm. PI/consultant/MSS pharmacist may retrieve released arm; blinded monitors receive coded status only.
5. Clinician signs a separate renal-adjusted prescription, referencing the actual allocation code. MSS dispensing is blocked unless prescription and locked allocation match.
6. Baseline CRF randomization fields are read-only derived data and cannot be overridden by typing arbitrary treatment arms.

## Renal adjustment (protocol reference, not an order)
CrCl >=60: 900-mg arm 900 mg OD; 450-mg arm 450 mg OD.
CrCl 40–59: both arms 450 mg OD.
CrCl 25–39: both arms 450 mg every 48 hours.
CrCl 10–24: both arms 450 mg twice weekly.
CrCl <10/HD: withhold trial tablets; clinician manages safely.

## Release checklist
Independent locked sequence / signed statistician specification, secure Fernet key escrow, no allocation leakage, four-stratum test vectors, double-click and concurrency tests, no duplicate allocations, pharmacy cross-check, full signed CRF UAT, live database migration, roles/MFA, backup and isolated restoration, and actual Oracle app/version check must ALL pass before the first real participant is randomized.

This repository contains no real participant allocation sequence. No clinical activation has been performed.
