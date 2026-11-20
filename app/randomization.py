"""Concealed, stratified 1:1 allocation controlled by an independent statistician.

Protocol v5 (14 August 2026): stratify rATG yes/no × donor living/deceased;
variable permuted blocks. Do not self-generate live sequences in this API.
Only the independent custodian can import/lock a previously prepared, signed
sequence. Each future allocation is encrypted at rest; no future arm is
returned by any endpoint. No re-randomization or manual arm assignment.
"""
import hashlib
import json
import os
import secrets
from pathlib import Path
from collections import Counter, defaultdict
from datetime import date
from typing import Literal
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .main import AuthContext, current, db, audit, now, CLINICAL_MODE
from .trial_models import RandomizationPlan, RandomizationSlot, TrialEligibility
from .clinical_gate import owner_authorized
from .workspace_policy import enabled as team_workspace

router=APIRouter(prefix="/api/trial/randomization", tags=["randomization"])
STRATA=("rATG:living","rATG:deceased","no_rATG:living","no_rATG:deceased")
ARMS=("450","900")
REVEAL_ROLES={"pi","consultant","pharmacy","scientist","nurse","pg"}
CUSTODIAN_ROLE="randomization_custodian"

def cipher():
    # Clinical installations read a protected mounted key, never a GitHub or
    # Compose environment variable. Synthetic CI may use an env-only key.
    keyfile=os.getenv("RANDOMIZATION_FERNET_KEY_FILE","")
    try:
        key=Path(keyfile).read_text(encoding="ascii").strip() if keyfile else (
            os.getenv("RANDOMIZATION_FERNET_KEY",""))
    except (OSError,UnicodeError):
        raise HTTPException(503,"Sealed allocation key is unavailable")
    if not key:
        raise HTTPException(503,"Sealed allocation key is not configured; contact system custodian")
    try:return Fernet(key.encode("ascii"))
    except (ValueError,TypeError):
        raise HTTPException(503,"Sealed allocation key invalid; contact system custodian")

def stratum(subject):
    if subject.ratg_induction is None or subject.donor_type not in {"living","deceased"}:
        raise HTTPException(422,"Document induction and donor type before randomization")
    return ("rATG" if subject.ratg_induction else "no_rATG")+":"+subject.donor_type

def canonical(rows):
    return json.dumps(sorted(
        [{"stratum":r["stratum"],"position":r["position"],"block_no":r["block_no"],
          "block_size":r["block_size"],"arm":r["arm"]} for r in rows],
        key=lambda r:(r["stratum"],r["position"])),
        sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")

class SequenceEntry(BaseModel):
    stratum:Literal["rATG:living","rATG:deceased","no_rATG:living","no_rATG:deceased"]
    position:int=Field(ge=1,le=10000)
    block_no:int=Field(ge=1,le=10000)
    block_size:int=Field(ge=2,le=20)
    arm:Literal["450","900"]

class ImportSequence(BaseModel):
    protocol_version:Literal["5.0"]
    statistician_reference:str=Field(min_length=8,max_length=160)
    signed_specification_reference:str=Field(min_length=8,max_length=160)
    independent_sequence_attested:bool
    legacy_reconciliation_reference:str|None=Field(default=None,min_length=8,max_length=160)
    sequence_sha256:str=Field(pattern=r"^[0-9a-f]{64}$")
    entries:list[SequenceEntry]=Field(min_length=20,max_length=5000)

def check_sequence(raw):
    groups=defaultdict(list)
    for row in raw:
        groups[row["stratum"]].append(row)
    if set(groups)!=set(STRATA):
        raise HTTPException(422,"Allocation import must cover all 4 protocol strata")
    used_sizes=set()
    for name,group in groups.items():
        group.sort(key=lambda x:x["position"])
        if [x["position"] for x in group]!=list(range(1,len(group)+1)):
            raise HTTPException(422,f"Noncontiguous positions in {name}")
        blocks=defaultdict(list)
        for x in group:
            if x["block_size"]%2 or x["block_size"] not in {4,6,8,10}:
                raise HTTPException(422,"Block sizes must be prespecified even permuted sizes")
            blocks[x["block_no"]].append(x)
        if sorted(blocks)!=list(range(1,len(blocks)+1)):
            raise HTTPException(422,f"Noncontiguous block numbers in {name}")
        next_position=1
        for idx in sorted(blocks):
            block=blocks[idx]
            size=block[0]["block_size"]
            if sorted(x["position"] for x in block)!=list(range(next_position,next_position+size)):
                raise HTTPException(422,f"Permuted block positions not contiguous in {name}/{idx}")
            next_position+=size
            if len(block)!=size or any(x["block_size"]!=size for x in block):
                raise HTTPException(422,f"Incomplete permuted block {name}/{idx}")
            if Counter(x["arm"] for x in block)!={"450":size//2,"900":size//2}:
                raise HTTPException(422,f"Unbalanced 1:1 block {name}/{idx}")
            used_sizes.add(size)
    if len(used_sizes)<2:
        raise HTTPException(422,"Variable permuted blocks require at least 2 approved sizes")
    return {name:len(values) for name,values in groups.items()},sorted(used_sizes)

@router.post("/sequence/lock")
def lock_sequence(data:ImportSequence,u:AuthContext=Depends(current),
                  s:Session=Depends(db)):
    if u.role!=CUSTODIAN_ROLE and not (team_workspace() and (u.workspace_full_access or u.pi_authorized)):
        raise HTTPException(403,"Only an independent randomization custodian can lock a sealed sequence")
    if not data.independent_sequence_attested and not team_workspace():
        raise HTTPException(422,"Independent generation/signature must be attested")
    if CLINICAL_MODE and not team_workspace() and not data.legacy_reconciliation_reference:
        raise HTTPException(422,"Document reconciliation of prior worksheet allocations before locking a new official sequence")
    if s.scalar(select(RandomizationPlan.id).limit(1)) is not None:
        raise HTTPException(409,"Sequence permanently locked already; cannot replace or reseed")
    rows=[r.model_dump() for r in data.entries]
    counts,sizes=check_sequence(rows)
    digest=hashlib.sha256(canonical(rows)).hexdigest()
    if not secrets.compare_digest(digest,data.sequence_sha256):
        raise HTTPException(422,"Signed sequence SHA-256 mismatch; no import performed")
    if CLINICAL_MODE:
        if sum(counts.values())<344 or any(count<80 for count in counts.values()):
            raise HTTPException(422,"Official sequence must have adequate slots in all four strata")
        if not owner_authorized(os.environ) and os.getenv("RANDOMIZATION_APPROVED_SHA256")!=digest:
            raise HTTPException(403,"Sequence fingerprint does not match locked institutional approval")
    f=cipher()
    plan=RandomizationPlan(protocol_version=data.protocol_version,
        statistician_reference=data.statistician_reference,
        signed_specification_reference=data.signed_specification_reference,
        sequence_sha256=digest,block_sizes={"sizes":sizes,"capacities":counts},
        locked_by=u.user_id,locked_at=now(),active=True)
    s.add(plan)
    try:
        s.flush()
        for row in rows:
            s.add(RandomizationSlot(plan_id=plan.id,stratum=row["stratum"],
                position=row["position"],encrypted_arm=f.encrypt(
                    row["arm"].encode("ascii")).decode("ascii")))
        # All rows encrypted before commit, and only hashed metadata reaches audit.
        audit(s,u,"randomization_lock","randomization_plan",str(plan.id),None,None,
              {"protocol_version":plan.protocol_version,"sequence_sha256":digest,
               "capacities":counts,"block_sizes":sizes,
               "signed_specification_reference":plan.signed_specification_reference,
               "legacy_reconciliation_reference":data.legacy_reconciliation_reference,
               "independent_sequence_attested":data.independent_sequence_attested,
               "allocation_management":"owner_managed" if team_workspace() else "independent_custodian"},
              "Owner-managed sealed sequence locked" if team_workspace() else "Independent, sealed sequence imported and permanently locked")
        s.commit()
    except IntegrityError:
        s.rollback()
        raise HTTPException(409,"Sequence lock conflict; do not re-import")
    return {"locked":True,"sequence_sha256":digest,"plan_id":plan.id,
            "stratum_capacities":counts,"approved_block_sizes":sizes,
            "future_allocations":"not accessible to clinical, monitor or pharmacy users"}

class GenerateSequence(BaseModel):
    statistician_reference:str=Field(min_length=8,max_length=160)
    signed_specification_reference:str=Field(min_length=8,max_length=160)
    independent_sequence_attested:bool=True
    legacy_reconciliation_reference:str|None=Field(default=None,min_length=8,max_length=160)
    block_sizes:list[int]=Field(min_length=2,max_length=4)

@router.post('/sequence/generate-and-lock')
def generate_and_lock(data:GenerateSequence,u:AuthContext=Depends(current),s:Session=Depends(db)):
    # The separately authorized custodian acts personally. Never seed a live
    # sequence on deployment, or allow the eligibility investigator to generate.
    if u.role!=CUSTODIAN_ROLE and not (team_workspace() and (u.workspace_full_access or u.pi_authorized)):
        raise HTTPException(403,'Sequence management permission required')
    if CLINICAL_MODE and not team_workspace() and not data.legacy_reconciliation_reference:
        raise HTTPException(422,'Reconcile prior worksheet allocations before generating a new official sequence')
    sizes=sorted(set(data.block_sizes))
    if len(sizes)<2 or any(size not in {4,6,8,10} for size in sizes):
        raise HTTPException(422,'Prespecify at least two distinct sizes from 4, 6, 8, 10')
    rng=secrets.SystemRandom();rows=[]
    for name in STRATA:
        position=0;block=0
        # Each stratum can accommodate the entire trial without disclosing or
        # needing to predict its eventual recruitment proportion.
        while position<344:
            size=rng.choice(sizes)
            block+=1
            arms=['450']*(size//2)+['900']*(size//2);rng.shuffle(arms)
            for arm in arms:
                position+=1;rows.append(dict(stratum=name,position=position,block_no=block,block_size=size,arm=arm))
    digest=hashlib.sha256(canonical(rows)).hexdigest()
    return lock_sequence(ImportSequence(protocol_version='5.0',
        statistician_reference=data.statistician_reference,
        signed_specification_reference=data.signed_specification_reference,
        independent_sequence_attested=data.independent_sequence_attested,legacy_reconciliation_reference=data.legacy_reconciliation_reference,
        sequence_sha256=digest,entries=rows),u,s)

def plan_enabled(plan):
    if not plan:return False
    return not CLINICAL_MODE or (os.getenv('RANDOMIZATION_ENABLED')=='true' and
        (owner_authorized(os.environ) or os.getenv('RANDOMIZATION_APPROVED_SHA256')==plan.sequence_sha256))

@router.get("/readiness")
def readiness(u:AuthContext=Depends(current),s:Session=Depends(db)):
    plan=s.scalar(select(RandomizationPlan).order_by(RandomizationPlan.id).limit(1))
    slots=s.scalar(select(func.count(RandomizationSlot.id))) or 0
    allocated=s.scalar(select(func.count(RandomizationSlot.id)).where(
        RandomizationSlot.subject_id.is_not(None))) or 0
    enabled=plan_enabled(plan)
    return {"sequence_locked":bool(plan),"protocol":"5.0","strata":list(STRATA),
            "planned_randomizations":slots,"randomized":allocated,
            "sequence_sha256":plan.sequence_sha256 if plan else None,
            "activation_ready":enabled,"clinical_mode":CLINICAL_MODE,
            "custodian_required":not team_workspace(),
            "allocation_management":"owner_managed" if team_workspace() else "independent_custodian",
            "note":"Counts do not reveal unassigned arms, block order or future sequence."}

def allocation_for(s,subject_id):
    return s.scalar(select(RandomizationSlot).where(
        RandomizationSlot.subject_id==subject_id))

def arm_for(s,subject_id):
    row=allocation_for(s,subject_id)
    if row is None:return None
    try:
        value=cipher().decrypt(row.encrypted_arm.encode("ascii")).decode("ascii")
    except InvalidToken:
        raise HTTPException(503,"Allocation key mismatch; stop dispensing and contact custodian")
    if value not in ARMS:
        raise HTTPException(503,"Allocation integrity failure; stop dispensing")
    return value

class RandomizeInput(BaseModel):
    investigator_confirmation:Literal[True]
    signed_randomization_source_ref:str=Field(min_length=8,max_length=160)
    stratification_verified:Literal[True]

def _next_slot_for_subject(s:Session,subject,*,lock:bool=False):
    """Use identical server-side prerequisites for read-only preflight and release.

    Preflight never decrypts or reserves an arm. The release rechecks within
    its locked transaction; the UI readiness indicator grants no authority.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    local_today=datetime.now(ZoneInfo("Asia/Kolkata")).date()
    if subject.status!="enrolled" or not subject.enrolled_on or subject.confirmed_by is None:
        raise HTTPException(409,"Approved active enrollment required before randomization")
    if not subject.consent_on or subject.consent_on>subject.enrolled_on:
        raise HTTPException(422,"Signed consent must precede randomization")
    if CLINICAL_MODE:
        from .main import Patient
        transplant=s.get(Patient,subject.patient_id).transplant_date
        days=(local_today-transplant).days if transplant else None
        if days is None or not 0<=days<=10:
            raise HTTPException(422,"Randomization outside protocol day 0–10 after transplantation")
    eligibility=s.get(TrialEligibility,subject.id)
    if (not eligibility or not eligibility.baseline.get("is_eligible")
        or not all(eligibility.inclusion.values())
        or any(eligibility.exclusion.values())
        or eligibility.reviewed_on>local_today):
        raise HTTPException(422,"Fresh signed, complete eligibility review required")
    if allocation_for(s,subject.id):
        raise HTTPException(409,"Participant already randomized; never rerandomize")
    statement=select(RandomizationPlan).where(RandomizationPlan.active.is_(True)).limit(1)
    if lock:statement=statement.with_for_update()
    plan=s.scalar(statement)
    if not plan:raise HTTPException(503,"No locked allocation sequence")
    allocated=s.scalar(select(func.count(RandomizationSlot.id)).where(
        RandomizationSlot.subject_id.is_not(None))) or 0
    if allocated>=344:raise HTTPException(409,"Protocol recruitment target reached; no further allocation allowed")
    if not plan_enabled(plan):
        raise HTTPException(403,"Clinical randomization awaits approved release and sequence fingerprint")
    key=stratum(subject)
    statement=(select(RandomizationSlot)
        .where(RandomizationSlot.plan_id==plan.id,RandomizationSlot.stratum==key,
               RandomizationSlot.subject_id.is_(None))
        .order_by(RandomizationSlot.position).limit(1))
    if lock:statement=statement.with_for_update()
    row=s.scalar(statement)
    if not row:raise HTTPException(409,"Sequence exhausted in this stratum; refer to statistician")
    return plan,key,row

@router.get("/subjects/{subject_id}/preflight")
def randomization_preflight(subject_id:int,u:AuthContext=Depends(current),
                            s:Session=Depends(db)):
    """No write, no decrypted arm and no released or future block information."""
    from .trial_api import find_subject
    subject=find_subject(s,subject_id)
    try:
        _,key,_=_next_slot_for_subject(s,subject)
    except HTTPException as exc:
        return {"ready":False,"randomized":bool(allocation_for(s,subject_id)),
                "study_code":subject.study_code,"reason":str(exc.detail)}
    return {"ready":True,"randomized":False,"study_code":subject.study_code,
            "stratum":key,"reason":"Protocol checks passed. Verify signed source and confirm irreversible allocation."}

@router.post("/subjects/{subject_id}/assign")
def assign(subject_id:int,data:RandomizeInput,u:AuthContext=Depends(current),
           s:Session=Depends(db)):
    if u.role!="pi" and not u.pi_authorized:
        raise HTTPException(403,"Only an authorized clinical workspace account may release an allocation")
    from .trial_api import active_subject
    subject=active_subject(s,subject_id)
    plan,key,row=_next_slot_for_subject(s,subject,lock=True)
    # Verify the sealed assignment *before* consuming the irreversible slot.
    try:
        assigned_arm=cipher().decrypt(row.encrypted_arm.encode("ascii")).decode("ascii")
    except InvalidToken:
        raise HTTPException(503,"Allocation encryption key mismatch; assignment not consumed")
    if assigned_arm not in ARMS:
        raise HTTPException(503,"Sealed allocation integrity failure; assignment not consumed")
    code="NCMV-R-"+secrets.token_hex(7).upper()
    matched=s.execute(update(RandomizationSlot).where(
        RandomizationSlot.id==row.id,RandomizationSlot.subject_id.is_(None))
        .values(subject_id=subject_id,assigned_by=u.user_id,assigned_at=now(),
                signed_source_reference=data.signed_randomization_source_ref,
                allocation_code=code))
    if matched.rowcount!=1:
        s.rollback();raise HTTPException(409,"Concurrent allocation; reload and retry")
    try:
        audit(s,u,"randomize","randomization_slot",str(row.id),subject.patient_id,
              None,{"allocation_code":code,"stratum":key,
                    "sequence_sha256":plan.sequence_sha256,
                    "signed_source_reference":data.signed_randomization_source_ref},
              "Next concealed sequential allocation released after eligibility")
        s.commit()
    except IntegrityError:
        s.rollback();raise HTTPException(409,"Duplicate participant randomization; check existing assignment")
    return {"allocation_code":code,"study_code":subject.study_code,
            "assigned_arm_mg":assigned_arm,
            "stratum":key,"assigned_at":row.assigned_at,
            "note":"Open-label nominal group; renal adjustment follows signed physician prescription"}

@router.get("/subjects/{subject_id}/allocation")
def read_allocation(subject_id:int,u:AuthContext=Depends(current),
                    s:Session=Depends(db)):
    from .trial_api import find_subject
    subject=find_subject(s,subject_id)
    row=allocation_for(s,subject_id)
    if row is None:
        return {"study_code":subject.study_code,"randomized":False,
                "arm":"not yet released"}
    masked={"study_code":subject.study_code,"randomized":True,
        "allocation_code":row.allocation_code,"stratum":row.stratum,
        "assigned_at":row.assigned_at}
    if u.role in REVEAL_ROLES or u.pi_authorized:
        masked["assigned_arm_mg"]=arm_for(s,subject_id)
    elif u.role not in {"scientist","nurse","monitor","pg","technician","microbiology"}:
        raise HTTPException(403,"No allocation access for role")
    return masked

@router.get("/assigned-group-counts")
def assigned_group_counts(u:AuthContext=Depends(current),s:Session=Depends(db)):
    # Even observed aggregate group totals can reveal future assignments near the
    # end of a permuted block. Conceal them from all recruitment/dispensing staff.
    if u.role!="randomization_custodian" and not (team_workspace() and u.workspace_full_access):
        raise HTTPException(403,"Arm totals concealed from the enrolling clinical team")
    rows=s.scalars(select(RandomizationSlot).where(
        RandomizationSlot.subject_id.is_not(None))).all()
    summary={"450":0,"900":0}
    for row in rows:
        group=arm_for(s,row.subject_id)
        summary[group]+=1
    return {"randomized":sum(summary.values()),"group_450":summary["450"],
        "group_900":summary["900"],
        "note":"Only realized assignments; no future block or allocation disclosed"}

