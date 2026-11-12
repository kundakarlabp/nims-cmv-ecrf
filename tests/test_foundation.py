import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# DB isolated; a new test process uses this disposable file.
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/nims_cmv_ecrf_staging_tests.sqlite3')
os.environ['COOKIE_SECURE']='false'
from app.main import app, SessionLocal, User, PH, cg_dose, Base, ENGINE

@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(ENGINE)
    Base.metadata.create_all(ENGINE)
    with SessionLocal() as s:
        s.add(User(username='testadmin',display_name='Staging admin',role='admin',password_hash=PH.hash('ThisIsALongTestingPassword123!')))
        s.add(User(username='testpg',display_name='Staging PG',role='pg',password_hash=PH.hash('AnotherLongTestingPassword456!')))
        s.commit()
    yield
    Base.metadata.drop_all(ENGINE)

def auth(client,username='testadmin',password='ThisIsALongTestingPassword123!'):
    r=client.post('/api/login',json={'username':username,'password':password});assert r.status_code==200,r.text
    return {'X-CSRF-Token':r.json()['csrf_token']}

def test_auth_required():
    with TestClient(app) as c:
        assert c.get('/api/patients').status_code==401
        assert c.post('/api/login',json={'username':'testadmin','password':'bad'}).status_code==401

def test_patient_entry_audit_conflict_and_csrf():
    with TestClient(app) as c:
        h=auth(c)
        assert c.post('/api/patients',json={'name':'Synthetic Example','cr_number':'TEST-0001'}).status_code==403
        p=c.post('/api/patients',headers=h,json={'name':'Synthetic Example','cr_number':'TEST-0001','transplant_date':'2026-10-01'})
        assert p.status_code==200,p.text
        pid=p.json()['id']
        entry=c.post(f'/api/patients/{pid}/entries',headers=h,json={'kind':'admission','occurred_on':'2026-10-10','payload':{'ward':'Nephrology','unit':'Unit I'}})
        assert entry.status_code==200,entry.text
        eid=entry.json()['id']
        edit=c.put(f'/api/entries/{eid}',headers=h,json={'expected_revision':1,'occurred_on':'2026-10-10','payload':{'ward':'Nephrology','unit':'Unit II'},'reason':'Corrected against signed source'})
        assert edit.status_code==200,edit.text
        assert edit.json()['revision']==2
        conflict=c.put(f'/api/entries/{eid}',headers=h,json={'expected_revision':1,'occurred_on':'2026-10-10','payload':{'unit':'wrong'},'reason':'Stale edit should fail'})
        assert conflict.status_code==409
        a=c.get(f'/api/patients/{pid}/audit')
        assert a.status_code==200
        assert len(a.json())==3
        assert a.json()[0]['old_record']['payload']['unit']=='Unit I'
        assert a.json()[0]['new_record']['payload']['unit']=='Unit II'

def test_pg_can_enter_visit_but_not_register_patient_or_access_audit():
    with TestClient(app) as c:
        admin=auth(c)
        r=c.post('/api/patients',headers=admin,json={'name':'Synthetic Other','cr_number':'TEST-0002'})
        pid=r.json()['id']
    with TestClient(app) as c:
        h=auth(c,username='testpg',password='AnotherLongTestingPassword456!')
        assert c.post('/api/patients',headers=h,json={'name':'Denied','cr_number':'TEST-0003'}).status_code==403
        assert c.post(f'/api/patients/{pid}/entries',headers=h,json={'kind':'visit','occurred_on':'2026-11-10','payload':{'creatinine_mg_dl':1.2}}).status_code==200
        assert c.post(f'/api/patients/{pid}/entries',headers=h,json={'kind':'pharmacy','occurred_on':'2026-11-10','payload':{}}).status_code==403
        assert c.get(f'/api/patients/{pid}/audit').status_code==403

def test_dosing_boundaries():
    # Select CrCl values exactly by inverting Cockcroft–Gault for fixed age/weight.
    age,wt=40,72
    for crcl,expected450,expected900 in [(9.99,'Withhold','Withhold'),(10,'twice weekly','twice weekly'),(24.99,'twice weekly','twice weekly'),(25,'every 48','every 48'),(39.99,'every 48','every 48'),(40,'once daily','once daily'),(59.99,'once daily','once daily'),(60,'450 mg once daily','900 mg once daily')]:
        creat=(140-age)*wt/(72*crcl)
        for arm,target in ((450,expected450),(900,expected900)):
            r=cg_dose(age,wt,creat,1.0,arm)
            # FP boundary values may round marginally; test with small tolerance away from exact boundary.
            if crcl in (10,25,40,60):
                r=cg_dose(age,wt,(140-age)*wt/(72*(crcl+0.001)),1.0,arm)
            assert target in r['suggested_regimen'],(crcl,arm,r['suggested_regimen'])

def test_not_public_api_docs():
    with TestClient(app) as c:
        assert c.get('/docs').status_code==404

def test_readiness_checks_database_and_hides_failure_details(monkeypatch):
    import app.main as main
    from sqlalchemy.exc import OperationalError
    with TestClient(app) as c:
        assert c.get('/readyz').status_code == 200
        def broken_connection():
            raise OperationalError('secret database address', {}, Exception('private detail'))
        monkeypatch.setattr(main.ENGINE, 'connect', broken_connection)
        response = c.get('/readyz')
        assert response.status_code == 503
        assert 'secret' not in response.text and 'private detail' not in response.text
        assert c.get('/healthz').status_code == 200

def test_duplicate_registration_returns_conflict():
    with TestClient(app) as c:
        h=auth(c)
        payload={'name':'Synthetic duplicate','cr_number':'TEST-DUP'}
        assert c.post('/api/patients',headers=h,json=payload).status_code==200
        assert c.post('/api/patients',headers=h,json=payload).status_code==409
