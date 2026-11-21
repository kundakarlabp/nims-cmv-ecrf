"""Protocol-grounded NIMS CMV CRF v3.0 forms (14 August 2026).

Form labels and structure follow sections C–L of the six-page signed CRF.
A/B are structured screening + eligibility endpoints. Seven-PCR specimens
and drug dispensing have distinct closed-loop ledgers, not duplicate values.
"""
from datetime import date
from typing import Any

def field(label, kind="text", required=False, choices=None, minimum=None, maximum=None):
    result={"label":label,"type":kind,"required":required}
    if choices is not None: result["choices"]=choices
    if minimum is not None: result["min"]=minimum
    if maximum is not None: result["max"]=maximum
    return result

YN=["yes","no"]
YNUNK=["yes","no","unknown"]
CRF_VERSION="3.0"
PROTOCOL_VERSION="5.0"
CRF_FORMS={
 "C_baseline":{
   "title":"C. Baseline and randomization",
   "repeat":"single",
   "fields":{
    "nephrology_unit":field("Nephrology unit (optional)","select",choices=["NP1","NP2","NP3"]),
    "weight_kg":field("Weight (kg)","number",minimum=20,maximum=300),
    "serum_creatinine_mg_dl":field("Serum creatinine (mg/dL)","number",minimum=0),
    "cockcroft_gault_crcl_ml_min":field("Cockcroft-Gault CrCl (mL/min)","number",minimum=0),
    "egfr_ml_min_173m2":field("eGFR (mL/min/1.73 m²)","number",minimum=0),
    "hemoglobin_g_dl":field("Hemoglobin (g/dL)","number",minimum=0),
    "wbc_per_ul":field("WBC (/µL)","number",minimum=0),
    "anc_per_ul":field("ANC (/µL)","number",minimum=0),
    "platelets_per_ul":field("Platelets (/µL)","number",minimum=0),
    "baseline_cmv_pcr_iu_ml":field("Baseline CMV PCR (IU/mL), if obtained","number",minimum=0),
    "induction":field("Induction therapy","select",choices=["rATG","basiliximab","other","none"]),
    "tacrolimus_regimen":field("Tacrolimus regimen"),
    "tacrolimus_trough_ng_ml":field("Tacrolimus trough (ng/mL)","number",minimum=0),
    "mycophenolate_regimen":field("Mycophenolate regimen"),
    "steroid_regimen":field("Steroid regimen"),
    "randomization_on":field("Randomization date","date"),
    "allocation_code":field("Independently assigned allocation reference"),
    "assigned_nominal_arm":field("Assigned nominal prophylaxis arm","select",choices=["450 mg OD","900 mg OD"]),
    "drug_start_on":field("Study-drug start date","date"),
    "renal_adjusted_starting_regimen":field("Actual renal-adjusted starting regimen"),
    "source_reference":field("Signed baseline/randomization source reference")
   }
 },
 "D_adherence":{
   "title":"D. Drug adherence, interruption and accounting",
   "repeat":"event",
   "fields":{
    "visit_on":field("Visit/date","date",required=True),
    "crcl_ml_min":field("Cockcroft-Gault CrCl at visit (mL/min)","number",minimum=0),
    "signed_prescription_ref":field("Signed prescription reference"),
    "dispensing_slip_code":field("Existing MSS dispensing slip reference"),
    "actual_prescribed_regimen":field("Prescribed regimen (not an automatic order)"),
    "pill_count_remaining":field("Observed tablets remaining","integer",minimum=0),
    "missed_doses":field("Missed doses","integer",minimum=0),
    "adherence_percent":field("Adherence (%)","number",minimum=0,maximum=100),
    "interruption":field("Interruption?","select",choices=YN),
    "interruption_reason":field("Interruption/reason","textarea"),
    "source_reference":field("Source document reference")
   }
 },
 "E_followup":{
   "title":"E. Scheduled follow-up: M1,2,3,4,6,9,12",
   "repeat":"month",
   "fields":{
    "scheduled_month":field("Protocol follow-up month","select",True,["1","2","3","4","6","9","12"]),
    "actual_visit_on":field("Actual visit date","date",True),
    "nephrology_unit":field("Nephrology unit (optional)","select",choices=["NP1","NP2","NP3"]),
    "pcr_specimen_code":field("Linked protocol CMV PCR specimen code"),
    "pcr_sample_on":field("Protocol PCR sample date (from collection source, if obtained)","date"),
    "pcr_study_funded":field("Protocol PCR study-funded?","select",choices=YNUNK),
    "pcr_funding_source_reference":field("PCR funding/source reference (if known)"),
    "cmv_signs_symptoms":field("CMV symptoms/signs","textarea"),
    "hemoglobin_g_dl":field("Hemoglobin (g/dL)","number",minimum=0),
    "wbc_per_ul":field("WBC (/µL)","number",minimum=0),
    "anc_per_ul":field("ANC (/µL)","number",minimum=0),
    "platelets_per_ul":field("Platelets (/µL)","number",minimum=0),
    "creatinine_mg_dl":field("Creatinine (mg/dL)","number",minimum=0),
    "cg_crcl_ml_min":field("Cockcroft-Gault CrCl (mL/min)","number",minimum=0),
    "egfr_ml_min_173m2":field("eGFR (mL/min/1.73 m²)","number",minimum=0),
    "actual_valganciclovir_regimen":field("Actual VGCV dose/regimen"),
    "study_drug_supplied":field("Study drug supplied?","select",choices=YN),
    "tacrolimus_trough_ng_ml":field("Tacrolimus trough (ng/mL)","number",minimum=0),
    "mycophenolate_dose":field("Mycophenolate dose"),
    "rejection_or_augmentation":field("Rejection / augmented immunosuppression?","select",choices=YN),
    "hospitalization":field("Hospitalization?","select",choices=YN),
    "ae_sae":field("AE/SAE since last visit?","select",choices=YN),
    "contact_notes":field("Notes / source-document reference","textarea")
   }
 },
 "F_unscheduled_pcr":{
   "title":"F. Unscheduled clinically indicated CMV testing",
   "repeat":"event",
   "fields":{
    "sample_on":field("CMV PCR sample date","date",True),
    "clinical_trigger":field("Clinical indication / trigger","textarea",True),
    "lab_accession":field("Laboratory accession/reference"),
    "pcr_iu_ml":field("CMV PCR IU/mL, if quantified","number",minimum=0),
    "pcr_result_kind":field("PCR result category","select",choices=["quantified","not_detected","below_loq","invalid","pending"]),
    "cmv_symptoms":field("Compatible symptoms?","select",choices=YNUNK),
    "repeat_planned":field("Repeat planned?","select",choices=YNUNK),
    "clinical_action":field("Action / treatment","textarea"),
    "funding_source":field("Funding/source of cost","select",choices=["study","routine_clinical_care","other"]),
    "source_reference":field("Signed laboratory/source reference")
   }
 },
 "G_cmv_event":{
   "title":"G. Suspected clinically significant CMV event",
   "repeat":"event",
   "fields":{
    "event_on":field("Event date","date",True),
    "qualifying_pcr_iu_ml":field("First qualifying PCR (IU/mL)","number",minimum=0),
    "pcr_at_least_1000":field("PCR >=1,000 IU/mL?","select",choices=YNUNK),
    "asymptomatic_near_threshold_repeat":field("Near threshold repeat (when clinically safe)?","select",choices=["yes","no","not_clinically_appropriate"]),
    "repeat_pcr_on":field("Repeat PCR date","date"),
    "repeat_pcr_iu_ml":field("Repeat PCR IU/mL","number",minimum=0),
    "treatment_initiated":field("Anti-CMV treatment initiated?","select",choices=YN),
    "treatment_start_on":field("Anti-CMV treatment start","date"),
    "treatment_regimen":field("Anti-CMV treatment regimen"),
    "cmv_syndrome_suspected":field("CMV syndrome suspected?","select",choices=YN),
    "tissue_invasive_suspected":field("Tissue-invasive CMV disease suspected?","select",choices=YN),
    "affected_organ":field("Suspected organ/site"),
    "supporting_evidence":field("Pathology / endoscopy / imaging evidence","textarea"),
    "alternative_diagnosis":field("Alternative diagnosis considered","textarea"),
    "adjudication_packet_sent":field("De-identified adjudication packet sent?","select",choices=YN),
    "packet_sent_on":field("Packet sent date","date"),
    "blinded_adjudication":field("Blinded EAC result (transcribe signed committee determination only)","select",choices=["pending","qualifying_dnaemia","cmv_syndrome","tissue_invasive_disease","does_not_qualify"]),
    "eac_decision_source_reference":field("Signed independent EAC decision reference (not a digital committee signature)"),
    "recurrent_event":field("Recurrent CMV event?","select",choices=YNUNK),
    "source_reference":field("CMV event source reference")
   }
 },
 "H_adverse_event":{
   "title":"H. Adverse event / serious adverse event",
   "repeat":"event",
   "fields":{
    "ae_term":field("AE term","text",True),
    "onset_on":field("Onset date","date",True),
    "resolved_on":field("End/resolution date","date"),
    "grade":field("AE severity grade","select",choices=["1","2","3","4","5","not_graded"]),
    "serious":field("Serious?","select",choices=YN),
    "relatedness":field("Relatedness to study drug","select",choices=["not_related","unlikely","possible","probable","definite","unknown"]),
    "action_on_study_drug":field("Action on valganciclovir","textarea"),
    "treatment":field("Treatment/supportive measures","textarea"),
    "outcome":field("Outcome"),
    "iec_reported":field("IEC report filed?","select",choices=YNUNK),
    "iec_report_on":field("IEC report date","date"),
    "source_reference":field("Source document reference")
   }
 },
 "I_clinical_outcome":{
   "title":"I. Rejection, graft and clinical outcomes",
   "repeat":"event",
   "fields":{
    "outcome_on":field("Outcome assessment date","date",True),
    "biopsy_proven_rejection":field("Biopsy-proven acute rejection?","select",choices=YN),
    "rejection_treatment":field("Rejection treatment/augmented immunosuppression","textarea"),
    "delayed_graft_function":field("Delayed graft function / dialysis in first 7 days?","select",choices=YN),
    "graft_loss":field("Graft loss?","select",choices=YN),
    "major_intercurrent_infection":field("Major bacterial/fungal/other viral infection","textarea"),
    "hospitalizations":field("All-cause hospitalization(s)","textarea"),
    "death":field("Death?","select",choices=YN),
    "death_on":field("Death date","date"),
    "cause_of_death":field("Cause of death"),
    "graft_status":field("Current graft status","select",choices=["functioning","failed","unknown"]),
    "creatinine_mg_dl":field("Creatinine (mg/dL)","number",minimum=0),
    "egfr_ml_min_173m2":field("eGFR (mL/min/1.73m²)","number",minimum=0)
   }
 },
 "J_deviation":{
   "title":"J. Protocol deviation or treatment crossover",
   "repeat":"event",
   "fields":{
    "occurred_on":field("Deviation/crossover date","date",True),
    "category":field("Category"),
    "description":field("Description / reason","textarea",True),
    "corrective_action":field("Corrective action","textarea"),
    "major_efficacy_affecting":field("Potential major efficacy-affecting deviation? PI/statistician to finalize","select",choices=YNUNK),
    "reported_to":field("Reported to IEC/DSMB?","textarea"),
    "source_reference":field("Source document")
   }
 },
 "K_resource_cost":{
   "title":"K. Study resource use and cost attribution",
   "repeat":"event",
   "fields":{
    "resource_on":field("Resource use date","date",True),
    "resource_type":field("Resource","select",True,[
     "scheduled_cmv_pcr","analytical_repeat","clinically_indicated_pcr",
     "cmv_resistance_testing","valganciclovir_prophylaxis","cmv_treatment",
     "gcsf_or_transfusion","cmv_hospitalization","other"]),
    "quantity":field("Quantity/duration","number",minimum=0),
    "study_funded":field("Study-funded?","select",choices=["yes","no","mixed"]),
    "direct_cost_inr":field("Direct cost (INR), if available","number",minimum=0),
    "attribution":field("Funding attribution / remarks","textarea"),
    "source_reference":field("Source document")
   }
 },
 "L_final_status":{
   "title":"L. Final 12-month status",
   "repeat":"single",
   "fields":{
    "month_12_completed":field("Completed 12-month follow-up?","select",True,YN),
    "not_completed_reason":field("Reason if incomplete","select",choices=["withdrawal","loss_to_followup","death","other"]),
    "last_contact_on":field("Date of last contact","date",True),
    "primary_endpoint":field("Primary endpoint status","select",True,["yes","no","unknown"]),
    "primary_endpoint_component":field("Primary endpoint component","select",choices=["qualifying_dnaemia","cmv_syndrome","tissue_invasive_disease","none","pending"]),
    "vital_status":field("Vital status","select",choices=["alive","dead","unknown"]),
    "graft_status":field("Graft status","select",choices=["functioning","failed","unknown"]),
    "final_creatinine_mg_dl":field("Final creatinine (mg/dL)","number",minimum=0),
    "final_egfr_ml_min_173m2":field("Final eGFR","number",minimum=0),
    "final_reviewer":field("Final reviewer name / signed source reference (not electronic sign-off)"),
    "final_review_on":field("Final review date","date")
   }
 }
}

# Optional provenance-anchored clinical narrative and NIMS nephrology unit.
# These are supplementary fields, not additional required trial investigations.
# Existing submitted payloads remain valid because their omission is permitted.
for _form in ("C_baseline","E_followup","G_cmv_event","H_adverse_event","I_clinical_outcome"):
    CRF_FORMS[_form]["fields"]["additional_notes"]=field(
        "Additional clinical notes / clarification (optional)","textarea")
# Repeatable source-detail records support CRF C/D/E/H/I without changing the
# approved intervention, visit schedule, endpoint or mandatory investigation set.
# A missing test stays missing; each dose change is a new dated source record.
CRF_FORMS.update({
 "M_medication":{
  "title":"M. Dated medication exposure / immunosuppression",
  "repeat":"event", "supplementary":True,
  "fields":{
   "start_on":field("Dose effective / administration date","date",True),
   "end_on":field("End date, if known (leave blank if continuing)","date"),
   "record_type":field("Record represents","select",True,["prescribed","administered","patient_reported","withheld"]),
   "drug":field("Medication / distinct formulation","select",True,["valganciclovir","ganciclovir","tacrolimus_immediate_release","tacrolimus_prolonged_release","cyclosporine","mycophenolate_mofetil","mycophenolate_sodium","prednisolone","methylprednisolone","ratg","basiliximab","rituximab","everolimus","sirolimus","ivig","tmp_smx","gcsf","other"]),
   "other_drug":field("Other drug / brand / formulation"),
   "indication":field("Indication","select",True,["study_prophylaxis","cmv_treatment","secondary_prophylaxis","induction","maintenance","rejection_treatment","other_prophylaxis","toxicity_support","other"]),
   "dose_per_administration":field("Dose per administration (not daily total)","number",minimum=0),
   "dose_unit":field("Dose unit","select",choices=["mg","mg_per_kg","microgram","g","unit","tablet"]),
   "frequency":field("Frequency","select",choices=["once_only","once_daily","twice_daily","three_times_daily","every_48_hours","twice_weekly","other"]),
   "timing_details":field("AM / PM doses, exact days / times or other frequency","textarea"),
   "route":field("Route","select",choices=["oral","intravenous","subcutaneous","other"]),
   "reason_for_change":field("Start / change / hold reason","textarea"),
   "renal_lab_reference":field("Dated renal assessment / laboratory reference"),
   "prescriber":field("Prescriber / signed order identity"),
   "source_reference":field("Signed source / order reference","text",True)
  }
 },
 "N_laboratory":{
  "title":"N. Dated renal, blood and drug-level results",
  "repeat":"event", "supplementary":True,
  "fields":{
   "sample_on":field("Sample / assessment date","date",True),
   "reported_on":field("Reported date","date"),
   "context":field("Assessment context","select",True,["pretransplant","transplant_admission","prerandomization","vgcv_initiation","inpatient","scheduled_followup","unscheduled","infection","rejection","vgcv_discontinuation"]),
   "scheduled_month":field("Linked scheduled month, if applicable","select",choices=["1","2","3","4","6","9","12"]),
   "weight_kg":field("Weight used in renal assessment (kg)","number",minimum=20,maximum=300),
   "creatinine_mg_dl":field("Creatinine (mg/dL)","number",minimum=0.01),
   "cg_crcl_ml_min":field("Cockcroft–Gault CrCl (mL/min), source verified","number",minimum=0),
   "egfr_ml_min_173m2":field("eGFR (mL/min/1.73 m²), graft outcome","number",minimum=0),
   "dialysis":field("Dialysis at assessment?","select",choices=YNUNK),
   "hemoglobin_g_dl":field("Hemoglobin (g/dL)","number",minimum=0,maximum=30),
   "wbc_per_ul":field("WBC (/µL)","number",minimum=0),
   "anc_per_ul":field("ANC (/µL)","number",minimum=0),
   "alc_per_ul":field("Absolute lymphocytes (/µL)","number",minimum=0),
   "platelets_per_ul":field("Platelets (/µL), convert lakh units before entry","number",minimum=0),
   "urea_mg_dl":field("Urea (mg/dL)","number",minimum=0),
   "sodium_mmol_l":field("Sodium (mmol/L)","number",minimum=0),
   "potassium_mmol_l":field("Potassium (mmol/L)","number",minimum=0),
   "alt_u_l":field("ALT (U/L)","number",minimum=0),
   "ast_u_l":field("AST (U/L)","number",minimum=0),
   "bilirubin_mg_dl":field("Total bilirubin (mg/dL)","number",minimum=0),
   "albumin_g_dl":field("Albumin (g/dL)","number",minimum=0),
   "tacrolimus_trough_ng_ml":field("Tacrolimus trough (ng/mL)","number",minimum=0),
   "last_drug_dose_at":field("Last calcineurin inhibitor dose date/time, source text"),
   "sample_time":field("Sample time / confirmed trough timing"),
   "other_results":field("Other clinically obtained test, result and units","textarea"),
   "source_reference":field("Laboratory accession / source reference","text",True)
  }
 },
 "O_infection":{
  "title":"O. Intercurrent infection episode",
  "repeat":"event", "supplementary":True,
  "fields":{
   "onset_on":field("Clinical onset date","date",True),
   "resolved_on":field("Resolution / end date","date"),
   "infection_category":field("Category","select",True,["bacterial","fungal","viral","mycobacterial","parasitic","unknown","mixed"]),
   "syndrome":field("Syndrome / site","select",True,["urinary_tract","bloodstream","pneumonia","surgical_site","gastrointestinal","cns","skin_soft_tissue","disseminated","other"]),
   "certainty":field("Diagnostic certainty","select",True,["suspected","clinically_diagnosed","microbiologically_confirmed","ruled_out"]),
   "organism":field("Organism(s), if identified"),
   "specimen":field("Specimen / site"),
   "sample_on":field("Diagnostic sample date","date"),
   "lab_accession":field("Culture / PCR / pathology reference"),
   "resistance_details":field("Resistance / susceptibility findings","textarea"),
   "diagnostic_evidence":field("Clinical, microbiology, imaging or pathology evidence","textarea"),
   "antimicrobial_treatment":field("Antimicrobial name, dated dose / route / duration","textarea"),
   "source_control":field("Source control procedure and date","textarea"),
   "hospitalized":field("Hospitalized for episode?","select",choices=YNUNK),
   "admitted_on":field("Admission date","date"),
   "discharged_on":field("Discharge date","date"),
   "icu":field("ICU care?","select",choices=YNUNK),
   "immunosuppression_change":field("Immunosuppression change and linked medication record","textarea"),
   "vgcv_interruption":field("VGCV interruption and linked exposure record","textarea"),
   "outcome":field("Episode outcome","select",choices=["ongoing","resolved","relapsed","death","unknown"]),
   "related_ae_reference":field("Related AE/SAE / CMV event reference, if applicable"),
   "source_reference":field("Clinical source reference","text",True)
  }
 },
 "P_transplant":{
  "title":"P. Transplant admission and background details",
  "repeat":"single", "supplementary":True,
  "fields":{
   "admitted_on":field("Transplant admission date","date"),
   "nephrology_unit":field("Nephrology unit (optional)","select",choices=["NP1","NP2","NP3"]),
   "discharged_on":field("Discharge date","date"),
   "primary_kidney_disease":field("Primary kidney disease"),
   "previous_transplants":field("Previous kidney transplants","integer",minimum=0),
   "pretransplant_dialysis":field("Pretransplant dialysis modality / duration"),
   "diabetes":field("Diabetes?","select",choices=YNUNK),
   "comorbidities":field("Relevant comorbidities","textarea"),
   "abo_compatibility":field("ABO compatibility","select",choices=["compatible","incompatible","unknown"]),
   "sensitization":field("PRA / cPRA / DSA, assay/date and units","textarea"),
   "desensitization":field("Desensitization procedures / dates, linked medication records","textarea"),
   "induction_summary":field("Induction agent(s), administration dates / cumulative mg/kg","textarea"),
   "delayed_graft_function":field("Dialysis in first 7 days?","select",choices=YNUNK),
   "dialysis_dates":field("Post-transplant dialysis dates / indications","textarea"),
   "source_reference":field("Transplant source reference","text",True)
  }
 }
})

# Apply the same optional labels to supplementary admission and dated events.
for _form in ("P_transplant","M_medication","N_laboratory","O_infection"):
    CRF_FORMS[_form]["fields"]["additional_notes"]=field(
        "Additional clinical notes / clarification (optional)","textarea")
def validate_payload(section:str,payload:dict[str,Any],partial:bool=False)->dict[str,Any]:
    """Validate types without inventing an absent laboratory finding or event."""
    spec=CRF_FORMS.get(section)
    if not spec:raise ValueError("Unknown CRF section")
    unknown=set(payload)-set(spec["fields"])
    if unknown:raise ValueError("Unknown field(s): "+", ".join(sorted(unknown)))
    checked={}
    for key,info in spec["fields"].items():
        v=payload.get(key)
        if v is None or v=="":
            if info["required"] and not partial:raise ValueError("Required field missing: "+info["label"])
            continue
        kind=info["type"]
        if kind in ("text","textarea"):
            if not isinstance(v,str) or len(v)>4000:raise ValueError("Invalid text: "+info["label"])
        elif kind=="select":
            if not isinstance(v,str) or v not in info["choices"]:
                raise ValueError("Invalid selection: "+info["label"])
        elif kind=="date":
            if not isinstance(v,str):raise ValueError("Date must use YYYY-MM-DD: "+info["label"])
            try:parsed=date.fromisoformat(v)
            except ValueError as err:raise ValueError("Invalid calendar date: "+info["label"]) from err
            if parsed>date.today():raise ValueError("Future clinical date prohibited: "+info["label"])
        elif kind in ("number","integer"):
            if isinstance(v,bool) or not isinstance(v,(int,float)):
                raise ValueError("Expected numeric result: "+info["label"])
            if kind=="integer" and (not isinstance(v,int) or isinstance(v,bool)):
                raise ValueError("Expected whole number: "+info["label"])
            from math import isfinite
            if not isfinite(v):raise ValueError("Nonfinite result: "+info["label"])
            if "min" in info and v<info["min"]:raise ValueError("Value below allowed range: "+info["label"])
            if "max" in info and v>info["max"]:raise ValueError("Value above allowed range: "+info["label"])
        checked[key]=v
    if not partial and not checked:raise ValueError("Empty form cannot be submitted")
    if section=="G_cmv_event" and "qualifying_pcr_iu_ml" in checked and "pcr_at_least_1000" in checked:
        observed=checked["qualifying_pcr_iu_ml"]>=1000
        if checked["pcr_at_least_1000"] in ("yes","no") and observed!=(checked["pcr_at_least_1000"]=="yes"):
            raise ValueError("CMV threshold classification conflicts with recorded IU/mL")
    if section=="H_adverse_event" and checked.get("serious")=="yes" and "iec_reported" not in checked:
        raise ValueError("Record whether an SAE IEC report has been filed")
    if section=="L_final_status" and checked.get("month_12_completed")=="no" and "not_completed_reason" not in checked:
        raise ValueError("Document reason for incomplete 12-month follow-up")
    if section=="E_followup" and "scheduled_month" in checked and checked["scheduled_month"] not in ("1","2","3","4","6","9","12"):
        raise ValueError("Invalid protocol visit month")
    for start,end in (("start_on","end_on"),("onset_on","resolved_on"),
                      ("sample_on","reported_on"),("admitted_on","discharged_on")):
        if checked.get(start) and checked.get(end) and checked[end]<checked[start]:
            raise ValueError("End date cannot precede start/sample/admission date")
    if section=="N_laboratory":
        if "anc_per_ul" in checked and "wbc_per_ul" in checked and checked["anc_per_ul"]>checked["wbc_per_ul"]:
            raise ValueError("ANC cannot exceed WBC in the same sample; verify units/source")
    if section=="M_medication" and not partial:
        if checked.get("record_type")!="withheld":
            if not checked.get("dose_per_administration") or not checked.get("dose_unit") or not checked.get("frequency") or not checked.get("route"):
                raise ValueError("Record a positive dose, unit, frequency and route")
        if checked.get("drug")=="other" and not checked.get("other_drug"):
            raise ValueError("Name the other medication")
        if checked.get("frequency")=="other" and not checked.get("timing_details"):
            raise ValueError("Specify the dosing frequency / timing")
    return checked

