"""Disposable OAuth/MCP integration: PKCE, attribution, replay and revocation."""
import base64
import hashlib
from urllib.parse import parse_qs, urlparse
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app, Base, ENGINE, SessionLocal, User, PH, Audit, Entry

ORIGIN = 'https://cmv.example.org'
CALLBACK = 'https://chatgpt.com/connector_platform_oauth_redirect'
VERIFIER = 'v' * 64
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b'=').decode()

@pytest.fixture
def cmv(monkeypatch):
    from app.oauth_models import OAuthBase
    monkeypatch.setenv('MCP_PUBLIC_ORIGIN', ORIGIN)
    OAuthBase.metadata.drop_all(ENGINE)
    Base.metadata.drop_all(ENGINE)
    Base.metadata.create_all(ENGINE)
    OAuthBase.metadata.create_all(ENGINE)
    with SessionLocal() as s:
        u = User(username='mcptest', display_name='Synthetic MCP user', role='pi',
                 password_hash=PH.hash('SyntheticMcpPassword123!'))
        s.add(u); s.commit(); actor = u.id
    with TestClient(app) as c:
        login = c.post('/api/login', json={'username':'mcptest','password':'SyntheticMcpPassword123!'})
        assert login.status_code == 200
        yield c, {'X-CSRF-Token': login.json()['csrf_token']}, actor
    OAuthBase.metadata.drop_all(ENGINE)
    Base.metadata.drop_all(ENGINE)
    Base.metadata.create_all(ENGINE)

def link(c, csrf, scope='cmv:read cmv:write'):
    client = c.post('/oauth/register', json={'client_name':'ChatGPT', 'redirect_uris':[CALLBACK],
        'token_endpoint_auth_method':'none'}).json()['client_id']
    data = dict(client_id=client, redirect_uri=CALLBACK, response_type='code',
        scope=scope, state='test-state', resource=ORIGIN+'/mcp',
        code_challenge=CHALLENGE, code_challenge_method='S256')
    assert c.get('/oauth/authorize', params=data).status_code == 200
    assert c.post('/oauth/authorize', json=data).status_code == 403
    approved = c.post('/oauth/authorize', headers=csrf, json=data)
    assert approved.status_code == 200, approved.text
    parsed = parse_qs(urlparse(approved.json()['redirect_url']).query)
    assert parsed['state'] == ['test-state'] and parsed['iss'] == [ORIGIN]
    form = dict(grant_type='authorization_code', client_id=client, redirect_uri=CALLBACK,
        code=parsed['code'][0], code_verifier=VERIFIER, resource=ORIGIN+'/mcp')
    return client, form

def rpc(c, token, name, arguments=None):
    return c.post('/mcp', headers={'Authorization':'Bearer '+token}, json={
        'jsonrpc':'2.0', 'id':1, 'method':'tools/call',
        'params':{'name':name,'arguments':arguments or {}}})

def test_complete_pkce_save_audit_readback_refresh_and_revoke(cmv):
    c, csrf, actor = cmv
    client, form = link(c, csrf)
    bad = c.post('/oauth/token', data={**form, 'code_verifier':'x'*64})
    assert bad.status_code == 400
    exchanged = c.post('/oauth/token', data=form)
    assert exchanged.status_code == 200, exchanged.text
    tokens = exchanged.json(); token = tokens['access_token']
    assert c.post('/oauth/token', data=form).status_code == 400
    c.cookies.clear()  # The connection works independently of a browser session.
    assert c.post('/mcp', json={'jsonrpc':'2.0','id':1,'method':'tools/list'}).status_code == 401
    saved = rpc(c, token, 'register_patient', {'data':{'name':'Synthetic MCP participant',
        'cr_number':'TEST-MCP-001'}, 'idempotency_key':'synthetic-registration-001', 'confirm':True})
    assert saved.status_code == 200, saved.text
    assert not saved.json()['result'].get('isError'), saved.text
    pid = saved.json()['result']['structuredContent']['saved']['id']
    repeated = rpc(c, token, 'register_patient', {'data':{'name':'Synthetic MCP participant',
        'cr_number':'TEST-MCP-001'}, 'idempotency_key':'synthetic-registration-001', 'confirm':True})
    assert repeated.json()['result']['structuredContent']['saved']['id'] == pid
    found = rpc(c, token, 'search_patient', {'query':'TEST-MCP-001'})
    assert pid in found.text
    assert isinstance(found.json()['result']['structuredContent'],dict)
    assert found.json()['result']['structuredContent']['items'][0]['id']==pid
    event = rpc(c, token, 'create_registry_entry', {'data':{'identifier':'TEST-MCP-001',
        'kind':'visit','occurred_on':'2026-11-01','payload':{'note':'Synthetic test only'}},
        'idempotency_key':'synthetic-entry-001','confirm':True})
    assert not event.json()['result'].get('isError'), event.text
    with SessionLocal() as s:
        entry = s.scalar(select(Entry).where(Entry.patient_id==pid))
        assert entry.created_by == actor
        assert s.scalar(select(Audit.id).where(Audit.actor_id==actor, Audit.patient_id==pid))
    login=c.post('/api/login',json={'username':'mcptest','password':'SyntheticMcpPassword123!'})
    assert login.status_code==200
    dashboard=c.get('/api/patients/'+pid)
    assert dashboard.status_code==200 and 'Synthetic test only' in dashboard.text
    refreshed = c.post('/oauth/token', data={'grant_type':'refresh_token','client_id':client,
        'refresh_token':tokens['refresh_token'],'resource':ORIGIN+'/mcp'})
    assert refreshed.status_code == 200, refreshed.text
    renewed = refreshed.json()
    assert rpc(c, renewed['access_token'], 'read_patient', {'patient_id':pid}).status_code == 200
    assert c.post('/oauth/revoke', data={'client_id':client,'token':renewed['refresh_token']}).status_code == 200
    assert rpc(c, token, 'read_patient', {'patient_id':pid}).status_code == 401
    assert rpc(c, renewed['access_token'], 'read_patient', {'patient_id':pid}).status_code == 401

def test_scope_redirect_origin_and_resource_enforcement(cmv):
    c, csrf, _ = cmv
    assert c.post('/oauth/register', json={'redirect_uris':['https://evil.example/callback']}).status_code == 400
    client, form = link(c, csrf, 'cmv:read')
    assert c.post('/oauth/token', data={**form,'resource':'https://evil.example/mcp'}).status_code == 400
    token = c.post('/oauth/token', data=form).json()['access_token']
    headers={'Authorization':'Bearer '+token}
    assert c.post('/mcp',headers={**headers,'Origin':'https://evil.example'},json={}).status_code == 403
    result = rpc(c,token,'register_patient',{'data':{'name':'Synthetic denied','cr_number':'TEST-DENIED'},
        'confirm':True,'idempotency_key':'denied-write-001'})
    assert result.status_code == 403
    with SessionLocal() as s:
        user=s.scalar(select(User).where(User.username=='mcptest')); user.active=False; s.commit()
    assert rpc(c,token,'connection_status').status_code == 401

def test_refresh_replay_revokes_token_family(cmv):
    c, csrf, _=cmv
    client, form=link(c,csrf)
    tokens=c.post('/oauth/token',data=form).json()
    data={'grant_type':'refresh_token','client_id':client,'refresh_token':tokens['refresh_token'],
          'resource':ORIGIN+'/mcp'}
    renewed=c.post('/oauth/token',data=data).json()
    assert c.post('/oauth/token',data=data).status_code==400
    assert rpc(c,renewed['access_token'],'connection_status').status_code==401

def test_discovery_transport_expiry_password_revocation_and_csrf(cmv):
    from datetime import timedelta
    from app.main import now,sha
    from app.oauth_models import OAuthToken
    c,csrf,_=cmv
    meta=c.get('/.well-known/oauth-authorization-server').json()
    assert meta['code_challenge_methods_supported']==['S256']
    assert meta['issuer']==ORIGIN
    assert c.get('/.well-known/oauth-protected-resource').json()['resource']==ORIGIN+'/mcp'
    client,form=link(c,csrf,'cmv:read')
    tokens=c.post('/oauth/token',data=form).json();token=tokens['access_token']
    h={'Authorization':'Bearer '+token}
    init=c.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':1,'method':'initialize',
        'params':{'protocolVersion':'2025-11-25','clientInfo':{'name':'test','version':'1'}}})
    assert init.json()['result']['protocolVersion']=='2025-11-25'
    tools=c.post('/mcp',headers=h,json={'jsonrpc':'2.0','id':2,'method':'tools/list'}).json()['result']['tools']
    assert all(t['annotations']['readOnlyHint'] for t in tools)
    assert c.post('/mcp',headers=h,json={'jsonrpc':'2.0','method':'notifications/initialized'}).status_code==202
    assert c.get('/mcp',headers=h).status_code==405
    unknown=rpc(c,token,'shell',{'command':'anything'})
    assert unknown.json()['error']['code']==-32602
    grants=c.get('/api/oauth/connections').json();gid=grants[0]['id']
    assert c.delete('/api/oauth/connections/'+gid).status_code==403
    with SessionLocal() as s:
        record=s.get(OAuthToken,sha(token));record.expires_at=now()-timedelta(seconds=1);s.commit()
    assert rpc(c,token,'connection_status').status_code==401
    refreshed=c.post('/oauth/token',data={'grant_type':'refresh_token','client_id':client,
        'refresh_token':tokens['refresh_token'],'resource':ORIGIN+'/mcp'}).json()
    with SessionLocal() as s:
        user=s.scalar(select(User).where(User.username=='mcptest'));user.password_hash=PH.hash('ChangedSyntheticPassword123!');s.commit()
    assert rpc(c,refreshed['access_token'],'connection_status').status_code==401

def test_additive_migration_matches_models():
    from pathlib import Path
    from sqlalchemy.schema import CreateTable,CreateIndex
    from sqlalchemy.dialects import postgresql
    from app.oauth_models import OAuthBase
    sql=Path('ops/migrations/20261119_assistant_oauth.sql').read_text()
    normalized=lambda value:'\n'.join(line.rstrip() for line in value.splitlines())
    for table in OAuthBase.metadata.sorted_tables:
        assert normalized(str(CreateTable(table,if_not_exists=True).compile(dialect=postgresql.dialect()))+';') in sql
        for index in table.indexes:
            assert str(CreateIndex(index,if_not_exists=True).compile(dialect=postgresql.dialect()))+';' in sql
    assert 'ALTER TABLE' not in sql and 'DROP ' not in sql


def test_oci_operational_mcp_read_tools_and_freshness(cmv, monkeypatch, tmp_path):
    """Complete read-only OAuth roundtrip; no real records, writes or OCI keys."""
    from datetime import datetime, timedelta, timezone
    from app import mcp_readonly
    from app.main import app
    c, csrf, actor = cmv
    client, form = link(c, csrf, "cmv:read")
    token = c.post("/oauth/token", data=form).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    listing = c.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/list"
    }).json()["result"]["tools"]
    names = {tool["name"] for tool in listing}
    expected = {
        "deployment_status", "backup_status", "restore_verification",
        "failure_diagnostics", "clinical_write_readiness", "trial_workflow_status"
    }
    assert expected <= names
    assert all(tool["annotations"]["readOnlyHint"]
               for tool in listing if tool["name"] in expected)
    assert "register_patient" not in names

    commit = "a" * 40
    monkeypatch.setenv("APP_COMMIT", commit)
    monkeypatch.setattr(mcp_readonly, "read_host_status", lambda: {
        "available": True, "fresh": True, "deployed_commit": commit,
        "approved_release_commit": commit, "timer_active": "active",
        "last_update_attempt": "success", "last_deploy_result": "success",
        "google_drive_backup_configuration_present": True,
        "google_drive_backup_receipt_present": True,
        "clinical_transition": "clinical_active",
    })
    monkeypatch.setattr(mcp_readonly.main, "CLINICAL_MODE", True)
    monkeypatch.setattr(mcp_readonly.main, "team_workspace", lambda: False)
    monkeypatch.setattr(mcp_readonly, "startup_deficiencies", lambda: [])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = "clinical-" + stamp + "-abcdef123456.tar"
    ref = "gdrive:1Mnzme95zuQM5WKuHWtsv2-nzhtPUK_EM:" + filename
    receipt = stamp + " " + ("f" * 64) + " " + ref + "\n"
    backup = tmp_path / "last_success"
    restore = tmp_path / "last_restore"
    backup.write_text(receipt)
    restore.write_text(receipt)
    monkeypatch.setenv("CLINICAL_BACKUP_RECEIPT_PATH", str(backup))
    monkeypatch.setenv("CLINICAL_RESTORE_RECEIPT_PATH", str(restore))

    deploy = rpc(c, token, "deployment_status").json()["result"]["structuredContent"]
    assert deploy["release_reconciliation"] == "verified"
    assert deploy["host_command_execution"] is False
    assert "secret" not in str(deploy).lower()

    state = rpc(c, token, "backup_status").json()["result"]["structuredContent"]
    assert state["offsite_backup_fresh_8h"] is True
    assert state["google_drive_receipt_current"] is True
    assert state["external_google_drive_listing_checked"] is False
    assert state["backup_receipt_backend"] == "google_drive"
    assert str(backup) not in str(state)
    restore_state = rpc(c, token, "restore_verification").json()["result"]["structuredContent"]
    assert restore_state["isolated_restore_proof_current_30d"] is True
    assert restore_state["new_restore_performed_by_this_tool"] is False

    readiness = rpc(c, token, "clinical_write_readiness").json()["result"]["structuredContent"]
    assert readiness["clinical_write_ready"] is True
    assert readiness["check_type"] == "read_only_preflight_no_patient_write"
    assert readiness["blocking_reasons"] == []

    monkeypatch.setattr(mcp_readonly, "read_host_status", lambda: {
        "available": True, "fresh": False,
    })
    backup.write_text((datetime.now(timezone.utc) - timedelta(hours=9)).strftime(
        "%Y%m%dT%H%M%SZ") + " " + ("f" * 64) + " " + ref + "\n")
    diagnostics = rpc(c, token, "failure_diagnostics").json()["result"]["structuredContent"]
    assert "host_status_missing_or_stale" in diagnostics["codes"]
    assert "clinical_backup_receipt_not_fresh" in diagnostics["codes"]
    blocked = rpc(c, token, "clinical_write_readiness").json()["result"]["structuredContent"]
    assert blocked["clinical_write_ready"] is False
    assert "encrypted_offsite_backup_not_verified" in blocked["blocking_reasons"]


def test_full_dashboard_tools_and_encrypted_drive_transfer(cmv, monkeypatch, tmp_path):
    """The connector exposes role-bound workflows and only restored ciphertext."""
    import json
    from app import mcp_backup_transfer, oauth_api
    from fastapi import HTTPException
    from ops.clinical_maintenance import offsite_reference

    c, csrf, _ = cmv
    client, form = link(c, csrf)
    token = c.post("/oauth/token", data=form).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    listing = c.post("/mcp", headers=headers, json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/list"
    }).json()["result"]["tools"]
    by_name = {tool["name"]: tool for tool in listing}
    expected = {
        "dashboard_overview", "action_worklist", "participant_context",
        "registry_dashboard", "registry_review_queue", "patient_audit_history",
        "followup_due", "valganciclovir_dose_preview",
        "participant_timeline", "eligibility_schema", "read_eligibility",
        "read_pcr_schedule", "pcr_worklist", "pharmacy_inventory",
        "participant_pharmacy", "crf_review_queue", "crf_completeness",
        "staff_accounts", "randomization_readiness", "read_allocation",
        "screen_participant", "review_eligibility", "enroll_participant",
        "discontinue_participant", "randomize_participant", "collect_pcr",
        "enter_pcr_result", "verify_pcr", "repeat_pcr", "receive_drug_lot",
        "authorize_study_drug", "dispense_study_drug", "record_drug_return",
        "review_crf", "renew_staff_access", "revoke_staff_access",
        "review_registry_entry",
        "prepare_google_drive_backup_transfer",
        "confirm_google_drive_backup_readback",
    }
    assert expected <= set(by_name)
    assert by_name["dashboard_overview"]["annotations"]["readOnlyHint"] is True
    assert by_name["enroll_participant"]["annotations"]["readOnlyHint"] is False
    assert "change_password" not in by_name and "mfa_setup" not in by_name
    assert "lock_sequence" not in by_name and "generate_sequence" not in by_name

    export = tmp_path / "export"
    ack = tmp_path / "ack"
    export.mkdir(); ack.mkdir()
    bundle_id = "20261120T021500Z-abcdef123456"
    raw = b"ciphertext-only synthetic backup test"
    digest = hashlib.sha256(raw).hexdigest()
    (export / (bundle_id + ".tar")).write_bytes(raw)
    (export / (bundle_id + ".json")).write_text(json.dumps({
        "id": bundle_id, "sha256": digest, "size": len(raw),
        "created_at": "2026-11-20T02:15:00+00:00", "stamp": "20261120T021500Z",
        "restore_verified": True,
    }))
    monkeypatch.setenv("CLINICAL_BACKUP_EXPORT_DIR", str(export))
    monkeypatch.setenv("CLINICAL_BACKUP_ACK_DIR", str(ack))

    real_authorize = oauth_api.authorize_account
    def paused_clinical_gate(request, *args, **kwargs):
        if request.method == "POST":
            raise HTTPException(503, "Synthetic paused clinical write gate")
        return real_authorize(request, *args, **kwargs)
    monkeypatch.setattr(oauth_api, "authorize_account", paused_clinical_gate)

    prepared = rpc(c, token, "prepare_google_drive_backup_transfer", {
        "idempotency_key": "prepare-drive-backup-001", "confirm": True
    }).json()["result"]["structuredContent"]["saved"]
    assert prepared["bundle_id"] == bundle_id
    assert prepared["sha256"] == digest
    assert prepared["contains_plaintext_clinical_data"] is False
    with SessionLocal() as s:
        from app.oauth_models import MCPReceipt
        rows = s.scalars(select(MCPReceipt)).all()
        assert prepared["authorization_header"] not in json.dumps(
            [row.result for row in rows], default=str)
    downloaded = c.get("/api/backup-transfer/" + bundle_id,
                       headers={"Authorization": prepared["authorization_header"]})
    assert downloaded.status_code == 200 and downloaded.content == raw
    assert c.get("/api/backup-transfer/" + bundle_id).status_code == 401

    filename = "clinical-" + bundle_id + ".tar"
    confirmed = rpc(c, token, "confirm_google_drive_backup_readback", {
        "bundle_id": bundle_id, "drive_file_id": "1AbCdEfGhIjKlMnOpQrStUv",
        "drive_file_name": filename, "readback_sha256": digest,
        "idempotency_key": "confirm-drive-backup-001", "confirm": True,
    }).json()["result"]["structuredContent"]["saved"]
    assert confirmed["acknowledged"] is True
    payload = json.loads((ack / (bundle_id + ".json")).read_text())
    assert payload["sha256"] == digest
    assert offsite_reference(payload) == (
        "gdrive:" + mcp_backup_transfer.FOLDER_ID + ":" + filename)

def test_blinded_workflow_status_exact_match_no_allocations_or_doses(cmv):
    """MCP sees workflow milestones but never fetches or returns the sealed arm."""
    from datetime import date, datetime, timezone
    from app.main import Patient
    from app.trial_models import (
        TrialSubject, TrialEligibility, RandomizationPlan, RandomizationSlot,
        DrugAuthorization,
    )
    c, csrf, actor = cmv
    client, form = link(c, csrf, "cmv:read")
    token = c.post("/oauth/token", data=form).json()["access_token"]
    with SessionLocal() as s:
        p = Patient(name="Synthetic status participant",
                    cr_number="TEST-MCP-STATUS-001", created_by=actor)
        s.add(p); s.flush()
        t = TrialSubject(
            patient_id=p.id, screening_code="NCMV-S-00200",
            screening_on=date(2026, 11, 16), status="screened",
            donor_cmv_igg="positive", recipient_cmv_igg="positive",
            donor_type="living", ratg_induction=True,
            consent_on=date(2026, 11, 16), consent_version="Synthetic v5",
            eligibility_attested=True, created_by=actor,
        )
        s.add(t); s.flush()
        t_id = t.id
        s.add(TrialEligibility(
            subject_id=t.id, inclusion={"synthetic": True},
            exclusion={"synthetic": False}, baseline={"is_eligible": True},
            reviewed_by=actor, reviewed_on=date(2026, 11, 16),
        ))
        s.commit()
    before = rpc(c, token, "trial_workflow_status", {
        "identifier": "NCMV-S-00200"
    }).json()["result"]["structuredContent"]
    assert before["eligibility"]["status"] == "eligible"
    assert before["enrollment"]["status"] == "screened"
    assert before["randomization"]["status"] == "not_applicable"
    assert before["pharmacy"]["status"] == "not_authorized"

    with SessionLocal() as s:
        t = s.get(TrialSubject, t_id)
        t.study_code = "NCMV200"
        t.status = "enrolled"
        t.enrolled_on = date(2026, 11, 17)
        p = s.get(Patient, t.patient_id)
        p.study_id = t.study_code
        plan = RandomizationPlan(
            protocol_version="5.0",
            statistician_reference="SYNTHETIC-INTERNAL",
            signed_specification_reference="SYNTHETIC-INTERNAL",
            sequence_sha256="a" * 64, block_sizes={"synthetic": [4]},
            active=True, locked_by=actor,
            locked_at=datetime.now(timezone.utc),
        )
        s.add(plan); s.flush()
        s.add(RandomizationSlot(
            plan_id=plan.id, stratum="synthetic", position=1,
            encrypted_arm="NEVER_EXPOSE_SEALED_ARM_900",
            subject_id=t_id, allocation_code="NEVER_EXPOSE_ALLOCATION_CODE",
            assigned_by=actor, assigned_at=datetime.now(timezone.utc),
            signed_source_reference="INTERNAL_SOURCE",
        ))
        s.add(DrugAuthorization(
            subject_id=t_id,
            prescription_ref="SYNTHETIC-PRESCRIPTION-001",
            signed_on=date(2026, 11, 17), authorization_by=actor,
            allocation_reference="NEVER_EXPOSE_ALLOCATION_CODE",
            renal_assessment_ref="SYNTHETIC-RENAL",
            authorized_dose_instruction="NEVER_EXPOSE_DOSE_900",
        ))
        s.commit()
    outcome = rpc(c, token, "trial_workflow_status", {
        "identifier": "NCMV200"
    })
    assert outcome.status_code == 200
    data = outcome.json()["result"]["structuredContent"]
    assert data["randomization"]["status"] == "completed"
    assert data["enrollment"]["completed"] is True
    assert data["pharmacy"]["status"] == "authorized_not_dispensed"
    assert "NEVER_EXPOSE" not in outcome.text
    assert "encrypted_arm" not in outcome.text
    assert "allocation_code" not in outcome.text
    assert "authorized_dose_instruction" not in outcome.text
    assert "900" not in outcome.text


def test_oci_operations_deny_non_operator_even_with_read_token(cmv):
    from app import mcp_readonly
    from app.main import AuthContext
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        mcp_readonly.deployment_status(AuthContext(
            user_id="synthetic-id", role="pg", name="Synthetic PG",
            csrf_hash="",
        ))
    assert e.value.status_code == 403
