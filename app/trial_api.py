"""Closed-loop CMV trial workflows, with synthetic-only defaults and audit events.

IMPORTANT: approved protocol, randomization allocation service, role scope,
validated eCRF, migration, backup/restore and institutional signoff remain
independent production gates. These endpoints do not prescribe or randomize.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Literal
import os
import re
import secrets
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator, field_validator
from sqlalchemy import select, func, update, delete, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .main import (
    Patient, User, LoginSession, AuthContext, current, db, audit, as_dict, now, sha, PH, ROLES
)
from .trial_models import (
    TrialSubject, PCRRecord, DrugLot, DrugAuthorization, DrugDispense,
    DrugReturn, UserInvitation, LoginThrottle, UserTotp, StaffAccess, TrialEligibility, TrialScreeningMeta,
    RandomizationSlot, TrialCRFEntry, TrialCRFReview
)

router=APIRouter(prefix="/api/trial",tags=["trial-workflows"])
MONTHS=(1,2,3,4,6,9,12)
STUDY_ID_LIMIT=350
STUDY_ID_PATTERN=re.compile(r"NCMV([0-9]{3})")


def allocate_study_id(s:Session)->str:
    """Assign one permanent, sequential ID per *enrollment* (not screening).

    All approved enrollments on PostgreSQL share a transaction-scoped
    advisory lock. Reading the committed identifiers after obtaining it
    prevents simultaneous participants from receiving the same number.
    Existing IDs, including withdrawn subjects, are never recycled.
    """
    if s.get_bind().dialect.name=="postgresql":
        s.execute(text("SELECT pg_advisory_xact_lock(165978, 350)"))
    assigned=s.scalars(select(TrialSubject.study_code).where(
        TrialSubject.study_code.is_not(None))).all()
    ids=[int(m.group(1)) for code in assigned
         if (m:=STUDY_ID_PATTERN.fullmatch(code or ""))]
    next_number=max(ids,default=0)+1
    if next_number>STUDY_ID_LIMIT:
        raise HTTPException(409,"All 350 protocol Study IDs have been assigned")
    return f"NCMV{next_number:03d}"

SCREENERS={"pi","consultant","scientist"}
ENROLLERS={"pi"}
PCR_COLLECTORS={"pi","consultant","scientist","nurse","technician","microbiology"}
PCR_RESULT_ROLES={"microbiology","technician"}
PCR_REVIEWERS={"pi","consultant","scientist","monitor"}
PRESCRIBERS={"pi","consultant"}
PHARMACISTS={"pharmacy"}
MANAGERS={"pi","admin"}

def role(u, allowed):
    if getattr(u,'workspace_full_access',False):return
    if u.role not in allowed and not ('pi' in allowed and u.pi_authorized):
        raise HTTPException(403,"The account lacks permission for this task")

def eligible_patient(s, patient_id):
    p=s.get(Patient,patient_id)
    if not p: raise HTTPException(404,"Registry record not found")
    # Defence in depth: no real registration via the new study module in staging.
    if os.getenv("CLINICAL_DATA_ENABLED","false").lower()!="true":
        if not (p.cr_number.upper().startswith("TEST-") and p.name.lower().startswith("synthetic")):
            raise HTTPException(403,"Synthetic-only staging. Patient information is prohibited.")
    return p

def find_subject(s, subject_id):
    subject=s.get(TrialSubject,subject_id)
    if not subject: raise HTTPException(404,"Study subject not found")
    eligible_patient(s,subject.patient_id)
    return subject

def active_subject(s, subject_id):
    subject=find_subject(s,subject_id)
    if subject.status!="enrolled":
        raise HTTPException(409,"Only active enrolled subjects can have new study procedures")
    return subject

def code_for(subject, section, suffix):
    return f"{subject.study_code}-{section}-{suffix}"

def month_date(start, m):
    year=start.year+(start.month-1+m)//12
    month=(start.month-1+m)%12+1
    return date(year,month,min(start.day,monthrange(year,month)[1]))

def subject_view(subject):
    return {
      "id":subject.id,"screening_code":subject.screening_code,"study_code":subject.study_code,
      "status":subject.status,"screening_on":subject.screening_on,
      "enrolled_on":subject.enrolled_on,"pcr_anchor_on":subject.pcr_anchor_on,
      "pcr_anchor_basis":subject.pcr_anchor_basis,"protocol_reference":subject.protocol_reference,
      "donor_type":subject.donor_type,"ratg_induction":subject.ratg_induction,
      "d_plus_r_plus":subject.donor_cmv_igg=="positive" and subject.recipient_cmv_igg=="positive",
      "consent_recorded":bool(subject.consent_on and subject.consent_version),
      "eligibility_attested":subject.eligibility_attested,
      "randomization_status":"SEE_RESTRICTED_ALLOCATION_MODULE",
    }

def pcr_view(row):
    return {
      "id":row.id,"specimen_code":row.specimen_code,"scheduled_month":row.scheduled_month,
      "attempt":row.attempt,"target_on":row.target_on,"status":row.status,
      "collected_on":row.collected_on,"reported_on":row.reported_on,
      "lab_accession":row.lab_accession,"assay_platform":row.assay_platform,
      "result_kind":row.result_kind,"quantitative_iu_ml":row.quantitative_iu_ml,
      "lower_limit_iu_ml":row.lower_limit_iu_ml,"qc_status":row.qc_status,
      "revision":row.revision,"verified_at":row.verified_at,
    }

class ScreeningIn(BaseModel):
    patient_id:str
    screening_on:date
    donor_cmv_igg:Literal["positive","negative","unknown"]
    recipient_cmv_igg:Literal["positive","negative","unknown"]
    donor_type:Literal["living","deceased"]
    ratg_induction:bool|None=None
    consent_on:date|None=None
    consent_version:str|None=Field(default=None,max_length=60)
    eligibility_attested:bool=False
    screening_note:str|None=Field(default=None,max_length=1000)
    participant_initials:str|None=Field(default=None,max_length=20)
    age_at_transplant:int|None=Field(default=None,ge=0,le=120)
    sex_at_birth:Literal["female","male","other","not_recorded"]|None=None
    donor_relationship:Literal["living_related","living_unrelated","deceased"]|None=None
    pis_version:str|None=Field(default=None,max_length=80)
    consent_language:Literal["English","Telugu","Hindi"]|None=None
    consent_obtained_by:str|None=Field(default=None,max_length=150)
    signed_consent_source_ref:str|None=Field(default=None,max_length=120)

@router.post("/screening")
def screen(data:ScreeningIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,SCREENERS)
    p=eligible_patient(s,data.patient_id)
    if data.screening_on>date.today():
        raise HTTPException(422,"Screening date cannot be in the future")
    if data.consent_on and data.consent_on>date.today():
        raise HTTPException(422,"Consent date cannot be in the future")
    if bool(data.consent_on)!=bool(data.consent_version):
        raise HTTPException(422,"Document signed consent date and version together")
    if data.donor_relationship:
        if (data.donor_relationship=="deceased")!=(data.donor_type=="deceased"):
            raise HTTPException(422,"Donor relationship conflicts with living/deceased stratum")
    # Store screening and declined consent even before the signed ICF exists.
    # Actual consent remains mandatory for eligibility and enrollment.
    if os.getenv("CLINICAL_DATA_ENABLED","false").lower()=="true" and data.consent_on:
        must=(data.participant_initials,data.age_at_transplant,data.sex_at_birth,
              data.donor_relationship,data.pis_version,data.consent_language,
              data.consent_obtained_by)
        if any(x is None or x=="" for x in must):
            raise HTTPException(422,"Complete consent details when signed consent is recorded")
    t=TrialSubject(patient_id=p.id,screening_on=data.screening_on,
        donor_cmv_igg=data.donor_cmv_igg,recipient_cmv_igg=data.recipient_cmv_igg,
        donor_type=data.donor_type,ratg_induction=data.ratg_induction,
        consent_on=data.consent_on,consent_version=data.consent_version,
        eligibility_attested=data.eligibility_attested,
        screening_note=data.screening_note,created_by=u.user_id)
    try:
        s.add(t);s.flush()
        t.screening_code=f"NCMV-S-{t.id:05d}"
        s.add(TrialScreeningMeta(
            subject_id=t.id,participant_initials=data.participant_initials,
            age_at_transplant=data.age_at_transplant,sex_at_birth=data.sex_at_birth,
            donor_relationship=data.donor_relationship,pis_version=data.pis_version,
            icf_version=data.consent_version,consent_language=data.consent_language,
            consent_obtained_by=data.consent_obtained_by,
            signed_consent_source_ref=data.signed_consent_source_ref))
        audit(s,u,"screen","trial_subject",str(t.id),p.id,None,
             subject_view(t),"Recorded screening; not enrollment or randomization")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Subject already screened")
    return subject_view(t)


@router.get("/subjects/{subject_id}/restricted-screening")
def restricted_screening(subject_id:int,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,{"pi","consultant","scientist"})
    t=find_subject(s,subject_id)
    meta=s.get(TrialScreeningMeta,t.id)
    return {"screening_code":t.screening_code,
        "restricted":as_dict(meta) if meta else None,
        "scope":"Restricted source-link metadata; never show in monitoring or lab pharmacy views"}

@router.get("/subjects")
def subjects(q:str="",limit:int=50,before_id:int|None=None,u:AuthContext=Depends(current),s:Session=Depends(db)):
    limit=max(1,min(limit,200))
    # Join registry identity once so staff can find the same CR throughout the
    # workflow. Preserve strict-role masking outside the owner-managed workspace.
    restricted=u.role in {"microbiology","pharmacy","technician","monitor"} and not u.workspace_full_access
    statement=select(TrialSubject,Patient).join(Patient,Patient.id==TrialSubject.patient_id).order_by(TrialSubject.id.desc())
    if before_id is not None:statement=statement.where(TrialSubject.id<before_id)
    if q.strip():
        term="%"+q.strip()+"%"
        match=TrialSubject.study_code.ilike(term) | TrialSubject.screening_code.ilike(term)
        if not restricted:match=match | Patient.cr_number.ilike(term) | Patient.name.ilike(term)
        statement=statement.where(match)
    records=s.execute(statement.limit(limit)).all()
    return [dict(subject_view(t),patient_id=p.id,
                 cr_number=None if restricted else p.cr_number,
                 name=None if restricted else p.name) for t,p in records
            if (os.getenv("CLINICAL_DATA_ENABLED","false").lower()=="true" or eligible_patient(s,t.patient_id))]

@router.get("/subjects/{subject_id}")
def subject(subject_id:int,u:AuthContext=Depends(current),s:Session=Depends(db)):
    t=find_subject(s,subject_id)
    return subject_view(t)


# Exact inclusion/exclusion concepts transcribed from signed CRF v3.0
# (14 Aug 2026), checked against protocol v5.0.
INCLUSION_ITEMS={
 "age_ge_18":"Age >=18 years",
 "solitary_kidney":"Solitary kidney transplant at NIMS",
 "donor_cmv_positive":"Donor CMV IgG positive",
 "recipient_cmv_positive":"Recipient CMV IgG positive",
 "vgcv_within_10_days":"Valganciclovir can start <=10 days after transplant",
 "written_consent":"Written NIEC-approved informed consent",
 "anc_ge_1500":"ANC >=1500 per microlitre",
 "platelets_ge_50000":"Platelets >=50000 per microlitre",
 "hemoglobin_ge_7":"Hemoglobin >=7 g/dL",
 "clinically_stable":"Clinically stable for prophylaxis and 12-month follow-up"
}
EXCLUSION_ITEMS={
 "pre_randomization_cmv_treatment":"Pre-randomization CMV requiring treatment",
 "multi_organ_transplant":"Multi-organ transplant",
 "ongoing_dialysis":"Ongoing dialysis at randomization",
 "crcl_below_10":"Cockcroft-Gault CrCl <10 mL/min",
 "vgcv_hypersensitivity":"Valganciclovir/ganciclovir hypersensitivity",
 "blood_counts_below_threshold":"Blood counts below inclusion thresholds",
 "pregnancy_or_breastfeeding":"Pregnancy or breastfeeding",
 "severe_infection_or_instability":"Severe infection, instability or unsafe randomization",
 "conflicting_interventional_trial":"Conflicting interventional trial",
 "unable_to_complete_followup":"Unable/unwilling to complete follow-up"
}
class EligibilityReviewIn(BaseModel):
    inclusion:dict[str,bool]
    exclusion:dict[str,bool]
    age_years:int=Field(ge=0,le=120)
    anc_per_ul:float=Field(ge=0)
    platelets_per_ul:float=Field(ge=0)
    hemoglobin_g_dl:float=Field(ge=0,le=25)
    crcl_cg_ml_min:float=Field(ge=0)
    baseline_cbc_on:date
    reviewed_on:date
    signed_source_reference:str|None=Field(default=None,max_length=100)

@router.get("/eligibility-schema")
def eligibility_schema(u:AuthContext=Depends(current)):
    return {"version":"CRF 3.0 / Protocol 5.0, 14 August 2026",
        "inclusion":INCLUSION_ITEMS,"exclusion":EXCLUSION_ITEMS}

@router.get("/subjects/{subject_id}/eligibility")
def eligibility_detail(subject_id:int,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,{"pi","consultant","scientist","monitor"})
    t=find_subject(s,subject_id)
    row=s.get(TrialEligibility,t.id)
    return {"eligibility":as_dict(row) if row else None}

@router.put("/subjects/{subject_id}/eligibility")
def eligibility_review(subject_id:int,data:EligibilityReviewIn,
    u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,{"pi","consultant"})
    t=find_subject(s,subject_id)
    if t.status!="screened":
        raise HTTPException(409,"Eligibility cannot be rewritten after enrollment")
    if set(data.inclusion)!=set(INCLUSION_ITEMS) or set(data.exclusion)!=set(EXCLUSION_ITEMS):
        raise HTTPException(422,"Complete every protocol inclusion and exclusion item")
    if any(type(v) is not bool for v in list(data.inclusion.values())+list(data.exclusion.values())):
        raise HTTPException(422,"Eligibility answers must be explicit yes/no")
    if data.reviewed_on<t.screening_on or data.reviewed_on>date.today():
        raise HTTPException(422,"Invalid eligibility review date")
    if data.baseline_cbc_on>data.reviewed_on:
        raise HTTPException(422,"CBC source date after eligibility review")
    p=eligible_patient(s,t.patient_id)
    if not p.transplant_date:raise HTTPException(422,"Transplant date must be verified in registry")
    incl=data.inclusion;excl=data.exclusion
    if incl["age_ge_18"]!=(data.age_years>=18):
        raise HTTPException(422,"Age answer conflicts with age at randomization")
    if incl["anc_ge_1500"]!=(data.anc_per_ul>=1500) or \
       incl["platelets_ge_50000"]!=(data.platelets_per_ul>=50000) or \
       incl["hemoglobin_ge_7"]!=(data.hemoglobin_g_dl>=7):
        raise HTTPException(422,"Blood-count eligibility answers conflict with measured source results")
    if excl["blood_counts_below_threshold"]!=(
        data.anc_per_ul<1500 or data.platelets_per_ul<50000 or data.hemoglobin_g_dl<7):
        raise HTTPException(422,"Blood-count exclusion conflicts with source results")
    if excl["crcl_below_10"]!=(data.crcl_cg_ml_min<10):
        raise HTTPException(422,"CrCl exclusion conflicts with Cockcroft-Gault result")
    if incl["donor_cmv_positive"]!=(t.donor_cmv_igg=="positive") or \
       incl["recipient_cmv_positive"]!=(t.recipient_cmv_igg=="positive"):
        raise HTTPException(422,"Serostatus checklist conflicts with laboratory serostatus")
    if incl["written_consent"]!=bool(t.consent_on and t.consent_version):
        raise HTTPException(422,"Consent checklist does not match recorded signed consent")
    eligible=all(incl.values()) and not any(excl.values())
    baseline={"age_years":data.age_years,"anc_per_ul":data.anc_per_ul,
       "platelets_per_ul":data.platelets_per_ul,"hemoglobin_g_dl":data.hemoglobin_g_dl,
       "crcl_cg_ml_min":data.crcl_cg_ml_min,"baseline_cbc_on":data.baseline_cbc_on.isoformat(),
       "is_eligible":eligible}
    if data.signed_source_reference:
        baseline["signed_source_reference"]=data.signed_source_reference
    prior=s.get(TrialEligibility,t.id)
    if prior:
        old=as_dict(prior)
        prior.inclusion=incl;prior.exclusion=excl;prior.baseline=baseline
        prior.reviewed_by=u.user_id;prior.reviewed_on=data.reviewed_on;prior.updated_at=now()
    else:
        old=None
        prior=TrialEligibility(subject_id=t.id,inclusion=incl,exclusion=excl,
            baseline=baseline,reviewed_by=u.user_id,reviewed_on=data.reviewed_on)
        s.add(prior)
    audit(s,u,"eligibility_review","trial_eligibility",str(t.id),t.patient_id,
        old,{"inclusion":incl,"exclusion":excl,"baseline":baseline,
             "reviewed_by":u.user_id,"reviewed_on":data.reviewed_on},
        "Protocol eligibility checklist confirmed by named account"+
        (": "+data.signed_source_reference if data.signed_source_reference else ""))
    s.commit()
    return {"subject_id":t.id,"eligible":eligible,
        "reviewed_by":u.user_id,"reviewed_on":data.reviewed_on,
        "note":"A complete checklist is mandatory; no auto-randomization."}

@router.get("/action-worklist")
def action_worklist(limit:int=Query(default=80,ge=1,le=200),
                    u:AuthContext=Depends(current),s:Session=Depends(db)):
    """Source-derived operational actions. Target dates are NOT approved visit windows.

    Never expose future assignments, treatment-arm balance or identifiers in
    these cards. Selecting an action does not automatically change trial data.
    """
    from zoneinfo import ZoneInfo
    from datetime import datetime
    from .trial_crf import FORM_EDITOR, BLINDED_FORM_SECTIONS
    today=datetime.now(ZoneInfo("Asia/Kolkata")).date()
    records=s.execute(select(TrialSubject,Patient).join(
        Patient,Patient.id==TrialSubject.patient_id)).all()
    subjects={t.id:(t,p) for t,p in records}
    eligibility={r.subject_id:r for r in s.scalars(select(TrialEligibility)).all()}
    assigned=set(s.scalars(select(RandomizationSlot.subject_id).where(
        RandomizationSlot.subject_id.is_not(None))).all())
    actions=[]
    def add(subject,patient,category,detail,route,priority=2,target_on=None):
        actions.append({
            "subject_id":subject.id,"patient_id":patient.id,
            "study_code":subject.study_code or subject.screening_code,
            "category":category,"detail":detail,"route":route,
            "priority":priority,
            "target_on":target_on.isoformat() if target_on else None,
        })
    for subject,patient in records:
        check=eligibility.get(subject.id)
        if subject.status=="screened":
            if check is None:
                add(subject,patient,"Eligibility pending","Complete and source-verify all inclusion and exclusion criteria","study",1)
            elif check.baseline.get("is_eligible") is True:
                add(subject,patient,"Enrollment pending","Eligibility documented; investigator must verify enrollment and consent","study",1)
        elif subject.status=="enrolled" and subject.id not in assigned:
            add(subject,patient,"Randomization pending","Verify stratum and signed source before irreversible assignment","randomization",1)
    for specimen in s.scalars(select(PCRRecord).where(
        PCRRecord.attempt==1,PCRRecord.status!="verified",
        PCRRecord.target_on<=today+timedelta(days=7))).all():
        pair=subjects.get(specimen.subject_id)
        if not pair or pair[0].status!="enrolled":continue
        subject,patient=pair
        if specimen.status=="result_entered":
            category,detail="PCR verification","Reported result awaiting source review"
        elif specimen.status=="collected":
            category,detail="PCR result pending","Collected specimen awaiting laboratory result"
        elif specimen.status=="planned":
            category,detail="PCR target","Scheduled month "+str(specimen.scheduled_month)+" target; confirm approved collection window"
        else:
            continue
        if specimen.target_on<today:
            detail+="; target date passed (not a protocol-window breach determination)"
        add(subject,patient,category,detail,"pcr",1 if specimen.target_on<today else 2,specimen.target_on)
    crf_rows=s.scalars(select(TrialCRFEntry)).all()
    review_keys={(r.entry_id,r.entry_revision):r.decision for r in
        s.scalars(select(TrialCRFReview)).all()}
    for entry in crf_rows:
        pair=subjects.get(entry.subject_id)
        if not pair:continue
        subject,patient=pair
        if (not u.workspace_full_access and u.role not in FORM_EDITOR.get(entry.section,set())
            and not (u.role=="monitor" and entry.section in BLINDED_FORM_SECTIONS)
            and not (u.pi_authorized and "pi" in FORM_EDITOR.get(entry.section,set()))):
            continue
        state=review_keys.get((entry.id,entry.revision),"pending")
        if state in ("pending","needs_correction"):
            add(subject,patient,"eCRF "+("review" if state=="pending" else "correction"),
                entry.section+" · "+("awaiting source review" if state=="pending" else "requires corrected revision"),
                "crf",2)
        if entry.section=="H_adverse_event" and entry.payload.get("serious")=="yes" and entry.payload.get("iec_reported")!="yes":
            add(subject,patient,"SAE reporting check",
                "Submitted serious adverse event: confirm required reporting and source evidence",
                "crf",0)
    rank={"SAE reporting check":0,"Eligibility pending":1,"Enrollment pending":1,
          "Randomization pending":1,"PCR verification":2,"PCR result pending":2,
          "PCR target":3,"eCRF correction":4,"eCRF review":5}
    actions.sort(key=lambda a:(a["priority"],rank.get(a["category"],6),
                               a["target_on"] or "9999-12-31",
                               a["study_code"] or ""))
    counts={}
    for item in actions:counts[item["category"]]=counts.get(item["category"],0)+1
    return {"as_of":today.isoformat(),"total":len(actions),"counts":counts,
            "actions":actions[:limit],
            "note":"Worklist derived from persisted records. PCR targets are not approved visit windows. Actions do not create approvals, allocations, orders or adjudicated endpoints."}


class EnrollmentIn(BaseModel):
    enrolled_on:date
    pcr_anchor_on:date
    pcr_anchor_basis:Literal["transplant_date"]
    protocol_reference:str=Field(min_length=3,max_length=80)
    reviewed_eligibility_and_consent:bool
    approved_visit_anchor:bool

@router.post("/subjects/{subject_id}/enroll")
def enroll(subject_id:int,data:EnrollmentIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,ENROLLERS)
    # Serialize approval of the same screened participant. PostgreSQL holds
    # this lock until the Study ID and seven PCR orders commit together.
    t=s.scalar(select(TrialSubject).where(TrialSubject.id==subject_id).with_for_update())
    if not t: raise HTTPException(404,"Study subject not found")
    eligible_patient(s,t.patient_id)
    if t.status!="screened": raise HTTPException(409,"Enrollment already decided")
    signed_check=s.get(TrialEligibility,t.id)
    if not signed_check or not signed_check.baseline.get("is_eligible") or \
       signed_check.reviewed_on>data.enrolled_on or \
       not all(signed_check.inclusion.values()) or any(signed_check.exclusion.values()):
        raise HTTPException(422,"Complete an eligible, signed protocol checklist before enrollment")
    if not (t.eligibility_attested and t.consent_on and t.consent_version and
            t.donor_cmv_igg=="positive" and t.recipient_cmv_igg=="positive" and
            t.ratg_induction is not None and data.reviewed_eligibility_and_consent and
            data.approved_visit_anchor):
        raise HTTPException(422,"Cannot enroll until eligibility, D+/R+, consent and scheduling are reviewed")
    if data.enrolled_on<t.consent_on:
        raise HTTPException(422,"Enrollment cannot precede informed consent")
    p=eligible_patient(s,t.patient_id)
    if not p.transplant_date or data.pcr_anchor_on!=p.transplant_date:
        raise HTTPException(422,"Per protocol v5.0, all seven CMV PCR targets are anchored to verified transplantation date")
    if data.enrolled_on<p.transplant_date or (data.enrolled_on-p.transplant_date).days>10:
        raise HTTPException(422,"Enrollment must support valganciclovir start within 10 days of transplantation")
    if data.enrolled_on>date.today() or data.pcr_anchor_on>date.today():
        raise HTTPException(422,"Study milestone dates cannot be in the future")
    if p.study_id:
        raise HTTPException(409,"Registry already has a Study ID; reconcile before enrollment")
    new_code=allocate_study_id(s)
    t.study_code=new_code;t.enrolled_on=data.enrolled_on;t.status="enrolled"
    t.pcr_anchor_on=data.pcr_anchor_on;t.pcr_anchor_basis=data.pcr_anchor_basis
    t.protocol_reference=data.protocol_reference;t.confirmed_by=u.user_id
    p.study_id=new_code
    for month in MONTHS:
        s.add(PCRRecord(subject_id=t.id,scheduled_month=month,attempt=1,
            specimen_code=code_for(t,"PCR",f"M{month:02d}-A01"),
            target_on=month_date(data.pcr_anchor_on,month),status="planned"))
    audit(s,u,"enroll","trial_subject",str(t.id),p.id,None,
          subject_view(t),"Enrollment approved; permanent Study ID and seven PCR codes generated; randomization remains separate")
    try:
        s.commit()
    except IntegrityError:
        s.rollback()
        raise HTTPException(409,"Study ID or scheduled PCR already exists; refresh this participant")
    return {"subject":subject_view(t),"study_id":new_code,"pcr_orders":len(MONTHS)}

class ConsentDeclinedIn(BaseModel):
    confirmed:Literal[True]

@router.post("/subjects/{subject_id}/consent-declined")
def mark_consent_declined(subject_id:int,data:ConsentDeclinedIn,
                         u:AuthContext=Depends(current),s:Session=Depends(db)):
    """Retain attributed screening history without enrollment or allocation."""
    role(u,SCREENERS)
    t=s.scalar(select(TrialSubject).where(TrialSubject.id==subject_id).with_for_update())
    if not t:raise HTTPException(404,"Screening record not found")
    eligible_patient(s,t.patient_id)
    if t.status!="screened" or t.enrolled_on or t.study_code:
        raise HTTPException(409,"Only never-enrolled screening records may be closed for declined consent")
    if t.consent_on or t.consent_version:
        raise HTTPException(409,"Consent recorded; reconcile source first, do not overwrite signed consent")
    if s.scalar(select(RandomizationSlot.id).where(RandomizationSlot.subject_id==subject_id).limit(1)):
        raise HTTPException(409,"Randomized participants cannot be marked consent declined")
    old=subject_view(t)
    t.status="consent_declined"
    t.discontinuation_reason="Written informed consent declined"
    audit(s,u,"consent_declined","trial_subject",str(t.id),t.patient_id,old,subject_view(t),
          "Screened; written consent declined; enrollment and randomization prohibited")
    s.commit()
    return subject_view(t)


class DiscontinueIn(BaseModel):
    status:Literal["withdrawn","deceased","discontinued"]
    reason:str=Field(min_length=5,max_length=500)

@router.post("/subjects/{subject_id}/discontinue")
def discontinue(subject_id:int,data:DiscontinueIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,{"pi","consultant"})
    t=active_subject(s,subject_id)
    old=subject_view(t)
    t.status=data.status;t.discontinuation_reason=data.reason
    audit(s,u,"discontinue","trial_subject",str(t.id),t.patient_id,
          old,subject_view(t),data.reason)
    s.commit()
    return subject_view(t)

@router.get("/subjects/{subject_id}/pcr")
def pcr_list(subject_id:int,u:AuthContext=Depends(current),s:Session=Depends(db)):
    t=find_subject(s,subject_id)
    records=s.scalars(select(PCRRecord).where(PCRRecord.subject_id==t.id)
            .order_by(PCRRecord.scheduled_month,PCRRecord.attempt)).all()
    return {"study_code":t.study_code,"schedule_basis":t.pcr_anchor_basis,
        "pcr_records":[pcr_view(r) for r in records]}

@router.get("/pcr-worklist")
def pcr_worklist(u:AuthContext=Depends(current),s:Session=Depends(db)):
    rows=s.execute(select(PCRRecord,TrialSubject).join(TrialSubject,PCRRecord.subject_id==TrialSubject.id)
        .where(TrialSubject.status=="enrolled",PCRRecord.attempt==1)
        .order_by(PCRRecord.target_on).limit(4000)).all()
    today=date.today()
    return [{
        "study_code":subject.study_code,"specimen_code":pcr.specimen_code,
        "month":pcr.scheduled_month,"target_on":pcr.target_on,
        "status":pcr.status,"days_until":(pcr.target_on-today).days,
        "completion_verified":pcr.status=="verified"
    } for pcr,subject in rows]

class CollectionIn(BaseModel):
    collected_on:date
    lab_accession:str=Field(min_length=2,max_length=100)

@router.post("/pcr/{record_id}/collect")
def collect(record_id:int,data:CollectionIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PCR_COLLECTORS)
    record=s.get(PCRRecord,record_id)
    if not record:raise HTTPException(404)
    active_subject(s,record.subject_id)
    if record.status!="planned":raise HTTPException(409,"Specimen already collected/processed")
    if data.collected_on>date.today():raise HTTPException(422,"Collection cannot occur in the future")
    old=pcr_view(record)
    record.collected_on=data.collected_on;record.lab_accession=data.lab_accession
    record.status="collected";record.updated_at=now();record.revision+=1
    audit(s,u,"collect","trial_pcr",str(record.id),find_subject(s,record.subject_id).patient_id,
          old,pcr_view(record),"Sample collected")
    try:s.commit()
    except IntegrityError:s.rollback();raise HTTPException(409,"Duplicate laboratory accession")
    return pcr_view(record)

class PCRResultIn(BaseModel):
    expected_revision:int=Field(ge=1)
    reported_on:date
    assay_platform:str=Field(min_length=2,max_length=120)
    result_kind:Literal["not_detected","quantified","detected_below_loq","invalid"]
    quantitative_iu_ml:float|None=Field(default=None,ge=0)
    lower_limit_iu_ml:float|None=Field(default=None,gt=0)
    qc_status:Literal["pass","fail"]
    correction_reason:str|None=Field(default=None,max_length=500)
    @model_validator(mode="after")
    def verify_pair(self):
        if self.result_kind=="quantified" and (self.quantitative_iu_ml is None or self.quantitative_iu_ml<=0):
            raise ValueError("Quantified PCR requires positive IU/mL")
        if self.result_kind!="quantified" and self.quantitative_iu_ml is not None:
            raise ValueError("A nonquantified result must not contain a fabricated IU/mL value")
        if self.result_kind=="invalid" and self.qc_status!="fail":
            raise ValueError("Invalid assay must have QC fail")
        if self.result_kind!="invalid" and self.qc_status!="pass":
            raise ValueError("Reportable assay must have QC pass")
        return self

@router.put("/pcr/{record_id}/result")
def report_pcr(record_id:int,data:PCRResultIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PCR_RESULT_ROLES)
    r=s.get(PCRRecord,record_id)
    if not r:raise HTTPException(404)
    active_subject(s,r.subject_id)
    if r.status not in {"collected","result_entered","verified"}:
        raise HTTPException(409,"Collect a specimen before reporting")
    if data.expected_revision!=r.revision:
        raise HTTPException(409,"PCR revision conflict; reload")
    if data.reported_on<r.collected_on or data.reported_on>date.today():
        raise HTTPException(422,"Reporting date must follow sample collection")
    if r.status in {"result_entered","verified"} and not data.correction_reason:
        raise HTTPException(422,"Corrections require an attributed reason")
    old=pcr_view(r)
    # Conditional write protects concurrent edits on PostgreSQL/SQLite.
    changed=s.execute(update(PCRRecord).where(PCRRecord.id==r.id,
        PCRRecord.revision==data.expected_revision).values(
        reported_on=data.reported_on,assay_platform=data.assay_platform,
        result_kind=data.result_kind,quantitative_iu_ml=data.quantitative_iu_ml,
        lower_limit_iu_ml=data.lower_limit_iu_ml,qc_status=data.qc_status,
        result_entered_by=u.user_id,verified_by=None,verified_at=None,
        status="result_entered",revision=PCRRecord.revision+1,updated_at=now()))
    if changed.rowcount!=1:s.rollback();raise HTTPException(409,"Concurrent PCR edit")
    s.flush();s.refresh(r)
    audit(s,u,"pcr_result","trial_pcr",str(r.id),find_subject(s,r.subject_id).patient_id,
          old,pcr_view(r),data.correction_reason or "Initial lab result")
    s.commit()
    return pcr_view(r)

class RevisionIn(BaseModel):
    expected_revision:int=Field(ge=1)
    review_reason:str=Field(min_length=5,max_length=300)

@router.post("/pcr/{record_id}/verify")
def verify_pcr(record_id:int,data:RevisionIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PCR_REVIEWERS)
    r=s.get(PCRRecord,record_id)
    if not r:raise HTTPException(404)
    find_subject(s,r.subject_id)
    if r.status!="result_entered":raise HTTPException(409,"Only submitted results may be verified")
    if r.result_entered_by==u.user_id and not u.workspace_full_access:raise HTTPException(403,"Independent reviewer required")
    if r.revision!=data.expected_revision:raise HTTPException(409,"PCR changed; reload")
    old=pcr_view(r)
    updated=s.execute(update(PCRRecord).where(PCRRecord.id==r.id,
        PCRRecord.revision==data.expected_revision,PCRRecord.status=="result_entered")
        .values(status="verified",verified_by=u.user_id,verified_at=now(),
                revision=PCRRecord.revision+1,updated_at=now()))
    if updated.rowcount!=1:s.rollback();raise HTTPException(409,"Concurrent PCR verification")
    s.flush();s.refresh(r)
    audit(s,u,"pcr_verify","trial_pcr",str(r.id),find_subject(s,r.subject_id).patient_id,
          old,pcr_view(r),data.review_reason)
    s.commit()
    return pcr_view(r)

class RepeatPCRIn(BaseModel):
    reason:str=Field(min_length=8,max_length=500)

@router.post("/pcr/{record_id}/repeat")
def repeat_pcr(record_id:int,data:RepeatPCRIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,{"pi","consultant","scientist","microbiology"})
    original=s.get(PCRRecord,record_id)
    if not original:raise HTTPException(404)
    t=active_subject(s,original.subject_id)
    attempts=s.scalar(select(func.max(PCRRecord.attempt)).where(
        PCRRecord.subject_id==t.id,PCRRecord.scheduled_month==original.scheduled_month)) or 1
    if attempts>=9:raise HTTPException(409,"Maximum repeat specimens reached; investigator review")
    r=PCRRecord(subject_id=t.id,scheduled_month=original.scheduled_month,
        attempt=attempts+1,target_on=original.target_on,status="planned",
        repeat_reason=data.reason,
        specimen_code=code_for(t,"PCR",f"M{original.scheduled_month:02d}-A{attempts+1:02d}"))
    s.add(r)
    try:
        s.flush()
        audit(s,u,"pcr_repeat","trial_pcr",str(r.id),t.patient_id,None,
              pcr_view(r),data.reason)
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Repeat created concurrently; reload")
    return pcr_view(r)

class LotIn(BaseModel):
    lot_number:str=Field(min_length=2,max_length=100)
    expiry_on:date
    received_on:date
    strength_mg:Literal[450]
    quantity_received:int=Field(gt=0,le=1000000)

@router.post("/pharmacy/lots")
def receive_lot(data:LotIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PHARMACISTS)
    if data.expiry_on<data.received_on:raise HTTPException(422,"Batch expired on receipt")
    lot=DrugLot(lot_number=data.lot_number,expiry_on=data.expiry_on,
        received_on=data.received_on,strength_mg=data.strength_mg,
        quantity_received=data.quantity_received,quantity_on_hand=data.quantity_received,
        received_by=u.user_id)
    s.add(lot)
    try:
        s.flush()
        audit(s,u,"stock_receive","drug_lot",str(lot.id),None,None,
              as_dict(lot),"Original receipt; preserve source invoice")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Duplicate lot+expiry")
    return {"lot_id":lot.id,"remaining":lot.quantity_on_hand}

@router.get("/pharmacy/lots")
def lots(u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PHARMACISTS|{"pi","admin","monitor","scientist"})
    return [as_dict(x) for x in s.scalars(select(DrugLot).order_by(DrugLot.expiry_on)).all()]

class AuthorizationIn(BaseModel):
    prescription_ref:str=Field(min_length=3,max_length=100)
    signed_on:date
    allocation_reference:str=Field(min_length=3,max_length=100)
    renal_assessment_ref:str=Field(min_length=3,max_length=100)
    authorized_dose_instruction:str=Field(min_length=5,max_length=500)

@router.post("/subjects/{subject_id}/drug-authorization")
def authorise_drug(subject_id:int,data:AuthorizationIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PRESCRIBERS)
    t=active_subject(s,subject_id)
    from .randomization import allocation_for, arm_for
    assigned=allocation_for(s,t.id)
    if assigned is None:
        raise HTTPException(409,"No concealed randomized allocation released; prescription not authorized")
    if data.allocation_reference!=assigned.allocation_code:
        raise HTTPException(422,"Signed prescription allocation code does not match locked randomization")
    arm_for(s,t.id)  # Decrypt and verify sealed allocation before authorizing drug.
    if data.signed_on>date.today() or (
        assigned.assigned_at and data.signed_on<assigned.assigned_at.date()):
        raise HTTPException(422,"Signed prescription must follow actual randomized allocation")
    d=DrugAuthorization(subject_id=t.id,prescription_ref=data.prescription_ref,
        signed_on=data.signed_on,allocation_reference=data.allocation_reference,
        renal_assessment_ref=data.renal_assessment_ref,
        authorized_dose_instruction=data.authorized_dose_instruction,
        authorization_by=u.user_id)
    s.add(d)
    try:
        s.flush()
        audit(s,u,"drug_authorize","trial_prescription",str(d.id),t.patient_id,
              None,as_dict(d),"Externally signed and clinically reviewed prescription reference")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Duplicate prescription reference")
    return {"id":d.id,"study_code":t.study_code,"prescription_ref":d.prescription_ref,
            "note":"Not an electronic prescription; verify signed paper and concealed allocation externally"}

class DispenseIn(BaseModel):
    authorization_id:int
    lot_id:int
    quantity_issued:int=Field(gt=0,le=10000)
    issued_on:date

@router.post("/subjects/{subject_id}/dispense")
def dispense(subject_id:int,data:DispenseIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PHARMACISTS)
    t=active_subject(s,subject_id)
    a=s.get(DrugAuthorization,data.authorization_id)
    if not a or a.subject_id!=t.id:raise HTTPException(422,"Approved prescription not linked to subject")
    from .randomization import allocation_for, arm_for
    assigned=allocation_for(s,t.id)
    if not assigned or a.allocation_reference!=assigned.allocation_code:
        raise HTTPException(409,"Dispensing blocked until sealed allocation and signed order reconcile")
    arm_for(s,t.id)  # Raise if independent encryption key or ciphertext is invalid.
    lot=s.get(DrugLot,data.lot_id)
    if not lot:raise HTTPException(404,"Study drug lot not found")
    if data.issued_on<a.signed_on or data.issued_on>date.today() or data.issued_on>lot.expiry_on:
        raise HTTPException(422,"Issue date conflicts with prescription or lot expiry")
    # Atomic stock decrement: two dispensers cannot both use the same remaining tablets.
    stock=s.execute(update(DrugLot).where(DrugLot.id==lot.id,
        DrugLot.quantity_on_hand>=data.quantity_issued)
        .values(quantity_on_hand=DrugLot.quantity_on_hand-data.quantity_issued))
    if stock.rowcount!=1:
        s.rollback();raise HTTPException(409,"Insufficient available stock")
    d=DrugDispense(subject_id=t.id,authorization_id=a.id,lot_id=lot.id,
        slip_code="UNASSIGNED-"+secrets.token_hex(12),quantity_issued=data.quantity_issued,
        issued_on=data.issued_on,issued_by=u.user_id)
    s.add(d);s.flush()
    d.slip_code=code_for(t,"MSS",f"{d.id:05d}")
    audit(s,u,"drug_dispense","trial_dispense",str(d.id),t.patient_id,None,
          as_dict(d),"Issue entered against approved signed paper prescription")
    s.commit()
    return {"slip_code":d.slip_code,"study_code":t.study_code,"quantity_issued":d.quantity_issued,
        "lot_number":lot.lot_number,"expiry_on":lot.expiry_on,"signed_by":u.name,
        "remaining_in_lot":lot.quantity_on_hand,
        "print_instruction":"Obtain physical recipient, issuing pharmacist and investigator signatures"}

class ReturnIn(BaseModel):
    quantity_returned:int=Field(gt=0)
    returned_on:date
    disposition:Literal["quarantine","destruction_pending","destroyed"]

@router.post("/pharmacy/dispenses/{dispense_id}/return")
def return_drug(dispense_id:int,data:ReturnIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PHARMACISTS)
    d=s.get(DrugDispense,dispense_id)
    if not d:raise HTTPException(404)
    t=find_subject(s,d.subject_id)
    if data.returned_on<d.issued_on or data.returned_on>date.today():
        raise HTTPException(422,"Invalid return date")
    previous=s.scalar(select(func.coalesce(func.sum(DrugReturn.quantity_returned),0))
         .where(DrugReturn.dispense_id==d.id)) or 0
    if previous+data.quantity_returned>d.quantity_issued:
        raise HTTPException(409,"Return exceeds quantity dispensed")
    r=DrugReturn(dispense_id=d.id,quantity_returned=data.quantity_returned,
        returned_on=data.returned_on,disposition=data.disposition,recorded_by=u.user_id)
    s.add(r);s.flush()
    # Returned stock is never automatically available for reissue.
    audit(s,u,"drug_return","trial_drug_return",str(r.id),t.patient_id,
          None,as_dict(r),"Return/quarantine tracked; not restocked")
    s.commit()
    return {"dispense_id":d.id,"returned_total":previous+r.quantity_returned,
            "unreconciled_quantity":d.quantity_issued-previous-r.quantity_returned}

@router.get("/subjects/{subject_id}/pharmacy")
def subject_pharmacy(subject_id:int,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,PHARMACISTS|{"pi","consultant","scientist","nurse","monitor"})
    t=find_subject(s,subject_id)
    authorizations=s.scalars(select(DrugAuthorization).where(
        DrugAuthorization.subject_id==t.id)).all()
    dispenses=s.scalars(select(DrugDispense).where(DrugDispense.subject_id==t.id)).all()
    returns=s.scalars(select(DrugReturn).where(
        DrugReturn.dispense_id.in_([x.id for x in dispenses]))).all() if dispenses else []
    totals={x.id:0 for x in dispenses}
    for r in returns:totals[r.dispense_id]+=r.quantity_returned
    # Allocation reference/dose information is limited to prescribers and dispensing pharmacy.
    allow_details=u.role in (PRESCRIBERS|PHARMACISTS)
    return {"study_code":t.study_code,
        "orders":[as_dict(a) if allow_details else {"id":a.id,"prescription_ref":a.prescription_ref}
                  for a in authorizations],
        "dispenses":[dict(as_dict(d),total_returned=totals[d.id],
                          remaining_unreconciled=d.quantity_issued-totals[d.id]) for d in dispenses]}

class InviteIn(BaseModel):
    username:str=Field(min_length=3,max_length=100,pattern=r"^[a-z][a-z0-9_.-]{2,99}$")
    display_name:str=Field(min_length=3,max_length=150)
    role:Literal["consultant","pg","scientist","nurse","technician","microbiology",
                 "pharmacy","monitor","pi","admin","randomization_custodian"]

    @field_validator("username",mode="before")
    @classmethod
    def normalize_username(cls,v):
        # Names such as "Sai" should be accepted and stored consistently with
        # the already case-insensitive login flow.
        return v.strip().lower() if isinstance(v,str) else v

    @field_validator("display_name",mode="before")
    @classmethod
    def trim_staff_name(cls,v):
        return v.strip() if isinstance(v,str) else v

@router.post("/staff/invite")
def invite_user(data:InviteIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,MANAGERS)
    if data.role in {"pi","admin","randomization_custodian"} and u.role!="admin":
        raise HTTPException(403,"Only an administrator may delegate privileged roles")
    user=User(username=data.username,display_name=data.display_name,role=data.role,
        password_hash=PH.hash(secrets.token_urlsafe(48)),active=False)
    token=secrets.token_urlsafe(36)
    try:
        s.add(user)
        s.flush()  # Must be inside try: duplicate usernames are 409, not a server crash.
        invitation=UserInvitation(user_id=user.id,token_sha256=sha(token),
            created_by=u.user_id,expires_at=now()+timedelta(days=7))
        s.add(invitation)
        audit(s,u,"staff_invite","user_invitation",user.id,None,None,
              {"username":user.username,"role":user.role,"expires_at":invitation.expires_at},
              "Named staff activation issued; password and token excluded from audit")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Username already exists; use reissue for an inactive account")
    # Secret only returned once over TLS to authenticated inviter, never persisted as plaintext.
    return {"username":user.username,"role":user.role,"activation_token":token,
        "expires_in_days":7,
        "instruction":"Give this one-time token privately to the named staff member. They set their own password. No shared accounts."}


class BulkStaffInviteIn(BaseModel):
    staff:list[InviteIn]=Field(min_length=1,max_length=15)

@router.post("/staff/invite-batch")
def invite_named_staff(data:BulkStaffInviteIn,u:AuthContext=Depends(current),
                       s:Session=Depends(db)):
    """Provision 1–15 named inactive users atomically. No shared passwords."""
    role(u,MANAGERS)
    usernames=[person.username.strip().lower() for person in data.staff]
    if len(set(usernames))!=len(usernames):
        raise HTTPException(422,"Duplicate username in this batch")
    if u.role!="admin" and any(x.role in {"pi","admin","randomization_custodian"} for x in data.staff):
        raise HTTPException(403,"Only administrator may invite high-privilege users")
    created=[]
    for person in data.staff:
        token=secrets.token_urlsafe(36)
        user=User(username=person.username.strip().lower(),
            display_name=person.display_name.strip(),role=person.role,
            password_hash=PH.hash(secrets.token_urlsafe(48)),active=False)
        s.add(user)
        try:
            s.flush()
        except IntegrityError:
            s.rollback();raise HTTPException(409,"One or more usernames already exist; none were provisioned")
        s.add(UserInvitation(user_id=user.id,token_sha256=sha(token),
            created_by=u.user_id,expires_at=now()+timedelta(days=7)))
        created.append({"username":user.username,"display_name":user.display_name,
            "role":user.role,"activation_token":token,
            "expires_in_days":7,"access_validity_days_after_activation":90})
    try:
        s.flush()
        audit(s,u,"staff_batch_invite","user_invitation_batch",u.user_id,None,None,
            {"count":len(created),
             "usernames":[x["username"] for x in created],
             "roles":[x["role"] for x in created]},
            "PI/administrator issued individual named-user enrollment tokens")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Batch conflict; no invitation tokens issued")
    return {"created":len(created),"invitations":created,
        "private_distribution_notice":"Each invitation token is shown only in this authenticated response. Distribute separately to verified named staff. Never share passwords."}

class ActivateIn(BaseModel):
    token:str=Field(min_length=40,max_length=300)
    password:str=Field(min_length=14,max_length=200)
@router.post("/staff/activate")
def activate(data:ActivateIn,s:Session=Depends(db)):
    invite=s.scalar(select(UserInvitation).where(
        UserInvitation.token_sha256==sha(data.token)))
    if not invite or invite.redeemed_at is not None or invite.expires_at.replace(tzinfo=now().tzinfo)<now():
        raise HTTPException(400,"Activation token invalid or expired")
    user=s.get(User,invite.user_id)
    if not user or user.active:raise HTTPException(400,"Account already active")
    user.password_hash=PH.hash(data.password);user.active=True;invite.redeemed_at=now()
    access=s.get(StaffAccess,user.id)
    if access is None:
        access=StaffAccess(user_id=user.id,activated_at=now(),
            expires_at=now()+timedelta(days=90))
        s.add(access)
    else:
        # A previously revoked account may be reinstated only by a separately
        # audited reissue; its former grant is not reused.
        access.activated_at=now()
        access.expires_at=now()+timedelta(days=90)
        access.renewed_at=now()
        access.renewed_by=invite.created_by
    s.commit()
    return {"ok":True,"username":user.username,"access_expires_at":access.expires_at,
            "notice":"90-day named account activated. Authenticator enrollment required before clinical use."}

@router.get("/staff/roles")
def roles(u:AuthContext=Depends(current)):
    return {
      "pi":["enrollment","clinical review","PCR review","drug prescription","staff invites"],
      "scientist":["screening","follow-up","data entry","PCR collection","review others' records"],
      "nurse":["visit entry","PCR specimen collection","safety events"],
      "technician":["PCR specimen collection","PCR result entry"],
      "microbiology":["PCR specimen collection","PCR result entry"],
      "pharmacy":["study drug lot receipt","issue against signed prescription","returns"],
      "consultant":["screening","clinical review","PCR review","prescription"],
      "pg":["clinical visit entries"],
      "monitor":["read-only trial review","independent PCR verification"],
      "admin":["account provisioning","system administration"],
      "randomization_custodian":["import and lock independently signed concealed allocation sequence; no enrollment or patient details"],
    }

@router.get("/overview")
def overview(u:AuthContext=Depends(current),s:Session=Depends(db)):
    subject_counts=dict(s.execute(select(TrialSubject.status,func.count())
        .group_by(TrialSubject.status)).all())
    pcr_counts=dict(s.execute(select(PCRRecord.status,func.count())
        .group_by(PCRRecord.status)).all())
    scheduled=s.scalar(select(func.count(PCRRecord.id)).where(PCRRecord.attempt==1)) or 0
    verified=s.scalar(select(func.count(PCRRecord.id)).where(
        PCRRecord.attempt==1,PCRRecord.status=="verified")) or 0
    total_enrolled=s.scalar(select(func.count(TrialSubject.id)).where(
        TrialSubject.enrolled_on.is_not(None))) or 0
    lot_balance=s.scalar(select(func.coalesce(func.sum(DrugLot.quantity_on_hand),0))) or 0
    issued=s.scalar(select(func.coalesce(func.sum(DrugDispense.quantity_issued),0))) or 0
    returned=s.scalar(select(func.coalesce(func.sum(DrugReturn.quantity_returned),0))) or 0
    from .trial_models import RandomizationSlot
    randomized=s.scalar(select(func.count(RandomizationSlot.id)).where(RandomizationSlot.subject_id.is_not(None))) or 0
    return {"randomized":randomized,"screened":s.scalar(select(func.count(TrialSubject.id))),
        "enrolled":subject_counts.get("enrolled",0),
        "ever_enrolled":total_enrolled,"subject_status":subject_counts,
        "pcr":pcr_counts,"protocol_pcr_per_subject":len(MONTHS),
        "scheduled_pcr_slots":scheduled,"verified_protocol_pcr_slots":verified,
        "pcr_completion_percent":round(verified*100/scheduled,1) if scheduled else 0,
        "drug_accountability":{"tablets_in_stock":lot_balance,
                               "tablets_issued":issued,"tablets_returned":returned,
                               "tablets_not_yet_reconciled":issued-returned},
        "randomization":"sealed sequence module; future allocations are never shown",
        "data_mode":"synthetic_staging" if os.getenv("CLINICAL_DATA_ENABLED","false").lower()!="true"
            else "clinical"}


@router.post("/staff/mfa-setup")
def mfa_setup(u:AuthContext=Depends(current),s:Session=Depends(db)):
    record=s.get(UserTotp,u.user_id)
    if record and record.enabled:
        raise HTTPException(409,"MFA already active; administrator-assisted recovery required")
    secret=pyotp.random_base32()
    if not record:
        record=UserTotp(user_id=u.user_id,secret=secret,enabled=False)
        s.add(record)
    else:
        record.secret=secret
    s.commit()
    # This secret is shown to the account owner once via the authenticated session.
    # Never persist it in browser storage or attach it to routine error logs.
    return {"secret":secret,
        "otpauth_uri":pyotp.TOTP(secret).provisioning_uri(name=u.user_id,
            issuer_name="NIMS CMV Trial"),
        "instruction":"Save in your authenticator, then confirm one current 6-digit code."}

class MfaConfirmIn(BaseModel):
    otp:str=Field(min_length=6,max_length=6,pattern=r"^\d{6}$")

@router.post("/staff/mfa-confirm")
def mfa_confirm(data:MfaConfirmIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    user=s.get(User,u.user_id)
    throttle=s.get(LoginThrottle,user.username)
    if throttle and throttle.locked_until and throttle.locked_until.replace(tzinfo=now().tzinfo)>now():
        raise HTTPException(429,'Authenticator attempts temporarily locked for 15 minutes')
    record=s.get(UserTotp,u.user_id)
    if not record or record.enabled:
        raise HTTPException(409,"MFA setup missing or already enabled")
    if not pyotp.TOTP(record.secret).verify(data.otp,valid_window=1):
        if not throttle:
            throttle=LoginThrottle(username=user.username,failures=0);s.add(throttle)
        throttle.failures+=1
        if throttle.failures>=5:throttle.locked_until=now()+timedelta(minutes=15)
        s.commit()
        raise HTTPException(422,"Authenticator code incorrect")
    record.enabled=True;record.confirmed_at=now()
    if throttle:throttle.failures=0;throttle.locked_until=None
    # Revoke all password-only/setup sessions. The owner signs in again with
    # both factors; enrollment never upgrades another open session.
    s.execute(delete(LoginSession).where(LoginSession.user_id==u.user_id))
    audit(s,u,"mfa_enabled","user",u.user_id,None,None,
        {"enabled":True,"confirmed_at":record.confirmed_at},
        "Account owner confirmed authenticator enrollment")
    s.commit()
    return {"mfa_enabled":True,"notice":"Authenticator code is required at subsequent logins"}


# Named credentials remain valid for 90 days after activation. The seven-day
# onboarding token is single-use and NOT a temporary account/password.
@router.get("/staff/accounts")
def staff_accounts(u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,MANAGERS)
    rows=s.execute(select(User,StaffAccess,UserTotp)
        .outerjoin(StaffAccess,StaffAccess.user_id==User.id)
        .outerjoin(UserTotp,UserTotp.user_id==User.id)
        .order_by(User.created_at.desc())).all()
    return [{"id":usr.id,"username":usr.username,"display_name":usr.display_name,
        "role":usr.role,"active":usr.active,
        "access_expires_at":access.expires_at if access else None,
        "mfa_enabled":bool(totp and totp.enabled),
        "status":("active" if not access or access.expires_at.replace(tzinfo=now().tzinfo)>now() else "expired")
                 if usr.active else ("revoked" if access else "awaiting_activation"),
        "requires_activation":not usr.active and access is None,
        "is_revoked":not usr.active and access is not None} for usr,access,totp in rows]

class ReissueStaffIn(BaseModel):
    reason:str=Field(min_length=8,max_length=500)
    restore_revoked:bool=False

@router.post("/staff/accounts/{user_id}/reissue")
def reissue_staff_access(user_id:str,data:ReissueStaffIn,
                         u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,MANAGERS)
    user=s.get(User,user_id)
    if not user:raise HTTPException(404,"Staff account not found")
    if user.id==u.user_id:raise HTTPException(409,"Cannot reissue own account")
    if user.role in {"pi","admin","randomization_custodian"} and u.role!="admin":
        raise HTTPException(403,"Only administrator may reissue privileged users")
    if user.active:
        raise HTTPException(409,"Account is active; use renewal or revoke first")
    previous=s.get(StaffAccess,user.id)
    if previous and not data.restore_revoked:
        raise HTTPException(409,"Previously revoked account: explicit reinstatement approval required")
    if not previous and data.restore_revoked:
        raise HTTPException(422,"Account has never been activated; reissue invitation instead")
    token=secrets.token_urlsafe(36)
    # Invalidate every older invitation and session, including those already used.
    s.execute(delete(UserInvitation).where(UserInvitation.user_id==user.id))
    s.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    user.password_hash=PH.hash(secrets.token_urlsafe(48))
    invitation=UserInvitation(user_id=user.id,token_sha256=sha(token),
        created_by=u.user_id,expires_at=now()+timedelta(days=7))
    s.add(invitation)
    audit(s,u,"staff_reissue","user_invitation",user.id,None,
          {"username":user.username,"previously_activated":bool(previous)},
          {"username":user.username,"invitation_expires_at":invitation.expires_at,
           "previously_revoked":bool(previous)},data.reason)
    s.commit()
    return {"username":user.username,"role":user.role,
            "activation_token":token,"expires_in_days":7,
            "access_validity_days_after_activation":90,
            "restored_previous_account":bool(previous),
            "instruction":"Give this one-time activation code privately to the verified staff member; they choose their own password."}

class RenewAccessIn(BaseModel):
    reason:str=Field(min_length=8,max_length=500)
    days:Literal[90]=90

@router.post("/staff/accounts/{user_id}/renew")
def renew_staff(user_id:str,data:RenewAccessIn,u:AuthContext=Depends(current),
                s:Session=Depends(db)):
    role(u,MANAGERS)
    user=s.get(User,user_id)
    if not user:raise HTTPException(404,"Staff account not found")
    if user.role in {"admin","pi"} and u.role!="admin":
        raise HTTPException(403,"Only IT administrator can renew privileged users")
    if not user.active:raise HTTPException(409,"Revoked/inactive account cannot be renewed")
    current_access=s.get(StaffAccess,user_id)
    before=as_dict(current_access) if current_access else None
    if not current_access:
        current_access=StaffAccess(user_id=user.id,activated_at=now(),
            expires_at=now()+timedelta(days=90),renewed_by=u.user_id,
            renewed_at=now())
        s.add(current_access)
    else:
        current_access.expires_at=now()+timedelta(days=90)
        current_access.renewed_at=now()
        current_access.renewed_by=u.user_id
    # Revocation of all existing devices forces reauthentication under new grant.
    s.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    s.flush()
    audit(s,u,"access_renew","user",user.id,None,before,
          as_dict(current_access),data.reason)
    s.commit()
    return {"username":user.username,"expires_at":current_access.expires_at,
            "next_action":"Staff member signs in again with their existing personal password and authenticator."}

class RevokeIn(BaseModel):
    reason:str=Field(min_length=8,max_length=500)

@router.post("/staff/accounts/{user_id}/revoke")
def revoke_staff(user_id:str,data:RevokeIn,u:AuthContext=Depends(current),
                 s:Session=Depends(db)):
    role(u,MANAGERS)
    user=s.get(User,user_id)
    if not user:raise HTTPException(404)
    if user.id==u.user_id:raise HTTPException(409,"Cannot revoke own active account")
    if user.role in {"admin","pi"} and u.role!="admin":
        raise HTTPException(403,"Only IT administrator can revoke privileged users")
    before={"active":user.active,"role":user.role}
    user.active=False
    s.execute(delete(LoginSession).where(LoginSession.user_id==user.id))
    s.execute(delete(UserInvitation).where(UserInvitation.user_id==user.id))
    audit(s,u,"access_revoke","user",user.id,None,before,
          {"active":False,"role":user.role},data.reason)
    s.commit()
    return {"username":user.username,"active":False,"sessions_revoked":True}

class PasswordChangeIn(BaseModel):
    old_password:str=Field(min_length=1,max_length=200)
    new_password:str=Field(min_length=14,max_length=200)
    otp:str|None=Field(default=None,min_length=6,max_length=6,pattern=r"^[0-9]{6}$")

@router.post("/staff/change-password")
def change_password(data:PasswordChangeIn,u:AuthContext=Depends(current),
                    s:Session=Depends(db)):
    from argon2.exceptions import VerifyMismatchError, VerificationError
    usr=s.get(User,u.user_id)
    try: valid=PH.verify(usr.password_hash,data.old_password)
    except (VerifyMismatchError,VerificationError):valid=False
    if not valid:raise HTTPException(403,"Current password incorrect")
    if data.new_password==data.old_password:
        raise HTTPException(422,"New password must differ")
    totp=s.get(UserTotp,usr.id)
    from .workspace_policy import password_only
    if not password_only() and totp and totp.enabled and not (data.otp and pyotp.TOTP(totp.secret).verify(data.otp,valid_window=1)):
        raise HTTPException(403,"Authenticator confirmation required")
    usr.password_hash=PH.hash(data.new_password)
    s.execute(delete(LoginSession).where(LoginSession.user_id==usr.id))
    audit(s,u,"password_change","user",usr.id,None,None,
          {"password_changed":True},"Self-service password rotation; all existing sessions revoked")
    s.commit()
    return {"password_changed":True,"sessions_revoked":True,
            "notice":"Log in again with your new private password"}

