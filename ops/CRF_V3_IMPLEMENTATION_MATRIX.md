# NIMS CMV trial — CRF v3.0 source-to-implementation audit

Audit date: **21 November 2026**. Signed source documents:
- `12_NIMS_CMV_Case_Record_Form_v3_14Aug2026.docx` (six pages), 14 August 2026.
- `15_NIMS_CMV_Final_Revised_Full_Study_Protocol_v5_14Aug2026.docx` (16 pages), 14 August 2026.

Protocol v5.0 remains D+/R+, with an initiation-within-10-days criterion. Proposed R+ donor-independent recruitment and late recruitment are **not** approved through dashboard staff/PI recommendations. The documented exception-review workflow does not authorize enrollment or concealed allocation. Do not backdate any source date.

This matrix describes the application repository, not proof of institutional clinical UAT, EAC adjudication, source accuracy, or production database lock. Runtime readiness is dynamic and must be checked against the currently deployed OCI commit, backups, restore proof, and permissions.

## Signed CRF vs implemented fields

| Signed section | Application capture | Remaining qualification or limitation |
|---|---|---|
| **A. Screening and enrollment** | Restricted registry CR link, screening number, serostatus recorded as positive/negative/unknown, donor type/relationship, dated consent/version, reviewed enrollment and server-assigned study ID | Identity remains restricted. Consent and donor status must be verified from source. Investigator/PI endorsements do not substitute for amendment approval. |
| **B. Eligibility** | Explicit 10 inclusion and 10 exclusion answers, numeric ANC/platelets/Hb/CrCl, signed-review date/source, optional NP1/NP2/NP3 and comments, separately audited exception request | Eligibility **must be recorded factually**. Signed protocol v5.0 gates still apply to enrollment/randomization. First prophylaxis-dose date is documented in exception review; it must not be mistaken for enrollment date. |
| **C. Baseline and randomization** | Weight, creatinine, CrCl, eGFR, CBC, optional baseline PCR, immunosuppression, study-drug start and actual starting regimen | Randomization date/code and nominal arm are obtained from locked allocation, not manually editable. Initial data require signed source verification. |
| **D. Valganciclovir accountability** | D_adherence records with dated CrCl, prescribed regimen, missed doses, adherence, interruptions/pill count; signed prescriptions, batch/lot, MSS dispensing and returns in separate ledgers | Reconcile all source rows to signed orders and pharmacy ledger; form submission alone is not evidence of drug administration or complete tablet accountability. |
| **E. Follow-up and seven scheduled PCRs** | E_followup per month 1/2/3/4/6/9/12, CBC, renal labs, drug exposure, symptoms, immunosuppression, clinical outcomes, linked PCR specimen; source-entered PCR sample date and funded status | PCR sample/result/verification comes from the linked laboratory ledger. Pending specimen is not a verified result. Funded status is **never assumed** from the schedule. Target dates are not approved visit windows. |
| **F. Unscheduled CMV PCR** | Clinical indication, sample date, laboratory accession, result category/IU/mL, repeat plan, action and funding source | Not a scheduled protocol sample; no inferred test result or reimbursement. |
| **G. Suspected clinically significant CMV** | Event date, viral load, 1,000-IU/mL consistency, repeat PCR, syndrome/site, evidence, treatment, and signed EAC decision reference | **Independent blinded adjudication workflow and committee digital sign-off remain to be implemented/validated.** A staff-transcribed result is not proof of EAC consensus. |
| **H. Adverse events/SAEs** | Grade, seriousness, relatedness, intervention, supportive treatment, outcome, IEC reporting/date | Report submission is not automated; local safety reporting and DSMB oversight still require source checking. |
| **I. Graft and clinical outcomes** | Biopsy-proven rejection, augmented immunosuppression, delayed graft function, graft loss, infections, hospitalisation, death, final graft/renal metrics | Biopsy/pathology, death, graft loss and follow-up completeness require independent source review. |
| **J. Protocol deviations/crossover** | Date, description/category, corrective action, provisional major efficacy-impact flag, reporting reference | **Per-protocol classification must be finalized by PI/statistician**, not inferred from a checkbox. |
| **K. Resource and cost** | Resource type, quantity, project-funded attribution, rupee direct cost when known and source reference | Actual study-vs-clinical funding and costs require pharmacy/lab/finance reconciliation. |
| **L. Twelve-month final status** | Last contact, endpoint/vital/graft statuses, final renal metrics and reviewer name/signed source | **Formal final reviewer e-signature, independent endpoint linkage and database lock not implemented.** A text field does not sign/lock the record. |

The supplementary M–P medication, laboratory, infection and transplant forms capture additional, dated clinical information; they are **not additional mandatory investigations under the signed CRF**. Optional free text and NP1/NP2/NP3 unit capture are supported without assuming absent values.

## Patient context, provenance and safety acceptance

1. One canonical selected patient is used for every tab; search accepts hospital CR, patient name or Study ID. Never infer identity from the first search result.
2. Changing patients must invalidate in-flight registry history, form drafts, eligibility checks, linked PCR specimens and MSS slips. All clinical read responses must confirm the requested patient/section before rendering.
3. Clinical entry, drafts, corrections and independent source review remain separate states. Optimistic revision checks must prevent silent concurrent overwrites.
4. Existing CRF source links are validated **server-side** against the same subject and, for E, the scheduled month; a documented sample date cannot contradict the source collection ledger.
5. A verified CRF entry does not automatically prove a verified PCR, a signed EAC result, drug dispensing, or final trial adjudication.
6. Tests use disposable synthetic fixtures; each live functional acceptance check must be conducted by authorized staff and preserve clinical audit records and concealed allocation.

## High-priority remaining work

- **P1:** Dedicated blinded independent endpoint-adjudication (two reviewers, discrepancy resolution, signed source, no arm disclosure).
- **P1:** Signed final CRF status, outcome lock, investigator reconciliation, and controlled unlock with immutable audit.
- **P1:** Live acceptance script for registration → screening → signed eligibility → study ID → concealed allocation → drug/PCR → longitudinal forms and patient switching; run with institution-authorized test protocol only, never invent real trial data.
- **P2:** Clear distinction of due/not-yet-due vs missing visits using approved windows; completeness queries, missing-field queries and automatic provenance links without duplicate clinical values.
- **P2:** Independent pharmacy/lab/finance reconciliation, structured protocol deviation categorization and source query resolution.

Current deployment and backup proof must be checked separately for each release. No permission or exception text in this document grants an eligibility override.
