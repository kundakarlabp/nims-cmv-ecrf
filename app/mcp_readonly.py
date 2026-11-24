"""Read-only MCP views of existing OCI operations and CMV trial workflow.

Purpose-built status queries only: no SQL proxy, command runner, token/secret
access, allocation ciphertext, dose, pharmacy order or patient narrative.
"""
from datetime import datetime, timezone
import os
from pathlib import Path
import re

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError

from . import assistant_api
from . import main
from . import trial_api
from .clinical_gate import backup_fresh, restore_verified, startup_deficiencies
from .operations import SHA, read_host_status
from .trial_models import (
    DrugAuthorization, DrugDispense, RandomizationSlot, TrialEligibility,
    TrialSubject,
)

UTC = timezone.utc
DRIVE_REF = re.compile(
    r"^gdrive:1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM:clinical-"
    r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}[.]tar$"
)


def _operator(u):
    """The owner's PI/admin authorization is required for host diagnostics."""
    if u.role not in {"admin", "pi"} and not u.pi_authorized:
        raise HTTPException(403, "PI or administrator permission required")


def _receipt_kind(variable):
    """Only disclose a verified receipt's backend class, not paths or digests."""
    value = os.environ.get(variable, "")
    try:
        path = Path(value)
        if not value or not path.is_absolute() or not path.is_file():
            return "none"
        parts = path.read_text(encoding="utf-8").strip().split()
        if len(parts) != 3:
            return "unrecognized"
        ref = parts[2]
        if DRIVE_REF.fullmatch(ref):
            return "google_drive"
        if ref.startswith("ecrfcrypt:"):
            return "rclone_crypt"
        if re.fullmatch(r"github-(?:artifact|release):[0-9:]+", ref):
            return "legacy_github"
        return "unrecognized"
    except (OSError, ValueError, UnicodeError):
        return "unavailable"


def _host_snapshot():
    status = read_host_status()
    return status if isinstance(status, dict) else {"available": False, "fresh": False}


def deployment_status(u):
    _operator(u)
    host = _host_snapshot()
    running = os.getenv("APP_COMMIT", "")
    running = running if SHA.fullmatch(running) else None
    deployed = host.get("deployed_commit") if host.get("fresh") else None
    approved = host.get("approved_release_commit") if host.get("fresh") else None
    verified = bool(running and deployed and approved
                    and running == deployed == approved)
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "host_report_available": host.get("available") is True,
        "host_report_fresh": host.get("fresh") is True,
        "running_application_commit": running,
        "host_deployed_commit": deployed,
        "approved_release_commit": approved,
        "release_reconciliation": "verified" if verified else "unverified",
        "deploy_timer": host.get("timer_active", "unknown") if host.get("fresh") else "unknown",
        "last_deploy_result": host.get("last_deploy_result", "unknown") if host.get("fresh") else "unknown",
        "last_update_attempt": host.get("last_update_attempt", "unknown") if host.get("fresh") else "unknown",
        "host_command_execution": False,
    }


def backup_status(u):
    _operator(u)
    host = _host_snapshot()
    active = bool(main.CLINICAL_MODE)
    fresh = bool(active and backup_fresh())
    restored = bool(active and restore_verified())
    backup_kind = _receipt_kind("CLINICAL_BACKUP_RECEIPT_PATH")
    restore_kind = _receipt_kind("CLINICAL_RESTORE_RECEIPT_PATH")
    host_fresh = host.get("fresh") is True
    drive_current = bool(fresh and backup_kind == "google_drive")
    drive_configured = (host.get("google_drive_backup_configuration_present")
                        if host_fresh else None)
    direct_verified = (host.get("google_drive_direct_receipt_verified")
                       if host_fresh else None)
    downloaded_restore = (host.get("google_drive_downloaded_restore_verified")
                          if host_fresh else None)
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "clinical_mode": active,
        "offsite_backup_fresh_8h": fresh,
        "isolated_restore_proof_current_30d": restored,
        "backup_receipt_backend": backup_kind,
        "restore_receipt_backend": restore_kind,
        "google_drive_receipt_current": drive_current,
        "google_drive_transfer_mode": ("oci_direct" if drive_configured is True and direct_verified is True else
                                       "connector_acknowledged" if drive_current else
                                       "not_ready"),
        "oci_direct_receipt_for_latest_bundle": direct_verified,
        "drive_downloaded_isolated_restore_for_latest_bundle": downloaded_restore,
        "host_report_fresh": host_fresh,
        "google_drive_configuration_present": drive_configured,
        "google_drive_receipt_present_on_host": host.get("google_drive_backup_receipt_present")
            if host_fresh else None,
        "external_google_drive_listing_checked": False,
        "note": ("Direct mode requires a matching OCI-generated Drive receipt. "
                 "The downloaded-archive restore proof is a separate disposable "
                 "database test with the OCI-held recovery key; this tool does not "
                 "list Google Drive or prove owner-held SSH-key recovery."),
    }



def restore_verification(u):
    """Report the existing proof only; never simulate an actual new restore."""
    _operator(u)
    clinical = bool(main.CLINICAL_MODE)
    valid = bool(clinical and restore_verified())
    host = _host_snapshot()
    offsite = (host.get("google_drive_downloaded_restore_verified")
               if host.get("fresh") is True else None)
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "clinical_mode": clinical,
        "isolated_restore_proof_current_30d": valid,
        "restore_receipt_backend": _receipt_kind("CLINICAL_RESTORE_RECEIPT_PATH"),
        "verification_scope": "existing_disposable_database_restore_proof",
        "drive_downloaded_archive_isolated_restore_verified": offsite,
        "downloaded_restore_scope": "OCI-held-key_disposable_database_only",
        "owner_ssh_key_independent_recovery_tested": False,
        "new_restore_performed_by_this_tool": False,
        "full_offsite_disaster_recovery_tested_by_this_tool": False,
    }

def _fresh_start(s):
    if not main.team_workspace():
        return True
    return bool(s.scalar(select(main.Audit.id).where(
        main.Audit.action == "owner_fresh_start_reset").limit(1)))


def clinical_write_readiness(u, s):
    _operator(u)
    active = bool(main.CLINICAL_MODE)
    fresh = bool(active and backup_fresh())
    restored = bool(active and restore_verified())
    prepared = bool(active and _fresh_start(s))
    database = "reachable"
    try:
        s.execute(select(1)).scalar()
    except SQLAlchemyError:
        database = "unavailable"
    # Match /readyz and the actual clinical write guards; no patient mutation.
    ready = bool(active and fresh and restored and prepared and database == "reachable")
    issues = []
    if not active:
        issues.append("clinical_mode_not_active")
    if active and not fresh:
        issues.append("encrypted_offsite_backup_not_verified")
    if active and not restored:
        issues.append("recent_isolated_restore_not_verified")
    if active and not prepared:
        issues.append("clinical_fresh_start_not_verified")
    if database != "reachable":
        issues.append("database_unavailable")
    # Startup configuration checks are separate from the request-time gate.
    config_issues = startup_deficiencies() if active else []
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "clinical_write_ready": ready,
        "clinical_mode": active,
        "database": database,
        "offsite_backup_fresh": fresh,
        "isolated_restore_proof_current": restored,
        "fresh_start_complete": prepared if active else None,
        "blocking_reasons": issues,
        "configuration_deficiencies": sorted(set(config_issues)),
        "check_type": "read_only_preflight_no_patient_write",
        "user_specific_write_scope": "not_evaluated",
    }


def failure_diagnostics(u):
    _operator(u)
    host = _host_snapshot()
    b = backup_status(u)
    codes = []
    if not host.get("fresh"):
        codes.append("host_status_missing_or_stale")
    else:
        if host.get("last_update_attempt") == "failed":
            codes.append("last_update_attempt_failed")
        if host.get("last_deploy_result") not in {"success", "unknown"}:
            codes.append("deploy_service_not_successful")
        if host.get("clinical_transition") == "maintenance_failed":
            codes.append("clinical_maintenance_failed")
        if host.get("timer_active") not in {"active", "activating"}:
            codes.append("auto_deploy_timer_not_active")
        if (host.get("google_drive_backup_configuration_present") is False and
                not b["google_drive_receipt_current"]):
            codes.append("google_drive_not_configured_on_host")
    if b["clinical_mode"]:
        if not b["offsite_backup_fresh_8h"]:
            codes.append("clinical_backup_receipt_not_fresh")
        if not b["isolated_restore_proof_current_30d"]:
            codes.append("clinical_restore_receipt_not_current")
    return {
        "checked_at": datetime.now(UTC).isoformat(),
        "codes": sorted(set(codes)),
        "host_report_fresh": host.get("fresh") is True,
        "host_transition": host.get("clinical_transition", "unknown") if host.get("fresh") else "unknown",
        "host_failed_step": host.get("clinical_failed_step", "unknown") if host.get("fresh") else "unknown",
        "raw_logs_available": False,
        "arbitrary_commands_available": False,
    }


def trial_workflow_status(identifier, u, s):
    # Match existing trial pharmacy visibility; do not expose allocation data.
    trial_api.role(u, trial_api.PHARMACISTS |
                   {"pi", "consultant", "scientist", "nurse", "monitor"})
    candidate = assistant_api.exact_trial_subject(identifier, u, s)
    subject = trial_api.find_subject(s, candidate["id"])
    eligible = s.get(TrialEligibility, subject.id)
    is_eligible = eligible.baseline.get("is_eligible") if eligible and isinstance(eligible.baseline, dict) else None
    eligibility_status = ("not_reviewed" if not eligible else
                          "eligible" if is_eligible is True else
                          "ineligible" if is_eligible is False else "undetermined")
    # Select only a timestamp. Never retrieve encrypted_arm, position, stratum,
    # allocation code, allocation reference or an unblinded pharmacy order.
    assigned_at = s.scalar(select(RandomizationSlot.assigned_at).where(
        RandomizationSlot.subject_id == subject.id).limit(1))
    randomization_status = ("completed" if assigned_at is not None else
                            "pending" if subject.status == "enrolled" else "not_applicable")
    authorizations = s.scalar(select(func.count(DrugAuthorization.id)).where(
        DrugAuthorization.subject_id == subject.id)) or 0
    dispenses = s.scalar(select(func.count(DrugDispense.id)).where(
        DrugDispense.subject_id == subject.id)) or 0
    pharmacy_status = ("dispensed" if dispenses else
                       "authorized_not_dispensed" if authorizations else "not_authorized")
    return {
        "subject_id": subject.id,
        "study_code": subject.study_code,
        "screening_code": subject.screening_code,
        "recruitment_disposition": trial_api.screening_disposition(subject, eligible),
        "enrollment": {
            "status": subject.status,
            "completed": subject.enrolled_on is not None,
            "enrolled_on": subject.enrolled_on,
        },
        "eligibility": {
            "status": eligibility_status,
            "reviewed_on": eligible.reviewed_on if eligible else None,
        },
        "randomization": {"status": randomization_status},
        "pharmacy": {
            "status": pharmacy_status,
            "authorization_present": bool(authorizations),
            "dispensing_record_present": bool(dispenses),
        },
        "scope": "status_only_no_allocation_or_dosing_details",
        "note": "Status does not authorize enrollment, randomization, prescribing or dispensing.",
    }
