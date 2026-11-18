# Active workspace configuration — 18 November 2026

The owner confirmed that the 15 filled rows in the previous randomization workbook were training examples and explicitly requested their removal, a fresh start, username/password-only login, and removal of the separate custodian requirement.

## Current access

- Active named accounts sign in with their existing username and password. MFA enrollment and OTP entry are disabled by the explicit owner policy. Existing passwords are preserved.
- Named study accounts share clinical workspace access: screening, eligibility recording, enrollment, randomization, laboratory entry, dispensing, correction and source review. Reviews retain the actual account identity, including reviews by an entry author.
- User creation, privileged account changes and account disabling remain controlled by the original administrator/investigator permissions. Existing 90-day staff authorization remains available.
- Consent, medical eligibility, data validation, permanent allocation, stock conservation, audit history and encrypted recovery remain part of the application. They do not require a separate custodian account.

## Fresh start

The deployment performs one fixed reset identified as `fresh-start-20261118-v1`. It first creates an encrypted, restore-tested recovery archive, stops clinical writes, clears training patient/study records, old allocations and MFA enrollment records, preserves named accounts/password hashes and access/invitation records, and logs the owner's instruction.

A database transaction marker prevents repeated deletion, including after a process interruption or loss of the filesystem marker. New clinical records entered after this reset survive subsequent deployments and maintenance. Existing account/security audit records are preserved. Historical encrypted recovery copies are retained privately.

The previous Drive workbook has been cleared across Randomization, Audit_Log and CTRI_Export. Its old seed and biased-coin allocation formulas were removed with the training content. It is an empty legacy template; the dashboard is the authoritative allocation system.

## Owner-managed randomization

The fresh sequence is generated automatically using operating-system randomness, with 1:1 variable permuted blocks of 4, 6 and 8 in the four protocol strata: rATG yes/no × living/deceased donor. Future assignments are encrypted and are never displayed. Each stratum has enough positions for the full study; a global ceiling limits enrollment to 344 allocations. There is no forced last-minute balancing to select a desired arm.

An enrolled participant with recorded consent and complete medical eligibility can be randomized directly by a named study account. The next stratum-specific assignment is consumed atomically and stored with the study code, allocation code, account and timestamp. Repeat or concurrent requests cannot allocate another arm to the same participant. The nominal arm remains visible throughout that participant's clinical workspace and remains unchanged when the actual renal-adjusted dose changes.

**This owner-managed custody procedure and shared access, including access by accounts originally labelled monitor, depart from protocol v5's independent-custodian and role-based blinding controls.** The implementation records the owner's configuration instruction; it does not certify an institutional or ethics-approved protocol amendment. Independent review and blinded access can be reinstated later without changing existing allocations.

## Clinical capture

Protocol v5 treatment arms, renal dose rules, endpoint definitions and the seven PCR timepoints at months 1, 2, 3, 4, 6, 9 and 12 after transplantation remain unchanged. The baseline and scheduled CRFs are complemented by dated medication exposure, laboratory, intercurrent infection and transplant-admission logs. MMF and mycophenolate sodium, prescribed and administered doses, CG CrCl and eGFR, and suspected versus confirmed infections remain distinct.

Medication previews do not create orders. Signed treatment/source references, actual drug supply and returned tablets remain separately attributable. Missing tests remain missing rather than being assumed normal or negative.

Clinical capture references: NIMS protocol v5.0 and CRF v3.0, 14 August 2026; the 2025 Fourth International CMV Consensus (https://pmc.ncbi.nlm.nih.gov/articles/PMC12180710/); OVERT kidney-transplant randomized trial (https://pmc.ncbi.nlm.nih.gov/articles/PMC10125645/). These sources inform data capture; this owner-requested access change is documented separately above.
