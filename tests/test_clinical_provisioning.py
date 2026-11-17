"""Disposable clinical Postgres schema, restricted-role and signoff-mode smoke test.

This runs ONLY in CI with CLINICAL_BOOTSTRAP_CI=true against the disposable
GitHub Actions PostgreSQL service. All test identifiers/receipts are synthetic.
"""
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]

@pytest.mark.skipif(os.environ.get("CLINICAL_BOOTSTRAP_CI")!="true",
                    reason="Requires dedicated ephemeral PostgreSQL CI service")
def test_empty_clinical_schema_provision_and_controlled_registration(tmp_path):
    import psycopg
    from cryptography.fernet import Fernet

    owner_password="CI-owner-disposable-only!"
    app_password="CI-app-disposable-long-secret-only!"
    with psycopg.connect("postgresql://ci:disposable-ci-only@127.0.0.1:5432/postgres",
                        autocommit=True) as superuser:
        superuser.execute(
            "CREATE ROLE nims_clinical_owner LOGIN CREATEROLE PASSWORD %s",
            (owner_password,))
        superuser.execute("CREATE DATABASE nims_cmv_clinical OWNER nims_clinical_owner")

    owner_url=("postgresql+psycopg://nims_clinical_owner:"+owner_password+
               "@127.0.0.1:5432/nims_cmv_clinical")
    app_url=("postgresql+psycopg://nims_clinical_app:"+app_password+
             "@127.0.0.1:5432/nims_cmv_clinical")
    base=os.environ.copy()
    base.update({
        "PYTHONPATH":str(ROOT),
        "DB_HOST":"127.0.0.1",
        "DB_NAME":"nims_cmv_clinical",
        "DB_USER":"nims_clinical_owner",
        "POSTGRES_PASSWORD":owner_password,
        "CLINICAL_DB_APP_PASSWORD":app_password,
        "DATABASE_URL":owner_url,
        "CLINICAL_SCHEMA_BOOTSTRAP":"true",
        "CLINICAL_DATA_ENABLED":"false",
    })
    command=[sys.executable,"-m","ops.clinical_schema_bootstrap"]
    initialized=subprocess.run(command,env=base,cwd=ROOT,
                      capture_output=True,text=True,timeout=40)
    assert initialized.returncode==0,initialized.stderr[-3500:]
    assert "Structural fingerprint" in initialized.stdout
    duplicate=subprocess.run(command,env=base,cwd=ROOT,
                     capture_output=True,text=True,timeout=30)
    assert duplicate.returncode!=0
    assert "already contains tables" in (duplicate.stderr+duplicate.stdout)

    with psycopg.connect(app_url.replace("postgresql+psycopg://","postgresql://")) as appdb:
        assert appdb.execute(
            "SELECT has_schema_privilege(current_user,'public','CREATE')"
        ).fetchone()[0] is False
        baseline=appdb.execute(
            "SELECT fingerprint FROM clinical_schema_baseline WHERE revision='initial-2026-11'"
        ).fetchone()[0]
        assert len(baseline)==64
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            appdb.execute("DELETE FROM audit_events")
        appdb.rollback()

    signed=tmp_path/"ci-non-institutional-signoff.txt"
    signed.write_text("CI ONLY. NOT A REAL NIMS RELEASE DOCUMENT.\n")
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup=tmp_path/"last_success"
    restored=tmp_path/"last_restore"
    for receipt in (backup,restored):
        receipt.write_text(stamp+" "+("0"*64)+" ecrfcrypt:ci-fake/no-patient-data.dump\n")
    key=tmp_path/"fernet.key"
    key.write_bytes(Fernet.generate_key())
    clinical=dict(base)
    clinical.update({
        "DB_USER":"nims_clinical_app",
        "POSTGRES_PASSWORD":app_password,
        "DATABASE_URL":app_url,
        "CLINICAL_SCHEMA_BOOTSTRAP":"false",
        "CLINICAL_DATA_ENABLED":"true",
        "MFA_REQUIRED":"true",
        "COOKIE_SECURE":"true",
        "CLINICAL_INSTITUTIONAL_APPROVAL":"verified",
        "CLINICAL_UAT_APPROVED":"verified",
        "CLINICAL_GOLIVE_ATTESTATION_PATH":str(signed),
        "CLINICAL_GOLIVE_SHA256":hashlib.sha256(signed.read_bytes()).hexdigest(),
        "CLINICAL_BACKUP_RECEIPT_PATH":str(backup),
        "CLINICAL_RESTORE_RECEIPT_PATH":str(restored),
        "RANDOMIZATION_FERNET_KEY_FILE":str(key),
        "SITE_DOMAIN":"ci-trial.nims.testbed.in",
    })
    snippet=r'''
from app.main import app,User,SessionLocal,PH,now
from app.trial_models import UserTotp,StaffAccess
from fastapi.testclient import TestClient
from datetime import timedelta
import pyotp
with SessionLocal() as s:
    otp_secret=pyotp.random_base32()
    u=User(username="clinicalcitest",display_name="CI synthetic clinical-mode user",
           role="scientist",password_hash=PH.hash("CIClinicalTestPassword123!"))
    s.add(u);s.flush()
    s.add(UserTotp(user_id=u.id,secret=otp_secret,enabled=True,confirmed_at=now()))
    s.add(StaffAccess(user_id=u.id,activated_at=now(),expires_at=now()+timedelta(days=90)))
    s.commit()
with TestClient(app,base_url="https://testserver") as client:
    login=client.post("/api/login",json={
      "username":"clinicalcitest","password":"CIClinicalTestPassword123!",
      "otp":pyotp.TOTP(otp_secret).now()})
    assert login.status_code==200,login.text
    headers={"X-CSRF-Token":login.json()["csrf_token"]}
    mode=client.get("/api/system/mode")
    assert mode.status_code==200,mode.text
    assert mode.json()["mode"]=="clinical"
    assert mode.json()["clinical_registration_enabled"] is True
    result=client.post("/api/patients",headers=headers,json={
      "cr_number":"CI-NOT-REAL-CR","name":"CI TEST RECORD - NOT A PATIENT",
      "transplant_date":"2026-10-01"})
    assert result.status_code==200,result.text
    assert client.get("/api/patients").status_code==200
print("Disposable signed-mode clinical registration smoke test PASS")
'''
    verified=subprocess.run([sys.executable,"-c",snippet],env=clinical,cwd=ROOT,
                     capture_output=True,text=True,timeout=50)
    assert verified.returncode==0,verified.stderr[-3500:]
    assert "smoke test PASS" in verified.stdout
