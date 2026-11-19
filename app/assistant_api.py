"""Same-origin assistant-workflow adapter; never an unauthenticated ChatGPT relay.

Authenticated users retain existing CRF permissions, clinical write gates, CSRF,
and database audit. This module does NOT accept third-party bearer credentials;
a future private MCP connection must implement scoped user-bound OAuth separately.
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .main import AuthContext, current, db
from .trial_api import subjects as find_subjects, find_subject
from .trial_crf import (
    CRFDraftInput, CRFSubmitIn, CRFEditIn,
    save_draft, submit_crf, edit_crf, list_forms,
)
from .trial_models import TrialCRFEntry

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
                       "submit_confirmed_crf", "correct_confirmed_crf"],
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
