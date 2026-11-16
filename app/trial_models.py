"""Structured CMV study workflow models. Imported before staging metadata creation.

These tables do not replace reviewed CRF schemas, independent randomization,
versioned migrations, or clinical go-live approval.
"""
from datetime import date, datetime
from sqlalchemy import (String, Integer, Date, DateTime, ForeignKey, UniqueConstraint,
                        Float, Text, CheckConstraint, JSON)
from sqlalchemy.orm import Mapped, mapped_column
from .main import Base, now

class TrialSubject(Base):
    __tablename__ = "trial_subjects"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients.id"), nullable=False, unique=True)
    screening_code: Mapped[str] = mapped_column(String(40), unique=True, nullable=True)
    study_code: Mapped[str | None] = mapped_column(String(40), unique=True)
    screening_on: Mapped[date] = mapped_column(Date, nullable=False)
    consent_on: Mapped[date | None] = mapped_column(Date)
    consent_version: Mapped[str | None] = mapped_column(String(60))
    donor_cmv_igg: Mapped[str] = mapped_column(String(12), nullable=False)
    recipient_cmv_igg: Mapped[str] = mapped_column(String(12), nullable=False)
    donor_type: Mapped[str] = mapped_column(String(12), nullable=False)
    ratg_induction: Mapped[bool | None] = mapped_column(nullable=True)
    eligibility_attested: Mapped[bool] = mapped_column(nullable=False, default=False)
    screening_note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(18), nullable=False, default="screened")
    enrolled_on: Mapped[date | None] = mapped_column(Date)
    pcr_anchor_on: Mapped[date | None] = mapped_column(Date)
    pcr_anchor_basis: Mapped[str | None] = mapped_column(String(40))
    protocol_reference: Mapped[str | None] = mapped_column(String(80))
    discontinuation_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class PCRRecord(Base):
    __tablename__ = "trial_pcr_records"
    __table_args__ = (
        UniqueConstraint("subject_id", "scheduled_month", "attempt"),
        CheckConstraint("scheduled_month IN (1,2,3,4,6,9,12)", name="pcr_valid_month"),
        CheckConstraint("attempt > 0", name="pcr_valid_attempt"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"), nullable=False, index=True)
    scheduled_month: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    specimen_code: Mapped[str] = mapped_column(String(90), nullable=False, unique=True)
    target_on: Mapped[date] = mapped_column(Date, nullable=False)
    collected_on: Mapped[date | None] = mapped_column(Date)
    reported_on: Mapped[date | None] = mapped_column(Date)
    lab_accession: Mapped[str | None] = mapped_column(String(100), unique=True)
    assay_platform: Mapped[str | None] = mapped_column(String(120))
    result_kind: Mapped[str | None] = mapped_column(String(40))
    quantitative_iu_ml: Mapped[float | None] = mapped_column(Float)
    lower_limit_iu_ml: Mapped[float | None] = mapped_column(Float)
    qc_status: Mapped[str | None] = mapped_column(String(30))
    repeat_reason: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(25), default="planned", nullable=False)
    result_entered_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class DrugLot(Base):
    __tablename__ = "trial_drug_lots"
    __table_args__ = (
        UniqueConstraint("lot_number", "expiry_on"),
        CheckConstraint("quantity_received >= 0 AND quantity_on_hand >= 0", name="lot_nonnegative"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lot_number: Mapped[str] = mapped_column(String(100), nullable=False)
    expiry_on: Mapped[date] = mapped_column(Date, nullable=False)
    formulation: Mapped[str] = mapped_column(String(80), nullable=False, default="valganciclovir")
    strength_mg: Mapped[int] = mapped_column(Integer, nullable=False, default=450)
    quantity_received: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, nullable=False)
    received_on: Mapped[date] = mapped_column(Date, nullable=False)
    received_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

class DrugAuthorization(Base):
    __tablename__ = "trial_drug_authorizations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"), nullable=False, index=True)
    prescription_ref: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    signed_on: Mapped[date] = mapped_column(Date, nullable=False)
    authorization_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    allocation_reference: Mapped[str] = mapped_column(String(100), nullable=False)
    renal_assessment_ref: Mapped[str] = mapped_column(String(100), nullable=False)
    authorized_dose_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    issued_for: Mapped[str] = mapped_column(String(40), nullable=False, default="CMV prophylaxis")

class DrugDispense(Base):
    __tablename__ = "trial_drug_dispenses"
    __table_args__ = (CheckConstraint("quantity_issued > 0", name="dispense_positive"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"), nullable=False, index=True)
    authorization_id: Mapped[int] = mapped_column(ForeignKey("trial_drug_authorizations.id"), nullable=False)
    lot_id: Mapped[int] = mapped_column(ForeignKey("trial_drug_lots.id"), nullable=False)
    slip_code: Mapped[str] = mapped_column(String(90), unique=True, nullable=False)
    quantity_issued: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_on: Mapped[date] = mapped_column(Date, nullable=False)
    issued_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

class DrugReturn(Base):
    __tablename__ = "trial_drug_returns"
    __table_args__ = (CheckConstraint("quantity_returned > 0", name="return_positive"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dispense_id: Mapped[int] = mapped_column(ForeignKey("trial_drug_dispenses.id"), nullable=False, index=True)
    quantity_returned: Mapped[int] = mapped_column(Integer, nullable=False)
    returned_on: Mapped[date] = mapped_column(Date, nullable=False)
    disposition: Mapped[str] = mapped_column(String(40), nullable=False, default="quarantine")
    recorded_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)

class UserInvitation(Base):
    __tablename__ = "trial_user_invitations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class UserTotp(Base):
    __tablename__ = "trial_user_totp"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    secret: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class LoginThrottle(Base):
    __tablename__ = "trial_login_throttle"
    username: Mapped[str] = mapped_column(String(100), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class StaffAccess(Base):
    """A named staff member's access validity; no plaintext password ever stored."""
    __tablename__ = "trial_staff_access"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    renewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    renewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))

class TrialEligibility(Base):
    """Signed, attributed pre-randomization checklist from protocol v5/CRF v3."""
    __tablename__ = "trial_eligibility"
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"), primary_key=True)
    inclusion: Mapped[dict] = mapped_column(JSON, nullable=False)
    exclusion: Mapped[dict] = mapped_column(JSON, nullable=False)
    baseline: Mapped[dict] = mapped_column(JSON, nullable=False)
    reviewed_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_on: Mapped[date] = mapped_column(Date, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class TrialCRFEntry(Base):
    __tablename__ = "trial_crf_entries"
    __table_args__ = (UniqueConstraint("subject_id","section","occurrence_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"), index=True, nullable=False)
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    occurrence_key: Mapped[str] = mapped_column(String(60), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class TrialCRFDraft(Base):
    __tablename__ = "trial_crf_drafts"
    __table_args__ = (UniqueConstraint("user_id","subject_id","section","occurrence_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"), index=True, nullable=False)
    section: Mapped[str] = mapped_column(String(40), nullable=False)
    occurrence_key: Mapped[str] = mapped_column(String(60), nullable=False)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class TrialCRFReview(Base):
    __tablename__ = "trial_crf_reviews"
    __table_args__ = (UniqueConstraint("entry_id","entry_revision"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("trial_crf_entries.id"), index=True, nullable=False)
    entry_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)

class TrialScreeningMeta(Base):
    """Restricted CRF A metadata; never exposed to blinded monitors or lab/pharmacy."""
    __tablename__ = "trial_screening_meta"
    subject_id: Mapped[int] = mapped_column(ForeignKey("trial_subjects.id"),primary_key=True)
    participant_initials: Mapped[str | None] = mapped_column(String(20))
    age_at_transplant: Mapped[int | None] = mapped_column(Integer)
    sex_at_birth: Mapped[str | None] = mapped_column(String(30))
    donor_relationship: Mapped[str | None] = mapped_column(String(30))
    pis_version: Mapped[str | None] = mapped_column(String(80))
    icf_version: Mapped[str | None] = mapped_column(String(80))
    consent_language: Mapped[str | None] = mapped_column(String(20))
    consent_obtained_by: Mapped[str | None] = mapped_column(String(150))
    signed_consent_source_ref: Mapped[str | None] = mapped_column(String(120))

class RandomizationPlan(Base):
    """Externally prepared, permanently locked sequence metadata."""
    __tablename__="trial_randomization_plans"
    id: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    protocol_version: Mapped[str] = mapped_column(String(40),nullable=False)
    statistician_reference: Mapped[str] = mapped_column(String(160),nullable=False)
    signed_specification_reference: Mapped[str] = mapped_column(String(160),nullable=False)
    sequence_sha256: Mapped[str] = mapped_column(String(64),nullable=False,unique=True)
    block_sizes: Mapped[dict] = mapped_column(JSON,nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False,default=True)
    locked_by: Mapped[str] = mapped_column(ForeignKey("users.id"),nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,default=now)

class RandomizationSlot(Base):
    """Ciphertext of a future allocation; never serialize it in APIs or audits."""
    __tablename__="trial_randomization_slots"
    __table_args__=(
        UniqueConstraint("plan_id","stratum","position"),
        UniqueConstraint("subject_id"),
        UniqueConstraint("allocation_code"),
        CheckConstraint("position>0",name="randomization_positive_position")
    )
    id: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("trial_randomization_plans.id"),nullable=False,index=True)
    stratum: Mapped[str] = mapped_column(String(32),nullable=False,index=True)
    position: Mapped[int] = mapped_column(Integer,nullable=False)
    encrypted_arm: Mapped[str] = mapped_column(Text,nullable=False)
    subject_id: Mapped[int | None] = mapped_column(ForeignKey("trial_subjects.id"),nullable=True)
    allocation_code: Mapped[str | None] = mapped_column(String(100))
    assigned_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signed_source_reference: Mapped[str | None] = mapped_column(String(160))
