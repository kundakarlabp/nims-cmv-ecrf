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
    for table in OAuthBase.metadata.sorted_tables:
        assert str(CreateTable(table,if_not_exists=True).compile(dialect=postgresql.dialect()))+';' in sql
        for index in table.indexes:
            assert str(CreateIndex(index,if_not_exists=True).compile(dialect=postgresql.dialect()))+';' in sql
    assert 'ALTER TABLE' not in sql and 'DROP ' not in sql
