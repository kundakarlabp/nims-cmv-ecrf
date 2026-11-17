# NIMS CMV: allocation and longitudinal capture

Implementation specification, 17 November 2026. Protocol v5.0 and CRF v3.0,
14 August 2026, govern the trial. This document is not a signed randomization
specification, ethics amendment or authorization to alter an existing assignment.

## Existing worksheet review

The Drive workbook `NIMS_CMV_Advanced_Randomization.xlsx` has Randomization,
Audit_Log and CTRI_Export tabs, 15 filled allocation rows, rATG, preferred/final
arms and running counts. Its formula uses an 80% biased coin toward the preferred
arm, with a deterministic pseudo-random seed and volatile NOW timestamps. This
is not the protocol v5 four-stratum variable-permuted-block method. The export
contains a broken reference and the running counts have gaps/inconsistencies.
The worksheet alone cannot establish whether these were real enrollments,
training examples, or formally authorized historic assignments. No identifying
rows, seed, allocation sequence or workbook bytes belong in Git or CI.

Keep this workbook unchanged as a restricted source. Before locking a new plan,
the PI and independent custodian must reconcile those rows with signed consent,
eligibility, transplant/donor/induction sources and the actual treatment delivered.
If they are real enrollments, preserve their assignments and resolve the
protocol-version/analysis and migration plan with the study statistician; never
rerandomize them or silently count them as new v5 allocations. If they are test
examples, document that conclusion. The clinical lock API requires a reference
to this reconciliation. It does not certify that the reconciliation occurred.

## Randomization procedure

1. Register the source patient, screen consecutively, record consent and complete
   the attributed inclusion/exclusion checklist. Do not allocate an ineligible
   patient. Confirm adult solitary-kidney D+/R+, stable oral intake/follow-up,
   CBC thresholds, no dialysis/CrCl below 10, and all other protocol exclusions.
2. PI verifies enrollment, transplantation-based PCR anchor and initiation within
   10 days. Determine rATG yes/no and living/deceased donor from source records
   before allocation. Keep living related/unrelated detail in screening data.
3. Appoint a named independent sequence custodian who does not determine
   eligibility. The custodian signs and locks the final protocol-specific
   specification, including prior-allocation reconciliation, before use.
4. Use concealed computer-generated 1:1 variable permuted blocks independently
   in all four strata. A reasonable proposed size set is 4, 6 and 8, to be
   finalized by the independent statistician. Sizes/order are restricted to the
   custodian; clinical staff never see future assignments or block positions.
   Do not copy the workbook's biased-coin formulas or reuse its exposed seed.
5. Custodian imports an independently checked signed package, or personally
   generates and permanently locks the sequence in the restricted module.
   The application uses operating-system randomness, validates balanced complete
   blocks, encrypts future arms and fingerprints the locked plan. The trial has
   a global ceiling of 344; within-stratum balance does not guarantee exactly
   172 patients per arm at an arbitrary stopping point.
6. The PI opens the enrolled participant directly from Enrollment, verifies
   consent/eligibility/stratum and records the signed randomization source.
   The server atomically consumes the next concealed slot in that stratum.
   Repeated/concurrent requests cannot allocate a second arm to that participant.
   The assignment, actor, timestamp, source and plan fingerprint persist.
7. Show the original nominal allocation and code throughout the selected
   participant's workspace for PI, consultant, scientist, nurse, PG and pharmacy.
   Endpoint monitors and laboratory roles do not receive the nominal arm.
   Treatment remains open label; endpoint adjudication remains blinded.
8. Preserve allocation for ITT regardless of dose change, crossover, withdrawal,
   toxicity, infection or graft dysfunction. Record actual exposure separately.
   Corrections require attribution/reason; no manual arm editing or reseeding.
9. If electronic allocation is unavailable, use only an independently controlled
   contingency process consistent with protocol §7.2. Do not run a second
   parallel sequence or reconcile two independent assignments after the fact.

## Dosing and follow-up

Nominal 450 or 900 mg OD is an allocation, not an automatic medication order.
The signed prescription uses Cockcroft–Gault CrCl and the protocol safety ceiling:

| CrCl, mL/min | 450 nominal arm | 900 nominal arm |
|---|---|---|
| ≥60 | 450 mg OD | 900 mg OD |
| 40–59 | 450 mg OD | 450 mg OD |
| 25–39 | 450 mg every 48 hours | 450 mg every 48 hours |
| 10–24 | 450 mg twice weekly | 450 mg twice weekly |
| <10 or hemodialysis | Protocol tablets withheld; clinician manages | Same |

The assigned arm never changes when renal function causes the regimens to
converge. eGFR is a graft outcome and does not replace CG CrCl for this dosing.
Continue the approved three-month strategy and seven PCR assessments at months
1, 2, 3, 4, 6, 9, 12 after transplantation; extra testing remains clinically
indicated. No new mandatory research investigations are introduced here.

## Capture workflow

| Record | Capture |
|---|---|
| A/B and C | Screening/consent, complete eligibility, measured CBC/renal baseline, source references; baseline can be entered before arm release |
| P transplant background | Admission/discharge, kidney disease, prior transplant/dialysis, ABO/DSA/PRA when available, desensitization, induction and early dialysis |
| M medication | One dated regimen/administration per drug/change; prescribed versus administered versus patient-reported versus withheld; dose per administration, unit, frequency, route, AM/PM detail, source, indication, renal assessment and change reason |
| N laboratory | Dated inpatient, pre-randomization, VGCV-initiation and follow-up samples; creatinine, CG CrCl, eGFR, weight, dialysis, CBC/ANC/ALC/platelets, available chemistry/LFT and tacrolimus trough with timing |
| D and pharmacy | Adherence, interruptions, signed orders, linked issue/return slips, lot/expiry and pill counts; do not substitute prescribed dose for tablets actually issued or taken |
| E and PCR | Seven visit forms, source-linked specimen/results and reviewed clinical outcomes; an extra lab panel does not mark a PCR or visit complete |
| O infection | Separate episode per onset/recurrence; suspected/clinical/microbiologic certainty, syndrome, specimen/organism/resistance, evidence, dated treatment/source control, hospital/ICU/outcome, linked immunosuppression/VGCV changes and AE/CMV records |
| G/H/I/J/L | CMV event and blinded adjudication, AE/SAE, rejection/graft/outcomes, deviations and final follow-up remain in their approved forms |

MMF and enteric-coated mycophenolate sodium, and immediate/prolonged-release
tacrolimus, remain distinct formulations. Do not infer dose equivalence. Use
separate rows or explicit AM/PM source detail for unequal doses. Capture induction
and rejection pulses by date/dose and link cumulative summaries to source.
Unknown values stay absent; a missing record does not establish no event.
Clinical dates, positivity/units, independent review status and revisions remain
visible in the paginated patient course. M–P are supplementary source-detail
logs supporting existing protocol variables, not a new endpoint or study arm.

## Evidence informing capture, not changing this protocol

- NIMS full protocol v5.0 §§5, 7–12, 15–18 and CRF v3.0 A–L (14 August 2026).
- Kotton et al., Fourth International CMV Consensus, 2025:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC12180710/
  Supports consistent virology, actual antiviral exposure, non-normalized renal
  function for dosing, immunosuppression and hematologic monitoring. Its general
  care recommendations do not replace the approved trial surveillance schedule.
- Reischig et al., OVERT randomized kidney-transplant trial, JASN 2023:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10125645/
  Illustrates documenting background immunosuppression, rejection, renal/graft
  outcomes, other infections, neutropenia and antiviral exposure. Its comparison
  groups, blocks and monitoring schedule are not imported into this trial.

## Release and remaining human actions

No schema/table change is needed: supplementary forms use existing attributed,
revisioned CRF records/drafts/reviews. Existing clinical data, assignments and
backups remain intact. Verify SQLite/PostgreSQL behavior, actual browser patient
switches, blocked unauthorized roles and Docker/clinical recovery before release.
Release through reviewed GitHub code and the existing VM pull mechanism.

Clinical data entry can remain active while the independent sequence is pending.
Actual custodial nomination, signed prior-record reconciliation and signed final
specification are human study actions; software cannot attest them for the team.
