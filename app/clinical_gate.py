"""Fail-closed clinical-release checks, independent of the staging database.

These machine-verifiable checks do not replace signed NIMS governance, IEC,
statistician custody or human UAT. Never interpret a file or flag alone as
permission to handle identifiable patient records.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import hashlib
import os
import re
import json

UTC=timezone.utc
STAMP_RE=re.compile(r"^[0-9]{8}T[0-9]{6}Z$")
HEX_RE=re.compile(r"^[0-9a-f]{64}$")

def _receipt(path:str, max_age:timedelta, at:datetime, expected_remote:bool):
    try:
        f=Path(path)
        if not f.is_absolute() or not f.is_file():return False
        fields=f.read_text(encoding="utf-8").strip().split()
        if len(fields)!=3:return False
        stamp,digest,reference=fields
        if not STAMP_RE.fullmatch(stamp) or not HEX_RE.fullmatch(digest):return False
        if expected_remote and not (reference.startswith("ecrfcrypt:") or
            re.fullmatch(r'github-artifact:1455709378:[1-9][0-9]*',reference) or
            re.fullmatch(r'github-release:1455709378:[1-9][0-9]*:[1-9][0-9]*',reference) or
            re.fullmatch(r'gdrive:1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM:clinical-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}[.]tar',reference)):return False
        event=datetime.strptime(stamp,"%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return timedelta(0)<=at-event<=max_age
    except (OSError,ValueError,UnicodeError):
        return False

def backup_fresh(env=None,at=None):
    env=os.environ if env is None else env
    at=datetime.now(UTC) if at is None else at
    return _receipt(env.get("CLINICAL_BACKUP_RECEIPT_PATH",""),
                    timedelta(hours=8),at,True)

def restore_verified(env=None,at=None):
    env=os.environ if env is None else env
    at=datetime.now(UTC) if at is None else at
    return _receipt(env.get("CLINICAL_RESTORE_RECEIPT_PATH",""),
                    timedelta(days=30),at,True)

def owner_authorized(env):
    """User's explicit activation instruction, never an institutional signature.

    A reviewed deployment supplies its exact document hash and HTTPS host.
    This path replaces placeholder paper flags, not technical protections.
    """
    try:
        path=Path(env.get('CLINICAL_OWNER_AUTHORIZATION_PATH',''))
        if not path.is_absolute() or not path.is_file():return False
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=env.get('CLINICAL_GOLIVE_SHA256'):return False
        data=json.loads(raw)
        return (data.get('owner')=='Dr. Kundakarla Bhanu Prasad' and
                data.get('project')=='NIMS CMV ICMR trial' and
                data.get('instruction')=='activate_clinical_data_capture' and
                data.get('site_domain')==env.get('SITE_DOMAIN') and
                data.get('protocol_version')=='5.0' and
                data.get('institutional_approval_claimed') is False)
    except (OSError,ValueError,TypeError):return False

def startup_deficiencies(env=None,at=None):
    """Reason codes only; never put credentials or PHI in errors/logs."""
    env=os.environ if env is None else env
    if env.get("CLINICAL_DATA_ENABLED","false").lower()!="true":return []
    at=datetime.now(UTC) if at is None else at
    issues=[]
    owner_release=owner_authorized(env)
    from .workspace_policy import password_only
    if env.get("MFA_REQUIRED","false").lower()!="true" and not password_only(env):
        issues.append("mandatory_MFA_disabled")
    if env.get("COOKIE_SECURE","true").lower()!="true":issues.append("secure_cookies_disabled")
    if not owner_release and env.get("CLINICAL_INSTITUTIONAL_APPROVAL","")!="verified":
        issues.append("institutional_approval_not_verified")
    if not owner_release and env.get("CLINICAL_UAT_APPROVED","")!="verified":
        issues.append("signed_UAT_not_verified")
    path=env.get("CLINICAL_OWNER_AUTHORIZATION_PATH","") if owner_release else env.get("CLINICAL_GOLIVE_ATTESTATION_PATH","")
    expected=env.get("CLINICAL_GOLIVE_SHA256","")
    try:
        doc=Path(path)
        if not doc.is_absolute() or not doc.is_file() or not HEX_RE.fullmatch(expected) or (
            hashlib.sha256(doc.read_bytes()).hexdigest()!=expected
        ):
            issues.append("signed_release_document_missing_or_changed")
    except (ValueError,OSError):
        issues.append("signed_release_document_missing_or_changed")
    if env.get("DB_HOST","") in ("","localhost") or env.get("DB_NAME")!="nims_cmv_clinical":
        issues.append("dedicated_clinical_database_missing")
    if env.get("DB_USER","") in ("","nims_ecrf","postgres","nims_clinical_owner"):
        issues.append("restricted_clinical_DB_role_missing")
    if env.get("DATABASE_URL","").lower().startswith("sqlite"):
        issues.append("SQLite_not_permitted_for_clinical")
    domain=env.get("SITE_DOMAIN","").strip().lower()
    if not owner_release and (not domain or domain.endswith((".invalid",".test",".localhost")) or any(x in domain for x in (
        "localhost","sslip.io","nip.io","YOUR_OWN_DOMAIN","example.org"
    ))):
        issues.append("institutionally_approved_domain_required")
    if not backup_fresh(env,at):issues.append("encrypted_offsite_backup_not_verified")
    if not restore_verified(env,at):issues.append("recent_isolated_restore_not_verified")
    keyfile=env.get("RANDOMIZATION_FERNET_KEY_FILE","")
    try:
        from cryptography.fernet import Fernet
        key=Path(keyfile).read_bytes().strip() if keyfile else b""
        Fernet(key)  # Validates usable sealed-allocation encryption key.
    except (OSError,TypeError,ValueError):
        issues.append("independent_allocation_key_not_configured")
    return issues

def release_enabled(env=None,at=None):
    env=os.environ if env is None else env
    return env.get("CLINICAL_DATA_ENABLED","false").lower()=="true" and not startup_deficiencies(env,at)

def runtime_startup_deficiencies(env=None,at=None):
    env=os.environ if env is None else env
    issues=startup_deficiencies(env,at)
    # Initial host cutover independently requires fresh offsite/restore proof.
    # After a reboot the scoped ciphertext service must remain reachable to
    # repair stale proof; request-time guards continue to freeze clinical writes.
    if env.get('CLINICAL_RECOVERY_SERVICE')=='true' and owner_authorized(env):
        issues=[issue for issue in issues if issue not in {
            'encrypted_offsite_backup_not_verified','recent_isolated_restore_not_verified'}]
    return issues


def metadata_fingerprint(metadata):
    """Stable structural fingerprint for the reviewed, one-time clinical baseline."""
    import json
    structure=[]
    for table in sorted(metadata.tables.values(),key=lambda x:x.name):
        structure.append({"table":table.name,"columns":[
            {"name":column.name,"type":str(column.type),"nullable":column.nullable,
             "primary_key":column.primary_key}
            for column in table.columns
        ]})
    return hashlib.sha256(json.dumps(structure,sort_keys=True,
                    separators=(",",":")).encode("utf-8")).hexdigest()

