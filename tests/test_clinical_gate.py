"""Clinical release conditions must never be satisfied by a UI toggle."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import hashlib
import os
import subprocess
import sys

from app.clinical_gate import backup_fresh, restore_verified, startup_deficiencies

def clinical_env(tmp_path, at):
    signoff=tmp_path/"signed-release.txt"
    signoff.write_text("TEST-ONLY: NOT A REAL INSTITUTIONAL RELEASE\n")
    from cryptography.fernet import Fernet
    key=tmp_path/"sealed.key"
    key.write_bytes(Fernet.generate_key())
    backup=tmp_path/"last_success"
    restore=tmp_path/"last_restore"
    stamp=at.strftime("%Y%m%dT%H%M%SZ")
    entry=f"{stamp} {'0'*64} ecrfcrypt:approved-clinical-backups/test.dump\n"
    backup.write_text(entry)
    restore.write_text(entry)
    return {
        "CLINICAL_DATA_ENABLED":"true",
        "MFA_REQUIRED":"true",
        "COOKIE_SECURE":"true",
        "CLINICAL_INSTITUTIONAL_APPROVAL":"verified",
        "CLINICAL_UAT_APPROVED":"verified",
        "CLINICAL_GOLIVE_ATTESTATION_PATH":str(signoff),
        "CLINICAL_GOLIVE_SHA256":hashlib.sha256(signoff.read_bytes()).hexdigest(),
        "CLINICAL_BACKUP_RECEIPT_PATH":str(backup),
        "CLINICAL_RESTORE_RECEIPT_PATH":str(restore),
        "RANDOMIZATION_FERNET_KEY_FILE":str(key),
        "DB_HOST":"db","DB_NAME":"nims_cmv_clinical",
        "DB_USER":"nims_clinical_app",
        "SITE_DOMAIN":"trial-edc.nims.example.in",
        "DATABASE_URL":"",
    }

def test_golive_requires_every_release_evidence(tmp_path):
    at=datetime(2026,11,16,12,0,tzinfo=timezone.utc)
    e=clinical_env(tmp_path,at)
    assert startup_deficiencies(e,at)==[]
    changes={
        "MFA_REQUIRED":"false",
        "COOKIE_SECURE":"false",
        "CLINICAL_INSTITUTIONAL_APPROVAL":"unverified",
        "CLINICAL_UAT_APPROVED":"unverified",
        "CLINICAL_GOLIVE_SHA256":"0"*64,
        "DB_NAME":"nims_ecrf",
        "DB_USER":"nims_clinical_owner",
        "SITE_DOMAIN":"152-70-77-77.sslip.io",
    }
    for key,value in changes.items():
        bad=dict(e,**{key:value})
        assert startup_deficiencies(bad,at),key
    assert startup_deficiencies(dict(e,CLINICAL_DATA_ENABLED="false"),at)==[]

def test_missing_or_stale_backup_pauses_clinical_writes(tmp_path):
    at=datetime(2026,11,16,12,0,tzinfo=timezone.utc)
    e=clinical_env(tmp_path,at)
    assert backup_fresh(e,at) and restore_verified(e,at)
    later=at+timedelta(hours=9)
    assert not backup_fresh(e,later)
    assert restore_verified(e,later)
    assert "encrypted_offsite_backup_not_verified" in startup_deficiencies(e,later)
    assert not restore_verified(e,at+timedelta(days=31))
    Path(e["CLINICAL_BACKUP_RECEIPT_PATH"]).write_text(
        f"{at.strftime('%Y%m%dT%H%M%SZ')} {'0'*64} unencrypted:plain.dump\n")
    assert not backup_fresh(e,at)

def test_unsigned_or_changed_release_document_fails(tmp_path):
    at=datetime(2026,11,16,12,0,tzinfo=timezone.utc)
    e=clinical_env(tmp_path,at)
    Path(e["CLINICAL_GOLIVE_ATTESTATION_PATH"]).write_text("changed after signing")
    assert "signed_release_document_missing_or_changed" in startup_deficiencies(e,at)

def test_clinical_mode_cannot_start_from_staging_defaults(tmp_path):
    env=os.environ.copy()
    env.update({"CLINICAL_DATA_ENABLED":"true","MFA_REQUIRED":"true",
                "DATABASE_URL":"sqlite:///"+str(tmp_path/"unsafe.sqlite3"),
                "CLINICAL_GOLIVE_ATTESTATION_PATH":str(tmp_path/"not-signed")})
    p=subprocess.run([sys.executable,"-c","import app.main"],
                     capture_output=True,text=True,env=env,timeout=15)
    assert p.returncode!=0
    assert "Clinical startup BLOCKED" in p.stderr


def test_placeholder_domain_stays_blocked_even_when_db_setup_defaults_apply(tmp_path):
    from datetime import datetime,timezone
    at=datetime(2026,11,16,12,0,tzinfo=timezone.utc)
    env=clinical_env(tmp_path,at)
    env["SITE_DOMAIN"]="unconfigured.invalid"
    assert "institutionally_approved_domain_required" in startup_deficiencies(env,at)

def test_explicit_owner_activation_keeps_technical_gates_and_does_not_claim_institutional_signature(tmp_path):
    import json
    at=datetime(2026,11,17,12,0,tzinfo=timezone.utc)
    env=clinical_env(tmp_path,at)
    document=Path(__file__).resolve().parents[1]/'ops/clinical-authorization.json'
    raw=document.read_bytes();authorization=json.loads(raw)
    assert authorization['institutional_approval_claimed'] is False
    env.update(CLINICAL_OWNER_AUTHORIZATION_PATH=str(document),
        CLINICAL_GOLIVE_SHA256=hashlib.sha256(raw).hexdigest(),
        CLINICAL_INSTITUTIONAL_APPROVAL='unverified',CLINICAL_UAT_APPROVED='unverified',
        SITE_DOMAIN=authorization['site_domain'])
    assert startup_deficiencies(env,at)==[]
    assert startup_deficiencies(dict(env,MFA_REQUIRED='false'),at)==['mandatory_MFA_disabled']
    assert startup_deficiencies(dict(env,MFA_REQUIRED='false',
        TEAM_WORKSPACE_ENABLED='true',PASSWORD_ONLY_LOGIN='true'),at)==[]
    assert 'dedicated_clinical_database_missing' in startup_deficiencies(dict(env,DB_NAME='nims_ecrf'),at)
    assert startup_deficiencies(dict(env,SITE_DOMAIN='another.sslip.io'),at)
    assert startup_deficiencies(dict(env,CLINICAL_GOLIVE_SHA256='0'*64),at)
    assert not backup_fresh(env,at+timedelta(hours=9))
    from app.clinical_gate import runtime_startup_deficiencies
    later=at+timedelta(days=31)
    assert runtime_startup_deficiencies(env,later)
    recovery=dict(env,CLINICAL_RECOVERY_SERVICE='true')
    assert runtime_startup_deficiencies(recovery,later)==[]
    assert runtime_startup_deficiencies(dict(recovery,MFA_REQUIRED='false'),later)==['mandatory_MFA_disabled']
    assert runtime_startup_deficiencies(dict(recovery,CLINICAL_GOLIVE_SHA256='0'*64),later)

def test_offsite_artifact_receipt_accepts_only_this_private_repository(tmp_path):
    at=datetime(2026,11,17,12,0,tzinfo=timezone.utc)
    env=clinical_env(tmp_path,at)
    backup=Path(env['CLINICAL_BACKUP_RECEIPT_PATH'])
    prefix=at.strftime('%Y%m%dT%H%M%SZ')+' '+('0'*64)+' '
    backup.write_text(prefix+'github-artifact:1455709378:12345\n')
    assert backup_fresh(env,at)
    backup.write_text(prefix+'github-artifact:123:12345\n')
    assert not backup_fresh(env,at)
    backup.write_text(prefix+'github-release:1455709378:91:93\n')
    assert backup_fresh(env,at)
    backup.write_text(prefix+'github-release:123:91:93\n')
    assert not backup_fresh(env,at)

