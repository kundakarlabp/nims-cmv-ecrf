"""Same-origin assistant-workflow adapter; never an unauthenticated ChatGPT relay.

Authenticated users retain existing CRF permissions, clinical write gates, CSRF,
and database audit. This module does NOT accept third-party bearer credentials;
a future private MCP connection must implement scoped user-bound OAuth separately.
"""
from sqlalchemy import select, update, func, or_
from sqlalchemy.exc import IntegrityError
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .main import (
    AuthContext, current, db, Patient, PatientIn, EntryIn, EntryEdit,
    create_patient, patient as get_patient_record, patients as search_registry,
    new_entry, edit_entry, permission, audit, as_dict, now, CLINICAL_MODE,
    patient_archived, active_patient_filter, ARCHIVE_ACTION, normalized_screening_code
)
from .trial_api import subjects as find_subjects, find_subject
from .trial_crf import (
    CRFDraftInput, CRFSubmitIn, CRFEditIn,
    save_draft, submit_crf, edit_crf, list_forms,
)
from .trial_models import TrialCRFEntry, TrialSubject

router = APIRouter(prefix="/api/assistant", tags=["authenticated-assistant-workflow"])


def _check_study_code(s: Session, subject_id: int, study_code: str):
    subject = find_subject(s, subject_id)
    if not subject.study_code or subject.study_code != study_code:
        raise HTTPException(409, "Study ID does not match the selected participant")
    return subject


class AssistedDraft(CRFDraftInput):
    study_code: str = Field(min_length=4, max_length=40)


class AssistedSubmit(CRFSubmitIn):
    study_code: str = Field(min_length=4, max_length=40)
    confirm_submission: bool = False


class AssistedCorrection(CRFEditIn):
    study_code: str = Field(min_length=4, max_length=40)
    confirm_correction: bool = False


@router.get("/capabilities")
def capabilities(u: AuthContext = Depends(current)):
    return {
        "connection": "existing authenticated same-origin study session",
        "external_chat_connection_active": False,
        "actor_id": u.user_id,
        "requires_csrf_for_writes": True,
        "operations": ["search_subject", "read_crf", "save_crf_draft",
                       "submit_confirmed_crf", "correct_confirmed_crf",
                       "search_patient", "register_patient", "read_patient",
                       "correct_patient_identity", "create_registry_entry",
                       "correct_registry_entry", "save_crf_draft_by_identifier"],
        "unavailable_operations": ["randomize", "prescribe", "dispense",
                                    "verify_consent", "change_trial_allocation"],
        "privacy": "No patient records or session credentials are sent to GitHub or Supabase",
    }


@router.get("/subjects")
def search_subjects(q: str = Query(min_length=3, max_length=100),
                    u: AuthContext = Depends(current),
                    s: Session = Depends(db)):
    # An empty query must never enumerate the clinical registry through this API.
    if not q.strip() or len(q.strip()) < 3:
        raise HTTPException(422, "Enter at least 3 characters of a CR number, study ID or name")
    return find_subjects(q=q.strip(), limit=10, before_id=None, u=u, s=s)


@router.get("/subjects/{subject_id}/crf")
def read_crf(subject_id: int,
             u: AuthContext = Depends(current),
             s: Session = Depends(db)):
    find_subject(s, subject_id)
    return list_forms(subject_id, section=None, u=u, s=s)


@router.put("/subjects/{subject_id}/drafts/{section}")
def save_assisted_draft(subject_id: int, section: str, data: AssistedDraft,
                        u: AuthContext = Depends(current),
                        s: Session = Depends(db)):
    _check_study_code(s, subject_id, data.study_code)
    return save_draft(subject_id, section,
                      CRFDraftInput.model_validate(data.model_dump(exclude={"study_code"})),
                      u=u, s=s)


@router.post("/subjects/{subject_id}/entries")
def submit_assisted_crf(subject_id: int, data: AssistedSubmit,
                        u: AuthContext = Depends(current),
                        s: Session = Depends(db)):
    if data.confirm_submission is not True:
        raise HTTPException(422, "Explicit submission confirmation required")
    _check_study_code(s, subject_id, data.study_code)
    return submit_crf(subject_id,
                      CRFSubmitIn.model_validate(data.model_dump(exclude={"study_code","confirm_submission"})),
                      u=u, s=s)


@router.put("/entries/{entry_id}")
def correct_assisted_crf(entry_id: int, data: AssistedCorrection,
                          u: AuthContext = Depends(current),
                          s: Session = Depends(db)):
    if data.confirm_correction is not True:
        raise HTTPException(422, "Explicit correction confirmation required")
    entry = s.get(TrialCRFEntry, entry_id)
    if not entry:
        raise HTTPException(404, "CRF entry not found")
    _check_study_code(s, entry.subject_id, data.study_code)
    return edit_crf(entry_id,
                    CRFEditIn.model_validate(data.model_dump(exclude={"study_code","confirm_correction"})),
                    u=u, s=s)


# The established registry API owns clinical validation, write permissions and
# audit. These convenience routes remove repeated manual patient-ID lookup;
# there is no second data store or service-account privilege.
@router.get("/patients")
def find_registry_patients(q: str = Query(min_length=2, max_length=100),
                           u: AuthContext = Depends(current),
                           s: Session = Depends(db)):
    return search_registry(q=q.strip(), limit=20, u=u, s=s)


@router.get("/patients/{patient_id}")
def read_registry_patient(patient_id: str,
                          u: AuthContext = Depends(current),
                          s: Session = Depends(db)):
    return get_patient_record(patient_id, u=u, s=s)


@router.post("/patients")
def register_assisted_patient(data: PatientIn,
                              u: AuthContext = Depends(current),
                              s: Session = Depends(db)):
    return create_patient(data, u=u, s=s)


class RegistryCorrection(BaseModel):
    expected_revision: int = Field(ge=1)
    expected_cr_number: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=250)
    cr_number: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=500)


@router.put("/patients/{patient_id}")
def correct_registry_patient(patient_id: str, data: RegistryCorrection,
                             u: AuthContext = Depends(current),
                             s: Session = Depends(db)):
    if u.role not in {"admin", "pi", "consultant", "scientist"}:
        raise HTTPException(403, "Registry correction permission required")
    record = s.get(Patient, patient_id)
    if not record:
        raise HTTPException(404, "Patient not found")
    if patient_archived(s,patient_id):
        raise HTTPException(409, "Registry record archived")
    if record.revision != data.expected_revision or record.cr_number != data.expected_cr_number:
        raise HTTPException(409, "Patient identity or revision changed; reload")
    if not CLINICAL_MODE and not (data.cr_number.upper().startswith("TEST-")
                                 and data.name.lower().startswith("synthetic")):
        raise HTTPException(403, "Synthetic-only staging")
    old = as_dict(record)
    try:
        changed = s.execute(update(Patient).where(
            Patient.id == patient_id, Patient.revision == data.expected_revision,
            Patient.cr_number == data.expected_cr_number
        ).values(
            name=data.name.strip(), cr_number=data.cr_number.strip(),
            revision=Patient.revision + 1
        ))
        if changed.rowcount != 1:
            s.rollback()
            raise HTTPException(409, "Patient changed concurrently; reload")
        s.flush()
        s.refresh(record)
        audit(s, u, "correct_patient_identity", "patient", record.id,
              record.id, old, as_dict(record), data.reason)
        s.commit()
    except IntegrityError:
        s.rollback()
        raise HTTPException(409, "CR number belongs to another patient")
    return {"id":record.id, "revision":record.revision,
            "cr_number":record.cr_number, "name":record.name,
            "study_id":record.study_id}


def exact_registry_match(identifier: str, s: Session) -> Patient:
    """Never route a write to the first partial/ambiguous name match."""
    value = identifier.strip()
    if len(value) < 2 or len(value) > 100:
        raise HTTPException(422, "Enter an exact patient name, CR number or study ID")
    lower = value.casefold()
    code = normalized_screening_code(value) or value
    matches = s.scalars(select(Patient).where(active_patient_filter(),or_(
        func.lower(Patient.name) == lower,
        func.lower(Patient.cr_number) == lower,
        func.lower(Patient.study_id) == lower,
        Patient.id.in_(select(TrialSubject.patient_id).where(func.lower(TrialSubject.screening_code)==code.casefold()))
    )).limit(2)).all()
    if not matches:
        raise HTTPException(404, "No exact patient match; search the registry")
    if len(matches) > 1:
        raise HTTPException(409, "Ambiguous patient name; supply CR number or study ID")
    return matches[0]


class RegistryArchiveInput(BaseModel):
    expected_revision: int = Field(ge=1)
    expected_cr_number: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=8, max_length=500)
    confirm_archive: bool = False


@router.post("/patients/{patient_id}/archive")
def archive_registry_patient(patient_id: str, data: RegistryArchiveInput,
                             u: AuthContext = Depends(current),
                             s: Session = Depends(db)):
    """Remove a never-screened record from the active workspace, retaining audit.

    No hard deletion, renamed identifiers, hidden allocation or schema migration.
    Locks the row and validates both expected identity and revision.
    """
    if u.role not in {"admin", "pi"} and not u.pi_authorized:
        raise HTTPException(403, "PI or administrator permission required")
    if not data.confirm_archive:
        raise HTTPException(422, "Explicit archive confirmation required")
    record=s.scalar(select(Patient).where(Patient.id==patient_id).with_for_update())
    if not record:
        raise HTTPException(404, "Registry record not found")
    if (record.cr_number != data.expected_cr_number
            or record.revision != data.expected_revision):
        raise HTTPException(409, "Record identity or revision changed; reload")
    if patient_archived(s,patient_id):
        raise HTTPException(409, "Record already archived")
    from .trial_models import TrialSubject
    if record.study_id is not None or s.scalar(select(TrialSubject.id).where(
            TrialSubject.patient_id==patient_id).limit(1)) is not None:
        raise HTTPException(409, "Screened/enrolled trial records cannot be archived")
    audit(s,u,ARCHIVE_ACTION,"patient",patient_id,patient_id,
          {"revision":record.revision},
          {"archived":True},
          data.reason)
    s.commit()
    return {"patient_id":patient_id,"archived":True,
            "visible_in_active_registry":False,
            "audit_preserved":True}


class RegistryEntryByIdentifier(EntryIn):
    identifier: str = Field(min_length=2, max_length=100)


@router.post("/patient-entry")
def enter_registry_event(data: RegistryEntryByIdentifier,
                         u: AuthContext = Depends(current),
                         s: Session = Depends(db)):
    # Check permission before any patient identity lookup.
    permission(u, data.kind)
    target = exact_registry_match(data.identifier, s)
    result = new_entry(target.id, EntryIn.model_validate(
        data.model_dump(exclude={"identifier"})), u=u, s=s)
    return {"patient_id":target.id, "cr_number":target.cr_number,
            "study_id":target.study_id, "entry":result}


@router.put("/registry-entries/{entry_id}")
def correct_registry_event(entry_id: str, data: EntryEdit,
                           u: AuthContext = Depends(current),
                           s: Session = Depends(db)):
    return edit_entry(entry_id, data, u=u, s=s)


class CRFDraftByIdentifier(CRFDraftInput):
    identifier: str = Field(min_length=2, max_length=100)
    section: str


def exact_trial_subject(identifier: str, u: AuthContext, s: Session):
    # Study IDs, CR numbers and names resolve against the SAME trial + registry.
    candidates = find_subjects(q=identifier.strip(), limit=50,
                               before_id=None, u=u, s=s)
    key = identifier.strip().casefold()
    screening_key = normalized_screening_code(identifier)
    exact = [candidate for candidate in candidates if any(
        isinstance(candidate.get(field), str)
        and (candidate[field].casefold() == key or (field=='screening_code' and screening_key and candidate[field].casefold()==screening_key.casefold()))
        for field in ("study_code", "screening_code", "cr_number", "name")
    )]
    if not exact:
        raise HTTPException(404, "No exact trial subject match")
    if len(exact) != 1:
        raise HTTPException(409, "Ambiguous trial subject; use the study ID or CR number")
    return exact[0]


@router.put("/crf-draft-by-identifier")
def save_crf_draft_by_identifier(data: CRFDraftByIdentifier,
                                  u: AuthContext = Depends(current),
                                  s: Session = Depends(db)):
    target = exact_trial_subject(data.identifier, u, s)
    result = save_draft(target["id"], data.section,
        CRFDraftInput.model_validate(data.model_dump(
            exclude={"identifier", "section"})), u=u, s=s)
    return {"subject_id":target["id"],
            "study_code":target.get("study_code"),
            "draft":result}
