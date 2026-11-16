# NIMS CMV clinical CRF v3.0 implementation mapping

Source of truth: uploaded **12_NIMS_CMV_Case_Record_Form_v3_14Aug2026.docx** (six pages) and **15_NIMS_CMV_Final_Revised_Full_Study_Protocol_v5_14Aug2026.docx** (16 pages). Both dated **14 August 2026**, NIEC EC/NIMS/3845/26, study IIRPIG(NAG)-I-2026-01-0634. Application integration is a developer/UAT implementation, not evidence of IEC-approved system validation.

## CRF section mapping

| Signed CRF | Implementation | Important limits |
|---|---|---|
| A Screening/enrollment | Trial screening register, restricted consent metadata, PI-controlled study code | Direct identifiers are registry-restricted; no actual participants before governance signoff |
| B Eligibility | Signed 10 inclusion and 10 exclusion answers, measured age/ANC/platelets/Hb/CrCl checks and source reference | Clinical source verification still requires PI/co-investigator review |
| C Baseline/randomization | Typed C_baseline form with baseline labs, immunosuppression, reference to randomized arm | **No independent allocation sequence loaded; do not treat a text reference as randomization** |
| D Supply/dose/adherence | Atomic pharmacy lot/issue/return ledgers, unique MSS slips; D_adherence CRF form | Requires paper prescription signatures and reconciliation of clinical exposure |
| E Seven scheduled visits | E_followup structured record for months 1/2/3/4/6/9/12; PCR specimen link to lab ledger | PCR target month anchored to verified transplant date, not enrollment date; event windows pending approval |
| F Unscheduled PCR | F_unscheduled_pcr with clinical trigger, viral load, reason, action, cost source | Not interchangeable with the seven protocol-funded scheduled tests |
| G Clinically significant CMV event | G_cmv_event threshold consistency and blinded EAC result capture | No automatic endpoint declaration from PCR; EAC evidence and independent adjudication required |
| H AE/SAE | H_adverse_event grade/seriousness/relatedness, action, treatment/outcome, IEC reporting | Does not automatically send mandatory IEC/DSMB reports |
| I Rejection/graft/outcomes | I_clinical_outcome event form | External biopsy/source review required |
| J Protocol deviations | J_deviation event form with major-efficacy-affecting flag | PI/statistician must approve PP categorization |
| K Resource/cost capture | K_resource_cost with attribution and direct INR cost | Funded drug/PCR entries checked against real study records |
| L Final study status | L_final_status with follow-up, endpoint/vital/graft status and reviewer | Final reviewer signoff/database lock not yet implemented |

Data entry uses role-filtered forms, per-user/patient/section optimistic-concurrency autosave, explicit submission, audit and independent review. A submitted record is not verified. Once the entry is verified, a correction creates a new revision and again requires independent review. Individual clinical domains are stored separately from screening identifiers and concealed allocation.

**Extended registry:** reference/data_dictionary_draft.csv describes hundreds of additional draft registry fields. They are **not** established as an approved clinical CRF by this mapping. There is no claim that the entire expanded dictionary has completed field-level operational validation.

## Staff access policy

- Initial invite token is single-use, valid **seven days** for account activation. It is **not** a recurring password reset.
- Named staff credential authorization lasts **90 days after activation**. PI/admin can renew another 90 days in the dashboard or revoke immediately; revocation/renewal invalidates active sessions.
- Staff select their own passwords and may change them from Account Security. Authenticator enrollment is available; the clinical-mode gate requires MFA.
- Users cannot view passwords or retrieve activation tokens after their initial creation. IT admin does not enroll subjects or dispense drugs.

## Preserved safety gates

- The current Oracle/GitHub release workflow is for **synthetic staging** only. No identifiable participant records should be entered yet.
- Independent stratified randomization, existing apparent allocation reconciliation, verified sealed list/custodian signoff, and blinded endpoint EAC workflows must be reconciled before any first patient is randomized.
- Database versioned migrations/immutable audit, NIEC/ICMR/CTRI release documentation, PI + lab + pharmacy signed UAT, source document checks, and a confirmed encrypted offsite backup **plus isolated full restore** are not yet demonstrated.
- An empty private personal Drive folder for **synthetic encrypted staging backups only** does not make OCI backups run. No live patient backup may be sent there without institutional data-governance authorization.
