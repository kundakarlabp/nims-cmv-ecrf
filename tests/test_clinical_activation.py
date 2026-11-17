"""Boundary checks: first-use MFA, independent custody, scoped ciphertext I/O."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import jwt
import pyotp
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app,Base,ENGINE,SessionLocal,User,PH,LoginSession,sha
from app.trial_models import RandomizationSlot,RandomizationPlan
from app import backup_channel as channel

@pytest.fixture(autouse=True)
def isolated_accounts():
    Base.metadata.drop_all(ENGINE);Base.metadata.create_all(ENGINE)
    with SessionLocal() as s:
        s.add(User(username='activationpi',display_name='CI investigator',role='admin',pi_authorized=True,
                   password_hash=PH.hash('ActivationTestPassword123!')))
        s.add(User(username='activationcustodian',display_name='CI independent custodian',role='randomization_custodian',
                   password_hash=PH.hash('ActivationTestPassword123!')));s.commit()
    yield
    Base.metadata.drop_all(ENGINE)

def login(c,who='activationpi',otp=None):
    r=c.post('/api/login',json={'username':who,'password':'ActivationTestPassword123!','otp':otp})
    assert r.status_code==200,r.text
    return r,{'X-CSRF-Token':r.json()['csrf_token']}

def test_mandatory_mfa_has_restricted_bootstrap_and_revokes_other_sessions(monkeypatch):
    monkeypatch.setenv('MFA_REQUIRED','true')
    with TestClient(app,base_url='https://testserver') as owner,TestClient(app,base_url='https://testserver') as other:
        r,h=login(owner);login(other)
        assert r.json()['mfa_setup_required'] is True
        assert owner.get('/api/patients').status_code==403
        assert owner.get('/api/trial/staff/accounts').status_code==403
        assert owner.get('/api/me').status_code==200
        setup=owner.post('/api/trial/staff/mfa-setup',headers=h)
        assert setup.status_code==200
        secret=setup.json()['secret']
        confirm=owner.post('/api/trial/staff/mfa-confirm',headers=h,json={'otp':pyotp.TOTP(secret).now()})
        assert confirm.status_code==200
        assert owner.get('/api/me').status_code==401
        assert other.get('/api/me').status_code==401
        assert owner.post('/api/login',json={'username':'activationpi','password':'ActivationTestPassword123!'}).status_code==401
        r,h=login(owner,otp=pyotp.TOTP(secret).now())
        assert r.json()['mfa_setup_required'] is False
        assert owner.get('/api/patients').status_code==200

def test_otp_setup_lockout_cannot_be_reset_by_password_login(monkeypatch):
    monkeypatch.setenv('MFA_REQUIRED','true')
    with TestClient(app,base_url='https://testserver') as owner:
        _,h=login(owner)
        secret=owner.post('/api/trial/staff/mfa-setup',headers=h).json()['secret']
        wrong=next(x for x in ('000000','123456','654321') if not pyotp.TOTP(secret).verify(x,valid_window=1))
        for _ in range(5):
            assert owner.post('/api/trial/staff/mfa-confirm',headers=h,json={'otp':wrong}).status_code==422
        assert owner.post('/api/trial/staff/mfa-confirm',headers=h,json={'otp':pyotp.TOTP(secret).now()}).status_code==429
        assert owner.post('/api/login',json={'username':'activationpi','password':'ActivationTestPassword123!'}).status_code==429

def test_only_independent_custodian_can_generate_once_with_concealed_arms(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('RANDOMIZATION_FERNET_KEY',Fernet.generate_key().decode())
    payload={'statistician_reference':'CI independent appointment',
             'signed_specification_reference':'CI signed specification reference',
             'independent_sequence_attested':True,'block_sizes':[4,6]}
    with TestClient(app,base_url='https://testserver') as pi:
        _,h=login(pi)
        assert pi.get('/api/trial/crf/schema').json()['forms']
        assert pi.post('/api/trial/randomization/sequence/generate-and-lock',headers=h,json=payload).status_code==403
    with TestClient(app,base_url='https://testserver') as custodian:
        _,h=login(custodian,'activationcustodian')
        assert custodian.get('/api/patients').status_code==403
        result=custodian.post('/api/trial/randomization/sequence/generate-and-lock',headers=h,json=payload)
        assert result.status_code==200,result.text
        assert all(n>=344 for n in result.json()['stratum_capacities'].values())
        assert 'entries' not in result.json() and 'arm' not in result.json()
        assert custodian.post('/api/trial/randomization/sequence/generate-and-lock',headers=h,json=payload).status_code==409
        with SessionLocal() as s:
            first=s.scalar(select(RandomizationSlot))
            assert first.encrypted_arm not in {'450','900'}
            assert s.scalar(select(RandomizationPlan)).locked_by==s.scalar(select(User).where(User.username=='activationcustodian')).id

def signed_workflow(monkeypatch,**overrides):
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    monkeypatch.setattr(channel,'key_client',lambda:SimpleNamespace(
        get_signing_key_from_jwt=lambda token:SimpleNamespace(key=key.public_key())))
    now=datetime.now(timezone.utc)
    claims={'iss':channel.ISSUER,'aud':channel.AUDIENCE,'exp':now+timedelta(minutes=5),
        'iat':now,'nbf':now,'jti':'ci-test-jti','sub':'repo:'+channel.REPO+':ref:refs/heads/main',
        'repository':channel.REPO,'repository_id':'1455709378','repository_owner_id':'213684388',
        'repository_visibility':'private','workflow_ref':channel.WORKFLOW,
        'ref':'refs/heads/main','event_name':'workflow_run','run_id':'12345',**overrides}
    return {'Authorization':'Bearer '+jwt.encode(claims,key,algorithm='RS256')}

@pytest.mark.parametrize('override',[
    {'repository_id':'1'},{'repository_owner_id':'1'},{'ref':'refs/pull/1/merge'},
    {'workflow_ref':'different.yml'},{'event_name':'pull_request'},{'aud':'wrong'},
    {'repository_visibility':'public'},{'exp':datetime.now(timezone.utc)-timedelta(minutes=1)},
])
def test_ciphertext_channel_rejects_wrong_workflow_identity(monkeypatch,override):
    headers=signed_workflow(monkeypatch,**override)
    with TestClient(app,base_url='https://testserver') as c:
        assert c.get('/api/backup-channel/latest',headers=headers).status_code==401

def test_ciphertext_readback_ack_is_scoped_and_does_not_issue_host_receipt(tmp_path,monkeypatch):
    export=tmp_path/'export';export.mkdir();ack=tmp_path/'ack';ack.mkdir()
    monkeypatch.setenv('CLINICAL_BACKUP_EXPORT_DIR',str(export))
    monkeypatch.setenv('CLINICAL_BACKUP_ACK_DIR',str(ack))
    headers=signed_workflow(monkeypatch)
    ident='20261117T120000Z-abcdef012345';raw=b'CI CIPHERTEXT ONLY'
    digest=hashlib.sha256(raw).hexdigest()
    (export/(ident+'.tar')).write_bytes(raw)
    (export/(ident+'.json')).write_text(json.dumps({'id':ident,'sha256':digest,'size':len(raw),
        'created_at':'2026-11-17T12:00:00+00:00','restore_verified':True}))
    with TestClient(app,base_url='https://testserver') as c:
        assert c.get('/api/backup-channel/latest').status_code==401
        assert c.get('/api/backup-channel/latest',headers=headers).json()['sha256']==digest
        assert c.get('/api/backup-channel/bundles/'+ident,headers=headers).content==raw
        payload={'bundle_id':ident,'sha256':digest,'artifact_id':1234}
        assert c.post('/api/backup-channel/acknowledge',headers=headers,json=dict(payload,sha256='0'*64)).status_code==409
        assert c.post('/api/backup-channel/acknowledge',headers=headers,json=payload).status_code==200
        assert json.loads((ack/(ident+'.json')).read_text())['run_id']=='12345'
        assert not (tmp_path/'last_success').exists()
