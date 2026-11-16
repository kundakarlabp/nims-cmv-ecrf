"""Closed-loop CMV trial workflows, with synthetic-only defaults and audit events.

IMPORTANT: approved protocol, randomization allocation service, role scope,
validated eCRF, migration, backup/restore and institutional signoff remain
independent production gates. These endpoints do not prescribe or randomize.
"""
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Literal
import os
import secrets
import pyotp
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, func, update, delete
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .main import (
    Patient, User, LoginSession, AuthContext, current, db, audit, as_dict, now, sha, PH, ROLES
)
from .trial_models import (
    TrialSubject, PCRRecord, DrugLot, DrugAuthorization, DrugDispense,
    DrugReturn, UserInvitation, LoginThrottle, UserTotp, StaffAccess
)

router=APIRouter(prefix="/api/trial",tags=["trial-workflows"])
MONTHS=(1,2,3,4,6,9,12)
SCREENERS={"pi","consultant","scientist"}
ENROLLERS={"pi"}
PCR_COLLECTORS={"pi","consultant","scientist","nurse","technician","microbiology"}
PCR_RESULT_ROLES={"microbiology","technician"}
PCR_REVIEWERS={"pi","consultant","scientist","monitor"}
PRESCRIBERS={"pi","consultant"}
PHARMACISTS={"pharmacy"}
MANAGERS={"pi","admin"}

def role(u, allowed):
    if u.role not in allowed:
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
      "randomization_status":"EXTERNAL_VERIFICATION_REQUIRED",
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

@router.post("/screening")
def screen(data:ScreeningIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,SCREENERS)
    p=eligible_patient(s,data.patient_id)
    if data.consent_on and data.consent_on>date.today():
        raise HTTPException(422,"Consent date cannot be in the future")
    if bool(data.consent_on)!=bool(data.consent_version):
        raise HTTPException(422,"Document signed consent date and version together")
    t=TrialSubject(patient_id=p.id,screening_on=data.screening_on,
        donor_cmv_igg=data.donor_cmv_igg,recipient_cmv_igg=data.recipient_cmv_igg,
        donor_type=data.donor_type,ratg_induction=data.ratg_induction,
        consent_on=data.consent_on,consent_version=data.consent_version,
        eligibility_attested=data.eligibility_attested,
        screening_note=data.screening_note,created_by=u.user_id)
    try:
        s.add(t);s.flush()
        t.screening_code=f"NCMV-S-{t.id:05d}"
        audit(s,u,"screen","trial_subject",str(t.id),p.id,None,
             subject_view(t),"Recorded screening; not enrollment or randomization")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Subject already screened")
    return subject_view(t)

@router.get("/subjects")
def subjects(q:str="",limit:int=50,u:AuthContext=Depends(current),s:Session=Depends(db)):
    limit=max(1,min(limit,200))
    statement=select(TrialSubject).order_by(TrialSubject.id.desc())
    if q.strip():
        term="%"+q.strip()+"%"
        statement=statement.where(TrialSubject.study_code.ilike(term) |
                                  TrialSubject.screening_code.ilike(term))
    records=s.scalars(statement.limit(limit)).all()
    return [subject_view(t) for t in records if (os.getenv("CLINICAL_DATA_ENABLED","false").lower()=="true"
            or eligible_patient(s,t.patient_id))]

@router.get("/subjects/{subject_id}")
def subject(subject_id:int,u:AuthContext=Depends(current),s:Session=Depends(db)):
    t=find_subject(s,subject_id)
    return subject_view(t)

class EnrollmentIn(BaseModel):
    enrolled_on:date
    pcr_anchor_on:date
    pcr_anchor_basis:Literal["transplant_date","enrollment_date","randomization_date","prophylaxis_start_date"]
    protocol_reference:str=Field(min_length=3,max_length=80)
    reviewed_eligibility_and_consent:bool
    approved_visit_anchor:bool

@router.post("/subjects/{subject_id}/enroll")
def enroll(subject_id:int,data:EnrollmentIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,ENROLLERS)
    t=find_subject(s,subject_id)
    if t.status!="screened": raise HTTPException(409,"Enrollment already decided")
    if not (t.eligibility_attested and t.consent_on and t.consent_version and
            t.donor_cmv_igg=="positive" and t.recipient_cmv_igg=="positive" and
            t.ratg_induction is not None and data.reviewed_eligibility_and_consent and
            data.approved_visit_anchor):
        raise HTTPException(422,"Cannot enroll until eligibility, D+/R+, consent and scheduling are reviewed")
    if data.enrolled_on<t.consent_on:
        raise HTTPException(422,"Enrollment cannot precede informed consent")
    p=eligible_patient(s,t.patient_id)
    if p.transplant_date and data.pcr_anchor_basis=="transplant_date" and data.pcr_anchor_on!=p.transplant_date:
        raise HTTPException(422,"Transplant-date anchor conflicts with registry record")
    if data.pcr_anchor_basis=="enrollment_date" and data.pcr_anchor_on!=data.enrolled_on:
        raise HTTPException(422,"Enrollment-date anchor must match enrollment date")
    if data.enrolled_on>date.today() or data.pcr_anchor_on>date.today():
        raise HTTPException(422,"Study milestone dates cannot be in the future")
    new_code=f"NCMV-{t.id:05d}"
    if p.study_id and p.study_id!=new_code:
        raise HTTPException(409,"Existing registry study ID requires reconciliation before enrollment")
    t.study_code=new_code;t.enrolled_on=data.enrolled_on;t.status="enrolled"
    t.pcr_anchor_on=data.pcr_anchor_on;t.pcr_anchor_basis=data.pcr_anchor_basis
    t.protocol_reference=data.protocol_reference;t.confirmed_by=u.user_id
    p.study_id=new_code
    for month in MONTHS:
        s.add(PCRRecord(subject_id=t.id,scheduled_month=month,attempt=1,
            specimen_code=code_for(t,"PCR",f"M{month:02d}-A01"),
            target_on=month_date(data.pcr_anchor_on,month),status="planned"))
    audit(s,u,"enroll","trial_subject",str(t.id),p.id,None,
          subject_view(t),"PI enrollment approved; independent randomization remains external")
    s.commit()
    return {"subject":subject_view(t),"pcr_orders":7}

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
    if r.result_entered_by==u.user_id:raise HTTPException(403,"Independent reviewer required")
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
    if data.signed_on>date.today():raise HTTPException(422,"Future signed prescription")
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
    role(u,PHARMACISTS|{"pi","consultant","scientist","monitor"})
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
                 "pharmacy","monitor","pi","admin"]

@router.post("/staff/invite")
def invite_user(data:InviteIn,u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,MANAGERS)
    if data.role in {"pi","admin"} and u.role!="admin":
        raise HTTPException(403,"Only an administrator may delegate privileged roles")
    user=User(username=data.username,display_name=data.display_name,role=data.role,
        password_hash=PH.hash(secrets.token_urlsafe(48)),active=False)
    token=secrets.token_urlsafe(36)
    s.add(user)
    s.flush()  # Generate the DB identity before binding the one-time invitation.
    invitation=UserInvitation(user_id=user.id,token_sha256=sha(token),
        created_by=u.user_id,expires_at=now()+timedelta(days=7))
    s.add(invitation)
    try:
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Username already exists")
    # Secret only returned once over TLS to authenticated inviter, never persisted as plaintext.
    return {"username":user.username,"role":user.role,"activation_token":token,
        "expires_in_days":7,
        "instruction":"Give this one-time token privately to the named staff member. They set their own password. No shared accounts."}

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
    access=StaffAccess(user_id=user.id,activated_at=now(),
        expires_at=now()+timedelta(days=90))
    s.add(access)
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
    }

@router.get("/overview")
def overview(u:AuthContext=Depends(current),s:Session=Depends(db)):
    subject_counts=dict(s.execute(select(TrialSubject.status,func.count())
        .group_by(TrialSubject.status)).all())
    pcr_counts=dict(s.execute(select(PCRRecord.status,func.count())
        .group_by(PCRRecord.status)).all())
    return {"screened":s.scalar(select(func.count(TrialSubject.id))),
        "enrolled":subject_counts.get("enrolled",0),"subject_status":subject_counts,
        "pcr":pcr_counts,"protocol_pcr_per_subject":len(MONTHS),
        "randomization":"external authorized system required",
        "data_mode":"synthetic_staging" if os.getenv("CLINICAL_DATA_ENABLED","false").lower()!="true"
            else "clinical_requested_not_validated"}


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
    record=s.get(UserTotp,u.user_id)
    if not record or record.enabled:
        raise HTTPException(409,"MFA setup missing or already enabled")
    if not pyotp.TOTP(record.secret).verify(data.otp,valid_window=1):
        raise HTTPException(422,"Authenticator code incorrect")
    record.enabled=True;record.confirmed_at=now()
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
        "requires_activation":not usr.active} for usr,access,totp in rows]

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
    if totp and totp.enabled and not (data.otp and pyotp.TOTP(totp.secret).verify(data.otp,valid_window=1)):
        raise HTTPException(403,"Authenticator confirmation required")
    usr.password_hash=PH.hash(data.new_password)
    s.execute(delete(LoginSession).where(LoginSession.user_id==usr.id))
    audit(s,u,"password_change","user",usr.id,None,None,
          {"password_changed":True},"Self-service password rotation; all existing sessions revoked")
    s.commit()
    return {"password_changed":True,"sessions_revoked":True,
            "notice":"Log in again with your new private password"}
