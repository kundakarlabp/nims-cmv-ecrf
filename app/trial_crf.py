"""Audited, schema-checked CRF v3.0 sections C-L, with private server autosave."""
import secrets
from datetime import date
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, update, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .main import AuthContext, current, db, audit, as_dict, now
from .trial_api import find_subject, role
from .trial_models import TrialCRFEntry, TrialCRFDraft, TrialCRFReview, PCRRecord, DrugDispense
from .crf_schema import CRF_FORMS, CRF_VERSION, PROTOCOL_VERSION, validate_payload

router=APIRouter(prefix="/api/trial/crf",tags=["trial-crf-v3"])
FORM_EDITOR={
 "C_baseline":{"pi","consultant","scientist"},
 "D_adherence":{"pi","consultant","scientist","nurse","pharmacy"},
 "E_followup":{"pi","consultant","scientist","nurse","pg"},
 "F_unscheduled_pcr":{"pi","consultant","scientist","microbiology","technician"},
 "G_cmv_event":{"pi","consultant","scientist"},
 "H_adverse_event":{"pi","consultant","scientist","nurse"},
 "I_clinical_outcome":{"pi","consultant","scientist","nurse","pg"},
 "J_deviation":{"pi","consultant","scientist"},
 "K_resource_cost":{"pi","scientist","pharmacy"},
 "L_final_status":{"pi","consultant","scientist"}
}
BLINDED_FORM_SECTIONS={"G_cmv_event","H_adverse_event","I_clinical_outcome","L_final_status"}
REVIEWERS={"pi","consultant","scientist","monitor"}

def allow_read(u,section):
    if section not in CRF_FORMS:raise HTTPException(404,"Unknown CRF form")
    if u.role not in FORM_EDITOR[section] and not ('pi' in FORM_EDITOR[section] and u.pi_authorized) and not (u.role=="monitor" and section in BLINDED_FORM_SECTIONS):
        raise HTTPException(403,"Section not available for this delegated role")

def allow_write(u,section):
    if section not in CRF_FORMS:raise HTTPException(404,"Unknown CRF form")
    role(u,FORM_EDITOR[section])

def visible_entry(row,review_status):
    return {"id":row.id,"subject_id":row.subject_id,"section":row.section,
        "occurrence_key":row.occurrence_key,"occurred_on":row.occurred_on,
        "payload":row.payload,"revision":row.revision,
        "created_by":row.created_by,"updated_by":row.updated_by,
        "review_status":review_status,"updated_at":row.updated_at}

def review_state(s,row):
    review=s.scalar(select(TrialCRFReview).where(
        TrialCRFReview.entry_id==row.id,
        TrialCRFReview.entry_revision==row.revision))
    return review.decision if review else "pending"

def validate_crf(section,payload,partial=False):
    try:return validate_payload(section,payload,partial=partial)
    except ValueError as err:raise HTTPException(422,str(err)) from err

def enforce_record_date(subject,event_on,section):
    if event_on>date.today():raise HTTPException(422,"Future event date prohibited")
    # Baseline might precede transplantation; subsequent follow-up cannot.
    if section not in {"C_baseline"} and subject.pcr_anchor_on and event_on<subject.pcr_anchor_on:
        raise HTTPException(422,"Clinical event cannot precede transplantation")

def enrich_from_sources(s,subject,section,payload):
    result=dict(payload)
    if section=="C_baseline":
        from .randomization import allocation_for, arm_for
        slot=allocation_for(s,subject.id)
        if not slot:
            raise HTTPException(409,"Cannot finalize baseline randomization fields before an independently locked allocation")
        locked={"allocation_code":slot.allocation_code,
                "assigned_nominal_arm":arm_for(s,subject.id)+" mg OD",
                "randomization_on":slot.assigned_at.date().isoformat()}
        if any(key in result and result[key]!=value for key,value in locked.items()):
            raise HTTPException(422,"Manually supplied treatment allocation contradicts the locked randomized group")
        result.update(locked)  # Read-only randomized source of truth, never an editable arm.
    if section=="E_followup" and result.get("pcr_specimen_code"):
        specimen=s.scalar(select(PCRRecord).where(
            PCRRecord.subject_id==subject.id,
            PCRRecord.specimen_code==result["pcr_specimen_code"]))
        if not specimen or specimen.scheduled_month!=int(result["scheduled_month"]):
            raise HTTPException(422,"PCR specimen code does not match this subject and scheduled month")
        result["_verified_pcr_reference"]={
            "specimen_code":specimen.specimen_code,
            "result_status":specimen.status,
            "result_kind":specimen.result_kind if specimen.status=="verified" else None,
            "quantitative_iu_ml":specimen.quantitative_iu_ml if specimen.status=="verified" else None
        }
    if section=="D_adherence" and result.get("dispensing_slip_code"):
        slip=s.scalar(select(DrugDispense).where(
            DrugDispense.subject_id==subject.id,
            DrugDispense.slip_code==result["dispensing_slip_code"]))
        if not slip:
            raise HTTPException(422,"MSS dispensing reference not issued for this study subject")
        result["_verified_mss_issue"]={"slip_code":slip.slip_code,
            "quantity_issued":slip.quantity_issued,"issued_on":slip.issued_on.isoformat()}
    return result

def occurrence_for(section,payload,requested=None):
    kind=CRF_FORMS[section]["repeat"]
    if kind=="single":return "MAIN"
    if kind=="month":
        month=payload.get("scheduled_month")
        if not month:raise HTTPException(422,"Choose the protocol visit month")
        return "M"+str(month).zfill(2)
    # Each event is independently numbered; no arbitrary user-supplied key
    # that could accidentally overwrite an earlier clinical event.
    if requested and requested.startswith("NEW"):return "EVENT-"+secrets.token_hex(8)
    return "EVENT-"+secrets.token_hex(8)

@router.get("/schema")
def crf_schema(u:AuthContext=Depends(current)):
    # Never render treatment-arm fields as editable CRF inputs.
    permitted={k:dict(v,fields=dict(v["fields"])) for k,v in CRF_FORMS.items()
              if u.role in FORM_EDITOR[k] or ('pi' in FORM_EDITOR[k] and u.pi_authorized) or (u.role=="monitor" and k in BLINDED_FORM_SECTIONS)}
    if "C_baseline" in permitted:
        for key in ("allocation_code","assigned_nominal_arm","randomization_on"):
            permitted["C_baseline"]["fields"].pop(key,None)
    return {"crf_version":CRF_VERSION,"protocol_version":PROTOCOL_VERSION,
        "forms":permitted,"notice":"CRF v3.0 approved-form mapping; randomization and dosing are separate controlled functions"}

@router.get("/subjects/{subject_id}/entries")
def list_forms(subject_id:int,section:str|None=None,
               u:AuthContext=Depends(current),s:Session=Depends(db)):
    subject=find_subject(s,subject_id)
    if section:allow_read(u,section)
    st=select(TrialCRFEntry).where(TrialCRFEntry.subject_id==subject.id)
    if section:st=st.where(TrialCRFEntry.section==section)
    rows=s.scalars(st.order_by(TrialCRFEntry.updated_at.desc()).limit(400)).all()
    return {"study_code":subject.study_code,
        "entries":[visible_entry(e,review_state(s,e)) for e in rows
                if u.role in FORM_EDITOR[e.section] or ('pi' in FORM_EDITOR[e.section] and u.pi_authorized) or
                   (u.role=="monitor" and e.section in BLINDED_FORM_SECTIONS)]}

class CRFDraftInput(BaseModel):
    occurred_on:date
    payload:dict[str,Any]
    occurrence_key:str=Field(default="NEW",min_length=1,max_length=60)
    expected_revision:int|None=Field(default=None,ge=1)

@router.get("/subjects/{subject_id}/drafts/{section}")
def get_draft(subject_id:int,section:str,occurrence_key:str="NEW",
              u:AuthContext=Depends(current),s:Session=Depends(db)):
    allow_write(u,section);subject=find_subject(s,subject_id)
    d=s.scalar(select(TrialCRFDraft).where(
        TrialCRFDraft.user_id==u.user_id,TrialCRFDraft.subject_id==subject.id,
        TrialCRFDraft.section==section,TrialCRFDraft.occurrence_key==occurrence_key))
    return {"draft":as_dict(d) if d else None}

@router.put("/subjects/{subject_id}/drafts/{section}")
def save_draft(subject_id:int,section:str,data:CRFDraftInput,
               u:AuthContext=Depends(current),s:Session=Depends(db)):
    allow_write(u,section);subject=find_subject(s,subject_id)
    enforce_record_date(subject,data.occurred_on,section)
    checked=validate_crf(section,data.payload,partial=True)
    if len(str(checked))>25000:raise HTTPException(413,"Draft too large")
    # Occurrence keys for draft forms: MAIN, M01 etc, or NEW for event work.
    if data.occurrence_key not in ("MAIN","NEW") and not (
        section=="E_followup" and data.occurrence_key in {"M01","M02","M03","M04","M06","M09","M12"}):
        raise HTTPException(422,"Invalid draft occurrence")
    d=s.scalar(select(TrialCRFDraft).where(TrialCRFDraft.user_id==u.user_id,
        TrialCRFDraft.subject_id==subject.id,TrialCRFDraft.section==section,
        TrialCRFDraft.occurrence_key==data.occurrence_key))
    if not d:
        if data.expected_revision is not None:raise HTTPException(409,"Draft deleted elsewhere")
        d=TrialCRFDraft(user_id=u.user_id,subject_id=subject.id,
           section=section,occurrence_key=data.occurrence_key,
           occurred_on=data.occurred_on,payload=checked)
        s.add(d)
        try:s.commit()
        except IntegrityError:s.rollback();raise HTTPException(409,"Draft concurrently created")
    else:
        if d.revision!=data.expected_revision:raise HTTPException(409,"Draft revision conflict")
        changed=s.execute(update(TrialCRFDraft).where(
           TrialCRFDraft.id==d.id,TrialCRFDraft.revision==data.expected_revision)
           .values(occurred_on=data.occurred_on,payload=checked,
                   revision=TrialCRFDraft.revision+1,updated_at=now()))
        if changed.rowcount!=1:s.rollback();raise HTTPException(409,"Draft changed in another tab")
        s.commit();s.refresh(d)
    return {"id":d.id,"revision":d.revision,"updated_at":d.updated_at,
        "is_draft":True,"not_part_of_verified_trial_data":True}

@router.delete("/subjects/{subject_id}/drafts/{section}")
def remove_draft(subject_id:int,section:str,occurrence_key:str,
                 expected_revision:int,
                 u:AuthContext=Depends(current),s:Session=Depends(db)):
    allow_write(u,section);subject=find_subject(s,subject_id)
    changed=s.execute(delete(TrialCRFDraft).where(
      TrialCRFDraft.user_id==u.user_id,TrialCRFDraft.subject_id==subject.id,
      TrialCRFDraft.section==section,TrialCRFDraft.occurrence_key==occurrence_key,
      TrialCRFDraft.revision==expected_revision))
    if changed.rowcount!=1:s.rollback();raise HTTPException(409,"Draft was changed; reload")
    s.commit()
    return {"ok":True}

class CRFSubmitIn(BaseModel):
    section:str
    occurred_on:date
    payload:dict[str,Any]

@router.post("/subjects/{subject_id}/entries")
def submit_crf(subject_id:int,data:CRFSubmitIn,
               u:AuthContext=Depends(current),s:Session=Depends(db)):
    allow_write(u,data.section);subject=find_subject(s,subject_id)
    if not subject.enrolled_on:raise HTTPException(409,"Screening not enrolled")
    enforce_record_date(subject,data.occurred_on,data.section)
    checked=validate_crf(data.section,data.payload)
    key=occurrence_for(data.section,checked)
    checked=enrich_from_sources(s,subject,data.section,checked)
    if len(str(checked))>25000:raise HTTPException(413,"Form exceeds allowed size")
    row=TrialCRFEntry(subject_id=subject.id,section=data.section,
         occurrence_key=key,occurred_on=data.occurred_on,payload=checked,
         created_by=u.user_id,updated_by=u.user_id)
    s.add(row)
    try:
        s.flush()
        audit(s,u,"crf_submit","trial_crf",str(row.id),subject.patient_id,None,
            as_dict(row),"CRF v3.0 submitted for independent review")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"This visit/section is already submitted; edit with reason")
    return {"entry_id":row.id,"revision":row.revision,"occurrence_key":key,
            "review_status":"pending"}

class CRFEditIn(BaseModel):
    expected_revision:int=Field(ge=1)
    occurred_on:date
    payload:dict[str,Any]
    reason:str=Field(min_length=8,max_length=500)

@router.put("/entries/{entry_id}")
def edit_crf(entry_id:int,data:CRFEditIn,
             u:AuthContext=Depends(current),s:Session=Depends(db)):
    row=s.get(TrialCRFEntry,entry_id)
    if not row:raise HTTPException(404)
    allow_write(u,row.section);subject=find_subject(s,row.subject_id)
    if row.revision!=data.expected_revision:raise HTTPException(409,"Revision conflict")
    checked=validate_crf(row.section,data.payload)
    if occurrence_for(row.section,checked)!=row.occurrence_key and CRF_FORMS[row.section]["repeat"]!="event":
        raise HTTPException(422,"Cannot change a submitted visit month or form identity")
    enforce_record_date(subject,data.occurred_on,row.section)
    checked=enrich_from_sources(s,subject,row.section,checked)
    old=as_dict(row)
    changed=s.execute(update(TrialCRFEntry).where(
        TrialCRFEntry.id==entry_id,TrialCRFEntry.revision==data.expected_revision)
        .values(payload=checked,occurred_on=data.occurred_on,
                updated_by=u.user_id,updated_at=now(),
                revision=TrialCRFEntry.revision+1))
    if changed.rowcount!=1:s.rollback();raise HTTPException(409,"Concurrent edit; reload")
    s.flush();s.refresh(row)
    audit(s,u,"crf_correct","trial_crf",str(row.id),subject.patient_id,
          old,as_dict(row),data.reason)
    s.commit()
    return {"entry_id":row.id,"revision":row.revision,"review_status":"pending"}

class CRFReviewIn(BaseModel):
    expected_revision:int=Field(ge=1)
    decision:Literal["verified","needs_correction"]
    reason:str=Field(min_length=8,max_length=500)

@router.post("/entries/{entry_id}/review")
def review_crf(entry_id:int,data:CRFReviewIn,
               u:AuthContext=Depends(current),s:Session=Depends(db)):
    row=s.get(TrialCRFEntry,entry_id)
    if not row:raise HTTPException(404)
    allow_read(u,row.section);role(u,REVIEWERS)
    subject=find_subject(s,row.subject_id)
    if u.user_id in (row.created_by,row.updated_by):
        raise HTTPException(403,"Independent review required")
    if row.revision!=data.expected_revision:raise HTTPException(409,"Stale revision")
    if review_state(s,row)!="pending":raise HTTPException(409,"Revision already reviewed")
    rec=TrialCRFReview(entry_id=row.id,entry_revision=row.revision,
         decision=data.decision,reason=data.reason,reviewer_id=u.user_id)
    s.add(rec)
    audit(s,u,"crf_review","trial_crf",str(row.id),subject.patient_id,
          None,{"reviewed_revision":row.revision,"decision":data.decision},data.reason)
    try:s.commit()
    except IntegrityError:s.rollback();raise HTTPException(409,"Concurrent review")
    return {"entry_id":row.id,"review_status":data.decision}

@router.get("/review-queue")
def crf_review_queue(u:AuthContext=Depends(current),s:Session=Depends(db)):
    role(u,REVIEWERS)
    rows=s.scalars(select(TrialCRFEntry).order_by(
         TrialCRFEntry.updated_at.desc()).limit(300)).all()
    return [visible_entry(e,review_state(s,e)) for e in rows
            if (u.role in FORM_EDITOR[e.section] or ('pi' in FORM_EDITOR[e.section] and u.pi_authorized) or
               (u.role=="monitor" and e.section in BLINDED_FORM_SECTIONS))
              and u.user_id not in (e.created_by,e.updated_by)]

@router.get("/completeness")
def crf_completeness(u:AuthContext=Depends(current),s:Session=Depends(db)):
    rows=s.scalars(select(TrialCRFEntry).where(TrialCRFEntry.section=="E_followup")).all()
    slots={m:{"submitted":0,"verified":0,"needs_correction":0}
       for m in ("1","2","3","4","6","9","12")}
    for row in rows:
        m=row.payload.get("scheduled_month")
        if m not in slots:continue
        slots[m]["submitted"]+=1
        r=review_state(s,row)
        if r in slots[m]:slots[m][r]+=1
    return {"visit_completion":slots,
        "denominator_note":"Enrollment denominator must be read from trial overview and follow-up eligibility; does not infer missing PCR result"}

