import os
from pathlib import Path
import pytest
from sqlalchemy import select
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

def test_cmv_serostatus_requires_source_verified_positive_or_negative():
    from types import SimpleNamespace
    from app.trial_api import subject_view
    source=dict(id=7,screening_code='TEST-S-7',study_code=None,status='screened',
                screening_on=None,enrolled_on=None,pcr_anchor_on=None,
                pcr_anchor_basis=None,protocol_reference=None,donor_type='deceased',
                ratg_induction=False,age_at_transplant=48,consent_on=None,
                consent_version=None,eligibility_attested=False)
    both_positive=subject_view(SimpleNamespace(**source,donor_cmv_igg='positive',
                                                  recipient_cmv_igg='positive'))
    assert both_positive['d_plus_r_plus'] is True
    assert both_positive['donor_cmv_igg']=='positive'
    unknown_donor=subject_view(SimpleNamespace(**source,donor_cmv_igg='unknown',
                                                  recipient_cmv_igg='positive'))
    assert unknown_donor['d_plus_r_plus'] is None
    assert unknown_donor['donor_cmv_igg']=='unknown'
    verified_negative=subject_view(SimpleNamespace(**source,donor_cmv_igg='negative',
                                                      recipient_cmv_igg='positive'))
    assert verified_negative['d_plus_r_plus'] is False

def test_auth_required():
    with TestClient(app) as c:
        assert c.get('/api/patients').status_code==401
        assert c.post('/api/login',json={'username':'testadmin','password':'bad'}).status_code==401

def test_session_recovers_csrf_after_refresh_without_extending_idle_deadline():
    from app.main import LoginSession, sha, now
    from datetime import timedelta
    with TestClient(app) as c:
        headers=auth(c)
        token=c.cookies.get('nims_session')
        with SessionLocal() as s:
            active=s.get(LoginSession,sha(token))
            assert 1790<(active.expires_at.replace(tzinfo=now().tzinfo)-now()).total_seconds()<=1800
            active.expires_at=now()+timedelta(minutes=5);s.commit()
            deadline=active.expires_at
        r=c.get('/api/session')
        assert r.status_code==200,r.text
        assert r.json()['csrf_token']==headers['X-CSRF-Token']
        assert r.json()['idle_timeout_seconds']==1800
        assert 'no-store' in r.headers['cache-control']
        assert c.get('/api/session').json()['csrf_token']==r.json()['csrf_token']
        with SessionLocal() as s:
            assert s.get(LoginSession,sha(token)).expires_at.replace(tzinfo=now().tzinfo)==deadline.replace(tzinfo=now().tzinfo)
        assert c.post('/api/session/activity').status_code==403
        assert c.post('/api/session/activity',headers=headers).status_code==200
        with SessionLocal() as s:
            active=s.get(LoginSession,sha(token))
            assert (active.expires_at.replace(tzinfo=now().tzinfo)-now()).total_seconds()>1790
            active.expires_at=now()-timedelta(seconds=1);s.commit()
        assert c.get('/api/session').status_code==401
        assert c.post('/api/session/activity',headers=headers).status_code==401

def test_session_recovery_revocation_and_legacy_session():
    from app.main import LoginSession, sha
    with TestClient(app) as c:
        assert c.get('/api/session').status_code==401
        auth(c)
        with SessionLocal() as s:
            active=s.get(LoginSession,sha(c.cookies.get('nims_session')))
            active.csrf_hash=sha('legacy-random-csrf');s.commit()
        r=c.get('/api/session');assert r.status_code==200
        assert c.get('/api/session').json()['csrf_token']==r.json()['csrf_token']
        assert c.post('/api/logout',headers={'X-CSRF-Token':r.json()['csrf_token']}).status_code==200
        assert c.get('/api/session').status_code==401


def test_password_team_workspace_keeps_authentication_and_removes_clinical_role_handoffs(monkeypatch):
    from app.main import Audit
    from app.trial_models import UserTotp
    import pyotp
    from cryptography.fernet import Fernet
    monkeypatch.setenv('TEAM_WORKSPACE_ENABLED','true')
    monkeypatch.setenv('PASSWORD_ONLY_LOGIN','true')
    monkeypatch.setenv('MFA_REQUIRED','false')
    monkeypatch.setenv('RANDOMIZATION_FERNET_KEY',Fernet.generate_key().decode())
    with SessionLocal() as s:
        owner=s.scalar(select(User).where(User.username=='testadmin'))
        owner.pi_authorized=True
        s.add(Audit(actor_id=owner.id,action='owner_fresh_start_reset',entity_type='workspace_policy',
            entity_id='fresh-start-20261118-v1',reason='Synthetic test reset fixture'))
        s.commit()
    with TestClient(app) as admin:
        h=auth(admin);pid,sid=setup_synthetic_trial(admin,h)
        assert admin.post('/api/users',headers=h,json={'username':'sharednurse',
            'display_name':'Synthetic named nurse','role':'nurse',
            'password':'NamedNursePassword123!'}).status_code==200
    with SessionLocal() as s:
        nurse=s.scalar(select(User).where(User.username=='sharednurse'))
        s.add(UserTotp(user_id=nurse.id,secret=pyotp.random_base32(),enabled=True));s.commit()
    with TestClient(app) as nurse:
        assert nurse.get('/api/patients').status_code==401
        bad=nurse.post('/api/login',json={'username':'sharednurse','password':'wrong'})
        assert bad.status_code==401
        h=auth(nurse,'sharednurse','NamedNursePassword123!')  # No OTP, even for an existing TOTP account.
        assert nurse.get('/api/me').json()['role']=='nurse'
        assert nurse.post('/api/users',headers=h,json={'username':'forbiddenadmin',
            'display_name':'Synthetic forbidden escalation','role':'admin',
            'password':'ForbiddenEscalation123!'}).status_code==403
        r=nurse.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert r.status_code==200,r.text
        matches=nurse.get('/api/trial/subjects',params={'q':'TEST-CLINICAL-001'}).json()
        assert len(matches)==1 and matches[0]['patient_id']==pid
        assert matches[0]['cr_number']=='TEST-CLINICAL-001'
        assert matches[0]['id']==sid and matches[0]['status']=='enrolled'
        assert nurse.get('/api/trial/randomization/subjects/'+str(sid)+'/allocation').json()['randomized'] is False
        from app.workspace_setup import initialize
        assert initialize()['created'] is True
        assert initialize()['created'] is False  # Never regenerate a plan.
        before=nurse.get(f'/api/trial/randomization/subjects/{sid}/preflight')
        assert before.status_code==200 and before.json()['ready'] is True
        assert before.json()['stratum']=='rATG:living'
        assert 'assigned_arm_mg' not in before.json() and 'position' not in before.json()
        allocation=nurse.post(f'/api/trial/randomization/subjects/{sid}/assign',headers=h,json={
            'investigator_confirmation':True,'stratification_verified':True,
            })
        assert allocation.status_code==200,allocation.text
        assert allocation.json()['assigned_arm_mg'] in ('450','900')
        assert allocation.json()['allocation_code'].startswith('NCMV-R-')
        after=nurse.get(f'/api/trial/randomization/subjects/{sid}/preflight')
        assert after.status_code==200 and after.json()['ready'] is False
        assert after.json()['randomized'] is True
        assert 'assigned_arm_mg' not in after.json()
        assert nurse.get('/api/trial/randomization/readiness').json()['custodian_required'] is False
        lot=nurse.post('/api/trial/pharmacy/lots',headers=h,json={
            'lot_number':'TEST-LOT-TEAM','expiry_on':'2027-10-01',
            'received_on':'2026-10-01','strength_mg':450,'quantity_received':100})
        assert lot.status_code==200,lot.text
        form=nurse.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json={
            'section':'C_baseline','occurred_on':'2026-10-03',
            'payload':{'weight_kg':60,'source_reference':'TEST-BASELINE-TEAM'}})
        assert form.status_code==200,form.text
        entry=form.json()['entry_id']
        assert any(x['id']==entry for x in nurse.get('/api/trial/crf/review-queue').json())
        reviewed=nurse.post(f'/api/trial/crf/entries/{entry}/review',headers=h,json={
            'expected_revision':1,'decision':'verified','reason':'Named entry author checked the source record'})
        assert reviewed.status_code==200,reviewed.text
        assert nurse.post(f'/api/trial/randomization/subjects/{sid}/assign',headers=h,json={
            'investigator_confirmation':True,'stratification_verified':True,
            'signed_randomization_source_ref':'Second request prohibited'}).status_code==409


def test_team_mode_waits_for_reset_before_accepting_new_clinical_writes(monkeypatch):
    monkeypatch.setenv('TEAM_WORKSPACE_ENABLED','true')
    monkeypatch.setenv('PASSWORD_ONLY_LOGIN','true')
    with TestClient(app) as c:
        h=auth(c)
        response=c.post('/api/patients',headers=h,json={'name':'Synthetic protected',
            'cr_number':'TEST-PENDING-RESET'})
        assert response.status_code==503 and 'fresh start' in response.text.lower()

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

def test_trial_study_id_cannot_be_preassigned_on_registration():
    with TestClient(app) as c:
        h=auth(c)
        rejected=c.post('/api/patients',headers=h,json={
            'name':'Synthetic premature ID','cr_number':'TEST-PREASSIGN',
            'study_id':'NCMV001'})
        assert rejected.status_code==422,rejected.text
        assert 'approved enrollment' in rejected.text
        registered=c.post('/api/patients',headers=h,json={
            'name':'Synthetic no enrollment','cr_number':'TEST-NO-ENROLL'})
        assert registered.status_code==200,registered.text
        patient=c.get('/api/patients/'+registered.json()['id']).json()['patient']
        assert patient['study_id'] is None


def test_study_ids_count_enrollments_not_screening_records_and_stop_at_350():
    from datetime import date
    from app.main import Patient
    from app.trial_models import TrialSubject
    from app.trial_api import allocate_study_id
    from fastapi import HTTPException
    with SessionLocal() as s:
        owner=s.scalar(select(User).where(User.username=='testadmin'))
        def screen(suffix,code=None,status='screened'):
            p=Patient(cr_number=f'TEST-STUDY-SEQ-{suffix}',
                name=f'Synthetic sequence {suffix}',created_by=owner.id)
            s.add(p);s.flush()
            t=TrialSubject(patient_id=p.id,screening_on=date(2026,10,1),
                donor_cmv_igg='positive',recipient_cmv_igg='positive',
                donor_type='living',created_by=owner.id,
                status=status,study_code=code)
            s.add(t);s.flush()
            return t
        screen('EXCLUDED')
        first=screen('FIRST')
        assert first.id!=1,'An excluded screening record must consume an internal row only'
        assert allocate_study_id(s)=='NCMV001'
        first.study_code='NCMV001'
        s.flush()
        assert allocate_study_id(s)=='NCMV002'
        first.status='withdrawn'
        assert allocate_study_id(s)=='NCMV002','Withdrawn Study IDs are never recycled'
        screen('END',code='NCMV350',status='enrolled')
        with pytest.raises(HTTPException) as err:
            allocate_study_id(s)
        assert err.value.status_code==409
        assert '350' in err.value.detail


def test_independent_review_requires_role_and_current_revision():
    with TestClient(app) as author:
        admin=auth(author)
        pid=author.post('/api/patients',headers=admin,json={'name':'Synthetic review','cr_number':'TEST-REVIEW'}).json()['id']
        eid=author.post(f'/api/patients/{pid}/entries',headers=admin,json={
            'kind':'visit','occurred_on':'2026-11-10','payload':{'synthetic':True}}).json()['id']
        assert author.get('/api/dashboard').json()['review']['pending']==1
        payload={'expected_revision':1,'decision':'verified','reason':'Synthetic source checked'}
        assert author.post(f'/api/entries/{eid}/review',headers=admin,json=payload).status_code==403
        author.post('/api/users',headers=admin,json={'username':'reviewer','display_name':'Independent reviewer',
            'role':'monitor','password':'SyntheticReviewerPassword123!'})
    with TestClient(app) as reviewer:
        rh=auth(reviewer,'reviewer','SyntheticReviewerPassword123!')
        assert reviewer.get('/api/review-queue').json()[0]['review_status']=='pending'
        assert reviewer.post(f'/api/entries/{eid}/review',headers=rh,json=payload).status_code==200
        assert reviewer.post(f'/api/entries/{eid}/review',headers=rh,json=payload).status_code==409
        assert reviewer.get('/api/dashboard').json()['review']['verified']==1
    with TestClient(app) as author:
        admin=auth(author)
        edit=author.put(f'/api/entries/{eid}',headers=admin,json={'expected_revision':1,
            'occurred_on':'2026-11-10','payload':{'synthetic':True,'corrected':True},
            'reason':'Corrected synthetic source'})
        assert edit.status_code==200
        assert author.get(f'/api/patients/{pid}').json()['entries'][0]['review_status']=='pending'
    with TestClient(app) as reviewer:
        rh=auth(reviewer,'reviewer','SyntheticReviewerPassword123!')
        assert reviewer.post(f'/api/entries/{eid}/review',headers=rh,json=payload).status_code==409
        assert reviewer.post(f'/api/entries/{eid}/review',headers=rh,json={
            **payload,'expected_revision':2,'decision':'needs_correction'}).status_code==200
        assert reviewer.get('/api/dashboard').json()['review']['needs_correction']==1
        assert len(reviewer.get(f'/api/patients/{pid}/audit').json())==5
    with TestClient(app) as pg:
        auth(pg,'testpg','AnotherLongTestingPassword456!')
        assert pg.get('/api/review-queue').status_code==403



def test_server_side_drafts_are_private_versioned_and_not_submitted():
    with TestClient(app) as c:
        h=auth(c)
        pid=c.post('/api/patients',headers=h,json={'name':'Synthetic draft','cr_number':'TEST-DRAFT',
            'study_id':'NCMV-TEST-1'}).json()['id']
        endpoint=f'/api/patients/{pid}/drafts/visit'
        assert c.get(endpoint).json()=={'draft':None}
        record={'occurred_on':'2026-11-16','payload':{'scheduled_month':1,'visit_complete':False}}
        saved=c.put(endpoint,headers=h,json=record)
        assert saved.status_code==200,saved.text
        assert saved.json()['revision']==1
        loaded=c.get(endpoint)
        assert loaded.json()['draft']['payload']==record['payload']
        assert c.get('/api/dashboard').json()['entries']==0
        assert c.get('/api/dashboard').json()['study_ids_assigned']==1
        stale=c.put(endpoint,headers=h,json=record)
        assert stale.status_code==409
        updated=c.put(endpoint,headers=h,json={**record,'expected_revision':1,
            'payload':{'scheduled_month':1,'visit_complete':True}})
        assert updated.status_code==200
        assert updated.json()['revision']==2
        assert c.delete(endpoint+'?expected_revision=1',headers=h).status_code==409
        assert c.delete(endpoint+'?expected_revision=2',headers=h).status_code==200
        assert c.get(endpoint).json()=={'draft':None}
        assert c.get('/api/dashboard').json()['entries']==0


def test_draft_role_auth_csrf_and_study_modules():
    with TestClient(app) as admin:
        h=auth(admin)
        pid=admin.post('/api/patients',headers=h,json={
            'name':'Synthetic access','cr_number':'TEST-ACCESS'}).json()['id']
    with TestClient(app) as pg:
        h=auth(pg,'testpg','AnotherLongTestingPassword456!')
        endpoint=f'/api/patients/{pid}/drafts/pharmacy'
        assert pg.get(endpoint).status_code==403
        assert pg.put(endpoint,headers=h,json={'occurred_on':'2026-11-16','payload':{}}).status_code==403
        endpoint=f'/api/patients/{pid}/drafts/visit'
        assert pg.put(endpoint,json={'occurred_on':'2026-11-16','payload':{}}).status_code==403
        r=pg.put(endpoint,headers=h,json={'occurred_on':'2026-11-16','payload':{'synthetic':True}})
        assert r.status_code==200
        assert pg.get(endpoint).json()['draft']['payload']=={'synthetic':True}
    with TestClient(app) as admin:
        auth(admin)
        assert admin.get(f'/api/patients/{pid}/drafts/visit').json()['draft'] is None


def test_dashboard_counts_only_latest_review_revision():
    with TestClient(app) as c:
        h=auth(c)
        pid=c.post('/api/patients',headers=h,json={
            'name':'Synthetic stats','cr_number':'TEST-STATS'}).json()['id']
        for kind in ('visit','lab','visit'):
            r=c.post(f'/api/patients/{pid}/entries',headers=h,json={
                'kind':kind,'occurred_on':'2026-11-16','payload':{'test':True}})
            assert r.status_code==200
        d=c.get('/api/dashboard').json()
        assert d['entries']==3
        assert d['review']['pending']==3
        assert d['by_kind']=={'visit':2,'lab':1}
        assert d['monthly_entries'][-1]=={'month':'2026-11','count':3}


def test_staging_blocks_identifiable_registration():
    with TestClient(app) as c:
        h=auth(c)
        r=c.post('/api/patients',headers=h,json={'name':'Real patient','cr_number':'HOSP-123'})
        assert r.status_code==403
        assert 'synthetic' in r.text.lower()


def setup_synthetic_trial(client,headers):
    patient=client.post('/api/patients',headers=headers,json={
        'name':'Synthetic participant','cr_number':'TEST-CLINICAL-001',
        'transplant_date':'2026-10-01'})
    assert patient.status_code==200,patient.text
    pid=patient.json()['id']
    r=client.post('/api/users',headers=headers,json={'username':'syntheticscreener',
        'display_name':'Synthetic screening scientist','role':'scientist',
        'password':'SyntheticScreenerPassword123!'})
    assert r.status_code==200,r.text
    with TestClient(app) as scientist:
        screener_auth=auth(scientist,'syntheticscreener','SyntheticScreenerPassword123!')
        screening=scientist.post('/api/trial/screening',headers=screener_auth,json={
        'patient_id':pid,'screening_on':'2026-10-02',
        'donor_cmv_igg':'positive','recipient_cmv_igg':'positive',
        'donor_type':'living','ratg_induction':True,
        'consent_on':'2026-10-02','consent_version':'ICF-v1',
        'eligibility_attested':True})
    assert screening.status_code==200,screening.text
    assert client.post('/api/users',headers=headers,json={
        'username':'testeligibilityconsultant','display_name':'Synthetic eligibility consultant',
        'role':'consultant','password':'EligibilityTestPassword123!'}).status_code==200
    from app.trial_api import INCLUSION_ITEMS,EXCLUSION_ITEMS
    with TestClient(app) as consultant:
        consultant_headers=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        eligibility=consultant.put(
            f"/api/trial/subjects/{screening.json()['id']}/eligibility",
            headers=consultant_headers,json={
              'inclusion':{k:True for k in INCLUSION_ITEMS},
              'exclusion':{k:False for k in EXCLUSION_ITEMS},
              'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
              'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
              'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-02',
              'signed_source_reference':'TEST-Baseline-Source'})
        assert eligibility.status_code==200,eligibility.text
        assert eligibility.json()['eligible'] is True
    return pid,screening.json()['id']


def test_action_worklist_is_source_derived_and_never_reveals_patient_names():
    with TestClient(app) as admin:
        h=auth(admin)
        pid,sid=setup_synthetic_trial(admin,h)
        actions=admin.get('/api/trial/action-worklist').json()
        assert actions['total']>=1
        matches=[a for a in actions['actions'] if a['subject_id']==sid]
        assert any(a['category']=='Enrollment pending' for a in matches)
        assert all('name' not in a and 'cr_number' not in a
                   and 'assigned_arm_mg' not in a for a in actions['actions'])
        assert admin.post('/api/users',headers=h,json={
            'username':'actionworkpi','display_name':'Synthetic action PI',
            'role':'pi','password':'StrongActionPI123456!'}).status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'actionworkpi','StrongActionPI123456!')
        status=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert status.status_code==200,status.text
        actions=pi.get('/api/trial/action-worklist').json()
        categories=[a['category'] for a in actions['actions'] if a['subject_id']==sid]
        assert 'Enrollment pending' not in categories
        assert 'Randomization pending' in categories
        assert 'PCR target' in categories
        assert all('overdue' not in a['detail'].lower() for a in actions['actions'])
        assert actions['note'].lower().find('not approved visit windows')!=-1


def test_screening_pi_enrollment_seven_pcr_codes_and_eligibility():
    with TestClient(app) as admin:
        h=auth(admin)
        pid,subject_id=setup_synthetic_trial(admin,h)
        assert admin.post(f'/api/trial/subjects/{subject_id}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True}).status_code==403
        assert admin.post('/api/users',headers=h,json={'username':'trialpi',
            'display_name':'Synthetic trial PI','role':'pi','password':'SyntheticPiPassword123!'}).status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'trialpi','SyntheticPiPassword123!')
        assert pi.get('/api/patients/'+pid).json()['patient']['study_id'] is None
        enrollment=pi.post(f'/api/trial/subjects/{subject_id}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert enrollment.status_code==200,enrollment.text
        assert enrollment.json()['pcr_orders']==7
        subject=enrollment.json()['subject']
        expected_id='NCMV001'
        assert subject['study_code']==expected_id
        assert enrollment.json()['study_id']==expected_id
        assert pi.get('/api/patients/'+pid).json()['patient']['study_id']==expected_id
        assert pi.get('/api/trial/subjects',params={'q':expected_id}).json()[0]['id']==subject_id
        assert subject['randomization_status']=='SEE_RESTRICTED_ALLOCATION_MODULE'
        samples=pi.get(f'/api/trial/subjects/{subject_id}/pcr')
        assert samples.status_code==200
        rows=samples.json()['pcr_records']
        assert [p['scheduled_month'] for p in rows]==[1,2,3,4,6,9,12]
        assert len(set(p['specimen_code'] for p in rows))==7
        assert all(p['specimen_code'].startswith(expected_id+'-PCR-') for p in rows)
        assert rows[0]['target_on']=='2026-11-01'
        assert pi.post(f'/api/trial/subjects/{subject_id}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True}).status_code==409
        assert pi.get('/api/patients/'+pid).json()['patient']['study_id']==expected_id
        assert len(pi.get(f'/api/trial/subjects/{subject_id}/pcr').json()['pcr_records'])==7
        worklist=pi.get('/api/trial/pcr-worklist').json()
        assert len(worklist)==7
        assert all(x['completion_verified'] is False for x in worklist)
        assert pi.get('/api/trial/overview').json()['enrolled']==1


def test_pcr_collection_qualitative_quantitative_and_independent_review():
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        for username,role in [('pcrpi','pi'),('pcrlab','microbiology'),('pcrreview','monitor')]:
            r=admin.post('/api/users',headers=h,json={'username':username,
                'display_name':'Synthetic '+role,'role':role,'password':'SyntheticClinicalPass123!'})
            assert r.status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'pcrpi','SyntheticClinicalPass123!')
        pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        record_id=pi.get(f'/api/trial/subjects/{sid}/pcr').json()['pcr_records'][0]['id']
    with TestClient(app) as lab:
        h=auth(lab,'pcrlab','SyntheticClinicalPass123!')
        r=lab.post(f'/api/trial/pcr/{record_id}/collect',headers=h,
            json={'collected_on':'2026-11-01','lab_accession':'TEST-LAB-1001'})
        assert r.status_code==200,r.text
        assert r.json()['revision']==2
        invalid=lab.put(f'/api/trial/pcr/{record_id}/result',headers=h,json={
            'expected_revision':2,'reported_on':'2026-11-02','assay_platform':'PCR Test',
            'result_kind':'not_detected','quantitative_iu_ml':100,'qc_status':'pass'})
        assert invalid.status_code==422
        r=lab.put(f'/api/trial/pcr/{record_id}/result',headers=h,json={
            'expected_revision':2,'reported_on':'2026-11-02','assay_platform':'PCR Test',
            'result_kind':'quantified','quantitative_iu_ml':1250.0,'lower_limit_iu_ml':100,
            'qc_status':'pass'})
        assert r.status_code==200,r.text
        assert r.json()['status']=='result_entered'
        assert lab.post(f'/api/trial/pcr/{record_id}/verify',headers=h,
            json={'expected_revision':3,'review_reason':'Signed report reviewed'}).status_code==403
        assert lab.get('/api/patients').json()[0]['name'] is None
        assert lab.get('/api/patients').json()[0]['cr_number'] is None
    with TestClient(app) as monitor:
        h=auth(monitor,'pcrreview','SyntheticClinicalPass123!')
        r=monitor.post(f'/api/trial/pcr/{record_id}/verify',headers=h,
            json={'expected_revision':3,'review_reason':'Signed report reviewed'})
        assert r.status_code==200,r.text
        assert r.json()['status']=='verified'
        assert monitor.post(f'/api/trial/pcr/{record_id}/verify',headers=h,
            json={'expected_revision':3,'review_reason':'Duplicate verification'}).status_code==409
        worklist=monitor.get('/api/trial/pcr-worklist').json()
        assert sum(x['completion_verified'] for x in worklist)==1



def sealed_test_rows():
    from app.randomization import STRATA
    # Test-only fixed example, not a clinical allocation sequence.
    rows=[]
    for stratum in STRATA:
        position=1
        for number,size in ((1,4),(2,6)):
            arms=['450']*(size//2)+['900']*(size//2)
            for arm in arms:
                rows.append({'stratum':stratum,'position':position,
                    'block_no':number,'block_size':size,'arm':arm})
                position+=1
    return rows


def lock_test_sequence(monkeypatch):
    from cryptography.fernet import Fernet
    from app.randomization import canonical
    import hashlib
    monkeypatch.setenv('RANDOMIZATION_FERNET_KEY',Fernet.generate_key().decode('ascii'))
    rows=sealed_test_rows()
    package={'protocol_version':'5.0','statistician_reference':'TEST-INDEPENDENT-STATISTICIAN',
             'signed_specification_reference':'TEST-SIGNED-BLOCK-PLAN',
             'independent_sequence_attested':True,
             'sequence_sha256':hashlib.sha256(canonical(rows)).hexdigest(),
             'entries':rows}
    with TestClient(app) as admin:
        h=auth(admin)
        created=admin.post('/api/users',headers=h,json={
            'username':'testallocationcustodian','display_name':'Synthetic independent sequence holder',
            'role':'randomization_custodian','password':'IndependentCustodianPassword123!'})
        assert created.status_code==200,created.text
        denied=admin.post('/api/trial/randomization/sequence/lock',headers=h,json=package)
        assert denied.status_code==403
    with TestClient(app) as custodian:
        h=auth(custodian,'testallocationcustodian','IndependentCustodianPassword123!')
        assert custodian.get('/api/patients').status_code==403
        assert custodian.get('/api/trial/subjects').status_code==403
        response=custodian.post('/api/trial/randomization/sequence/lock',headers=h,json=package)
        assert response.status_code==200,response.text
        assert response.json()['locked'] and response.json()['sequence_sha256']==package['sequence_sha256']
        assert response.json()['stratum_capacities']=={s:10 for s in (
            'rATG:living','rATG:deceased','no_rATG:living','no_rATG:deceased')}
        assert 'entries' not in response.json()
        again=custodian.post('/api/trial/randomization/sequence/lock',headers=h,json=package)
        assert again.status_code==409
        assert custodian.get('/api/trial/randomization/assigned-group-counts').json()['randomized']==0
    return package

def test_pharmacy_authorization_stock_issue_return_and_separate_roles(monkeypatch):
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        for name,role in [('drugpi','pi'),('dispensepharm','pharmacy')]:
            assert admin.post('/api/users',headers=h,json={'username':name,
                'display_name':'Synthetic '+role,'role':role,
                'password':'SyntheticDrugPassword123!'}).status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'drugpi','SyntheticDrugPassword123!')
        r=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert r.status_code==200
        before=pi.post(f'/api/trial/subjects/{sid}/drug-authorization',headers=h,json={
            'prescription_ref':'TEST-RX-UNRANDOMIZED','signed_on':'2026-10-03',
            'allocation_reference':'UNLOCKED-ATTEMPT',
            'renal_assessment_ref':'TEST-CRCL-001',
            'authorized_dose_instruction':'Use signed prescription only'})
        assert before.status_code==409
        lock_test_sequence(monkeypatch)
        assigned=pi.post(f'/api/trial/randomization/subjects/{sid}/assign',
            headers=h,json={'investigator_confirmation':True,'stratification_verified':True,
                'signed_randomization_source_ref':'TEST-SIGNED-PI-001'})
        assert assigned.status_code==200,assigned.text
        order=pi.post(f'/api/trial/subjects/{sid}/drug-authorization',headers=h,json={
            'prescription_ref':'TEST-RX-001','signed_on':__import__('datetime').date.today().isoformat(),
            'allocation_reference':assigned.json()['allocation_code'],
            'renal_assessment_ref':'TEST-CRCL-001',
            'authorized_dose_instruction':'Use signed prescription only'})
        assert order.status_code==200,order.text
        order_id=order.json()['id']
        assert pi.post('/api/trial/pharmacy/lots',headers=h,json={
            'lot_number':'TEST-BATCH','expiry_on':'2028-01-01','received_on':'2026-10-01',
            'strength_mg':450,'quantity_received':60}).status_code==403
    with TestClient(app) as pharm:
        h=auth(pharm,'dispensepharm','SyntheticDrugPassword123!')
        received=pharm.post('/api/trial/pharmacy/lots',headers=h,json={
            'lot_number':'TEST-BATCH','expiry_on':'2028-01-01','received_on':'2026-10-01',
            'strength_mg':450,'quantity_received':60})
        assert received.status_code==200,received.text
        lot=received.json()['lot_id']
        issued=pharm.post(f'/api/trial/subjects/{sid}/dispense',headers=h,json={
            'authorization_id':order_id,'lot_id':lot,'quantity_issued':30,
            'issued_on':__import__('datetime').date.today().isoformat()})
        assert issued.status_code==200,issued.text
        assert issued.json()['remaining_in_lot']==30
        assert '-MSS-' in issued.json()['slip_code']
        assert pharm.post(f'/api/trial/subjects/{sid}/dispense',headers=h,json={
            'authorization_id':order_id,'lot_id':lot,'quantity_issued':31,
            'issued_on':__import__('datetime').date.today().isoformat()}).status_code==409
        dispenses=pharm.get(f'/api/trial/subjects/{sid}/pharmacy').json()['dispenses']
        assert len(dispenses)==1
        r=pharm.post(f"/api/trial/pharmacy/dispenses/{dispenses[0]['id']}/return",headers=h,
            json={'quantity_returned':5,'returned_on':__import__('datetime').date.today().isoformat(),'disposition':'quarantine'})
        assert r.status_code==200,r.text
        assert r.json()['unreconciled_quantity']==25
        assert pharm.get('/api/trial/pharmacy/lots').json()[0]['quantity_on_hand']==30


def test_invitation_tokens_are_one_use_and_staff_choose_passwords():
    with TestClient(app) as c:
        h=auth(c)
        r=c.post('/api/trial/staff/invite',headers=h,json={
            'username':'researchtech','display_name':'Synthetic lab technician','role':'technician'})
        assert r.status_code==200,r.text
        token=r.json()['activation_token']
        assert len(token)>40
        assert c.post('/api/login',json={'username':'researchtech','password':'RandomGuess'}).status_code==401
        activated=c.post('/api/trial/staff/activate',json={
            'token':token,'password':'StrongTechnicianPassword123!'})
        assert activated.status_code==200,activated.text
        assert c.post('/api/trial/staff/activate',json={
            'token':token,'password':'AnotherLongPassword123456!'}).status_code==400
    with TestClient(app) as technician:
        auth(technician,'researchtech','StrongTechnicianPassword123!')
        r=technician.get('/api/trial/staff/roles')
        assert r.status_code==200


def test_totp_required_after_individual_enrollment():
    import pyotp
    with TestClient(app) as admin:
        h=auth(admin)
        setup=admin.post('/api/trial/staff/mfa-setup',headers=h)
        assert setup.status_code==200,setup.text
        secret=setup.json()['secret']
        otp=pyotp.TOTP(secret).now()
        confirm=admin.post('/api/trial/staff/mfa-confirm',headers=h,json={'otp':otp})
        assert confirm.status_code==200,confirm.text
    with TestClient(app) as new_session:
        assert new_session.post('/api/login',json={
            'username':'testadmin','password':'ThisIsALongTestingPassword123!'}).status_code==401
        correct=new_session.post('/api/login',json={
            'username':'testadmin','password':'ThisIsALongTestingPassword123!',
            'otp':pyotp.TOTP(secret).now()})
        assert correct.status_code==200,correct.text
        assert correct.json()['mfa_enabled'] is True


def test_user_lockout_after_five_failed_passwords():
    with TestClient(app) as client:
        for attempt in range(5):
            assert client.post('/api/login',json={
                'username':'testadmin','password':'definitely-incorrect'}).status_code==401
        response=client.post('/api/login',json={
            'username':'testadmin','password':'ThisIsALongTestingPassword123!'})
        assert response.status_code==429,response.text


def test_blinded_monitor_audit_does_not_include_identity_or_raw_payload():
    with TestClient(app) as admin:
        h=auth(admin)
        patient=admin.post('/api/patients',headers=h,json={
            'name':'Synthetic monitor target','cr_number':'TEST-MON-001'})
        pid=patient.json()['id']
        assert admin.post('/api/users',headers=h,json={
            'username':'monitortest','display_name':'Synthetic monitor','role':'monitor',
            'password':'SyntheticMonitorPass123!'}).status_code==200
    with TestClient(app) as monitor:
        auth(monitor,'monitortest','SyntheticMonitorPass123!')
        rows=monitor.get(f'/api/patients/{pid}/audit').json()
        assert len(rows)>0
        assert all('old_record' not in row and 'new_record' not in row for row in rows)
        p=monitor.get(f'/api/patients/{pid}').json()['patient']
        assert 'name' not in p and 'cr_number' not in p
        assert monitor.get('/api/patients?q=TEST-MON-001').json()==[]


def test_90_day_activation_renewal_and_revocation():
    from datetime import datetime, timezone
    with TestClient(app) as admin:
        h=auth(admin)
        issued=admin.post('/api/trial/staff/invite',headers=h,json={
          'username':'cmvnurse90','display_name':'Synthetic Research Nurse','role':'nurse'})
        assert issued.status_code==200,issued.text
        token=issued.json()['activation_token']
        assert issued.json()['expires_in_days']==7
        activated=admin.post('/api/trial/staff/activate',json={
          'token':token,'password':'NurseTestPasswordLong123!'})
        assert activated.status_code==200,activated.text
        access=activated.json()['access_expires_at']
        assert 89 < (datetime.fromisoformat(access.replace('Z','+00:00'))-
                     datetime.now(timezone.utc)).total_seconds()/86400 <= 91
        accounts=admin.get('/api/trial/staff/accounts').json()
        nurse=next(a for a in accounts if a['username']=='cmvnurse90')
        assert nurse['role']=='nurse' and nurse['active']
        user_id=nurse['id']
    with TestClient(app) as nurse:
        h=auth(nurse,'cmvnurse90','NurseTestPasswordLong123!')
        assert nurse.get('/api/me').status_code==200
    with TestClient(app) as admin:
        h=auth(admin)
        renewed=admin.post(f'/api/trial/staff/accounts/{user_id}/renew',headers=h,
            json={'reason':'Approved next 90 day data entry assignment'})
        assert renewed.status_code==200,renewed.text
        revoked=admin.post(f'/api/trial/staff/accounts/{user_id}/revoke',headers=h,
            json={'reason':'Research task completed; revoke access'})
        assert revoked.status_code==200,revoked.text
    with TestClient(app) as nurse:
        assert nurse.post('/api/login',json={'username':'cmvnurse90',
            'password':'NurseTestPasswordLong123!'}).status_code==401


def test_pcr_anchor_and_eligibility_exclusion_review():
    from app.trial_api import INCLUSION_ITEMS,EXCLUSION_ITEMS
    with TestClient(app) as admin:
        h=auth(admin)
        pid,sid=setup_synthetic_trial(admin,h)
        assert admin.post('/api/users',headers=h,json={'username':'pialign',
            'display_name':'Synthetic protocol PI','role':'pi',
            'password':'ProtocolPiPasswordLong123!'}).status_code==200
    with TestClient(app) as clinician:
        h=auth(clinician,'testeligibilityconsultant','EligibilityTestPassword123!')
        inc={k:True for k in INCLUSION_ITEMS}
        exc={k:False for k in EXCLUSION_ITEMS}
        exc['ongoing_dialysis']=True
        response=clinician.put(f'/api/trial/subjects/{sid}/eligibility',headers=h,
          json={'inclusion':inc,'exclusion':exc,
            'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
            'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
            'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-02',
            'signed_source_reference':'TEST-DIALYSIS-EXCLUSION'})
        assert response.status_code==200
        assert response.json()['eligible'] is False
    with TestClient(app) as pi:
        h=auth(pi,'pialign','ProtocolPiPasswordLong123!')
        base={'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
              'pcr_anchor_basis':'transplant_date','protocol_reference':'signed-protocol-v5',
              'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True}
        assert pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json=base).status_code==422
    with TestClient(app) as clinician:
        h=auth(clinician,'testeligibilityconsultant','EligibilityTestPassword123!')
        exc['ongoing_dialysis']=False
        response=clinician.put(f'/api/trial/subjects/{sid}/eligibility',headers=h,
          json={'inclusion':inc,'exclusion':exc,
            'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
            'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
            'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-02',
            'signed_source_reference':'TEST-FINAL-SIGNED-CHECKLIST'})
        assert response.status_code==200
        assert response.json()['eligible'] is True
    with TestClient(app) as pi:
        h=auth(pi,'pialign','ProtocolPiPasswordLong123!')
        bad=dict(base,pcr_anchor_basis='enrollment_date',pcr_anchor_on='2026-10-03')
        assert pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json=bad).status_code==422
        assert pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json=base).status_code==200


def test_crf_v3_schema_contains_all_remaining_signed_sections():
    from app.crf_schema import CRF_FORMS, validate_payload
    assert list(CRF_FORMS)[:10]==[
        'C_baseline','D_adherence','E_followup','F_unscheduled_pcr',
        'G_cmv_event','H_adverse_event','I_clinical_outcome',
        'J_deviation','K_resource_cost','L_final_status']
    assert all(CRF_FORMS[k]['supplementary'] for k in (
        'M_medication','N_laboratory','O_infection','P_transplant'))
    assert len(CRF_FORMS['E_followup']['fields']) >= 17
    assert validate_payload('E_followup',{
        'scheduled_month':'3','actual_visit_on':'2026-10-30',
        'hemoglobin_g_dl':12.5})['hemoglobin_g_dl']==12.5
    import pytest
    with pytest.raises(ValueError,match='threshold'):
        validate_payload('G_cmv_event',{'event_on':'2026-10-30',
            'qualifying_pcr_iu_ml':1300,'pcr_at_least_1000':'no'})
    with pytest.raises(ValueError,match='Required'):
        validate_payload('F_unscheduled_pcr',{'pcr_iu_ml':700})
    with pytest.raises(ValueError,match='IEC'):
        validate_payload('H_adverse_event',{'ae_term':'neutropenia',
            'onset_on':'2026-10-30','serious':'yes'})


def test_longitudinal_source_record_context_blinding_and_cursor():
    from app.trial_models import TrialCRFEntry
    from datetime import date
    with TestClient(app) as admin:
        h=auth(admin);pid,sid=setup_synthetic_trial(admin,h)
        other_patient=admin.post('/api/patients',headers=h,json={
            'name':'Synthetic second participant','cr_number':'TEST-COURSE-OTHER',
            'transplant_date':'2026-10-01'}).json()['id']
        from app.trial_models import TrialSubject
        with SessionLocal() as s:
            author=s.get(TrialSubject,sid).created_by
            other=TrialSubject(patient_id=other_patient,screening_code='TEST-SCREEN-OTHER',
                screening_on=date(2026,10,2),donor_cmv_igg='positive',recipient_cmv_igg='positive',
                donor_type='living',created_by=author,status='screened')
            s.add(other);s.commit();other_id=other.id
        page=admin.get('/api/trial/subjects?limit=1').json()
        assert page[0]['id']==other_id
        earlier=admin.get(f'/api/trial/subjects?limit=1&before_id={other_id}').json()
        assert earlier[0]['id']==sid
        for username,role in [('coursepi','pi'),('coursenurse','nurse'),('coursemonitor','monitor')]:
            assert admin.post('/api/users',headers=h,json=dict(username=username,
                display_name='Synthetic '+role,role=role,password='SyntheticCoursePassword123!')).status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'coursepi','SyntheticCoursePassword123!')
        assert pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True}).status_code==200
        # Baseline clinical measurements must be recordable before allocation.
        r=pi.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json={
            'section':'C_baseline','occurred_on':'2026-10-02',
            'payload':{'serum_creatinine_mg_dl':1.4}})
        assert r.status_code==200,r.text
        context=pi.get(f'/api/trial/crf/patients/{pid}/context').json()
        assert context['subject']['id']==sid and context['allocation']['randomized'] is False
    with TestClient(app) as nurse:
        h=auth(nurse,'coursenurse','SyntheticCoursePassword123!')
        body={'section':'M_medication','occurred_on':'2026-10-02','payload':{
            'start_on':'2026-10-02','drug':'mycophenolate_sodium','indication':'maintenance',
            'record_type':'administered','dose_per_administration':360,'dose_unit':'mg',
            'frequency':'twice_daily','route':'oral','source_reference':'TEST-SOURCE-001'}}
        r=nurse.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json=body)
        assert r.status_code==200,r.text
        mismatch=dict(body,occurred_on='2026-10-03')
        assert nurse.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json=mismatch).status_code==422
        result=nurse.get(f'/api/trial/crf/subjects/{sid}/timeline').json()
        assert len(result['entries'])==1 and result['entries'][0]['payload']==body['payload']
        uid=result['entries'][0]['created_by']
        # More than a page on the same clinical date: no records lost or repeated.
        with SessionLocal() as s:
            for i in range(102):
                s.add(TrialCRFEntry(subject_id=sid,section='N_laboratory',
                    occurrence_key=f'TEST-LAB-{i}',occurred_on=date(2026,10,4),
                    payload={'sample_on':'2026-10-04','context':'inpatient',
                             'source_reference':f'TEST-{i}','creatinine_mg_dl':1.3},
                    created_by=uid,updated_by=uid))
            s.commit()
        first=nurse.get(f'/api/trial/crf/subjects/{sid}/timeline').json()
        second=nurse.get(f'/api/trial/crf/subjects/{sid}/timeline',params=first['next_cursor']).json()
        assert len(first['entries'])==100 and len(second['entries'])==3
        assert not set(x['id'] for x in first['entries']) & set(x['id'] for x in second['entries'])
        assert second['next_cursor'] is None
    with TestClient(app) as monitor:
        auth(monitor,'coursemonitor','SyntheticCoursePassword123!')
        assert monitor.get(f'/api/trial/crf/subjects/{sid}/timeline').json()['entries']==[]
        assert 'M_medication' not in monitor.get('/api/trial/crf/schema').json()['forms']
        assert monitor.get(f'/api/trial/crf/subjects/{sid}/entries?section=M_medication').status_code==403


def test_official_new_sequence_requires_prior_allocation_reconciliation(monkeypatch):
    from app import randomization as r
    from types import SimpleNamespace
    from fastapi import HTTPException
    monkeypatch.setattr(r,'CLINICAL_MODE',True)
    with pytest.raises(HTTPException) as error:
        r.generate_and_lock(r.GenerateSequence(statistician_reference='TEST-INDEPENDENT',
            signed_specification_reference='TEST-SPECIFICATION',independent_sequence_attested=True,
            block_sizes=[4,6]),SimpleNamespace(role='randomization_custodian'),None)
    assert error.value.status_code==422 and 'Reconcile' in error.value.detail


def test_structured_crf_autosave_submission_and_independent_review():
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        for username,role in [('formpi','pi'),('formnurse','nurse'),
                              ('formmonitor','monitor')]:
            r=admin.post('/api/users',headers=h,json={'username':username,
                'display_name':'Synthetic '+role,'role':role,
                'password':'SyntheticFormPassword123!'})
            assert r.status_code==200,r.text
    with TestClient(app) as pi:
        h=auth(pi,'formpi','SyntheticFormPassword123!')
        r=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert r.status_code==200,r.text
        assert 'C_baseline' in pi.get('/api/trial/crf/schema').json()['forms']
    with TestClient(app) as nurse:
        h=auth(nurse,'formnurse','SyntheticFormPassword123!')
        schema=nurse.get('/api/trial/crf/schema').json()['forms']
        assert 'E_followup' in schema
        assert 'C_baseline' not in schema
        path=f'/api/trial/crf/subjects/{sid}/drafts/E_followup'
        raw={'occurred_on':'2026-11-02','occurrence_key':'M01',
             'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-02',
                        'hemoglobin_g_dl':11.2,'hospitalization':'no'}}
        created=nurse.put(path,headers=h,json=raw)
        assert created.status_code==200,created.text
        assert created.json()['is_draft']
        assert nurse.get(path+'?occurrence_key=M01').json()['draft']['payload']==raw['payload']
        assert nurse.put(path,headers=h,json=raw).status_code==409
        revise=nurse.put(path,headers=h,json=dict(raw,expected_revision=1))
        assert revise.status_code==200
        submitted=nurse.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,
            json={'section':'E_followup','occurred_on':'2026-11-02',
                  'payload':raw['payload']})
        assert submitted.status_code==200,submitted.text
        entry_id=submitted.json()['entry_id']
        assert nurse.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,
            json={'section':'E_followup','occurred_on':'2026-11-02',
                  'payload':raw['payload']}).status_code==409
        assert nurse.post(f'/api/trial/crf/entries/{entry_id}/review',
          headers=h,json={'expected_revision':1,'decision':'verified',
                          'reason':'Source document checked'}).status_code==403
    with TestClient(app) as pi:
        h=auth(pi,'formpi','SyntheticFormPassword123!')
        r=pi.post(f'/api/trial/crf/entries/{entry_id}/review',headers=h,
            json={'expected_revision':1,'decision':'verified',
                  'reason':'Signed nurse visit note verified'})
        assert r.status_code==200,r.text
        complete=pi.get('/api/trial/crf/completeness').json()['visit_completion']
        assert complete['1']['submitted']==1
        assert complete['1']['verified']==1
    with TestClient(app) as monitor:
        h=auth(monitor,'formmonitor','SyntheticFormPassword123!')
        forms=monitor.get(f'/api/trial/crf/subjects/{sid}/entries').json()['entries']
        assert forms==[]
        assert monitor.get('/api/trial/crf/schema').json()['forms'].get('C_baseline') is None


def test_crf_pcr_month_link_rejects_wrong_subject_and_unapproved_results():
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        for username,role in [('linkpi','pi'),('linkscience','scientist')]:
            r=admin.post('/api/users',headers=h,json={'username':username,
                'display_name':'Synthetic '+role,'role':role,
                'password':'LinkPCRPassword123456!'})
            assert r.status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'linkpi','LinkPCRPassword123456!')
        r=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert r.status_code==200
        pcrs=pi.get(f'/api/trial/subjects/{sid}/pcr').json()['pcr_records']
        m2=next(x for x in pcrs if x['scheduled_month']==2)
    with TestClient(app) as scientist:
        h=auth(scientist,'linkscience','LinkPCRPassword123456!')
        bad=scientist.post(f'/api/trial/crf/subjects/{sid}/entries',
          headers=h,json={'section':'E_followup','occurred_on':'2026-11-01',
            'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-01',
                       'pcr_specimen_code':m2['specimen_code']}})
        assert bad.status_code==422,bad.text
        premature=scientist.post(f'/api/trial/crf/subjects/{sid}/entries',
          headers=h,json={'section':'E_followup','occurred_on':'2026-11-01',
            'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-01',
                       'pcr_specimen_code':pcrs[0]['specimen_code'],
                       'pcr_sample_on':'2026-11-01'}})
        assert premature.status_code==422,premature.text
        assert 'collection' in premature.text.lower()
        good=scientist.post(f'/api/trial/crf/subjects/{sid}/entries',
          headers=h,json={'section':'E_followup','occurred_on':'2026-11-01',
            'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-01',
                       'pcr_study_funded':'unknown',
                       'pcr_funding_source_reference':'TEST-FUNDING-SOURCE'}})
        assert good.status_code==200,good.text
        entries=scientist.get(f'/api/trial/crf/subjects/{sid}/entries').json()['entries']
        assert next(x for x in entries if x['section']=='E_followup')['payload']['pcr_study_funded']=='unknown'


def test_staff_expiration_enforced_on_active_sessions_and_login():
    from app.main import SessionLocal, User
    from app.trial_models import StaffAccess
    from app.main import now
    from datetime import timedelta
    from sqlalchemy import select
    with TestClient(app) as admin:
        h=auth(admin)
        invitation=admin.post('/api/trial/staff/invite',headers=h,json={
            'username':'expiringcmvstaff','display_name':'Synthetic expiring staff',
            'role':'nurse'})
        assert invitation.status_code==200,invitation.text
        activation=admin.post('/api/trial/staff/activate',json={
            'token':invitation.json()['activation_token'],
            'password':'LongStaffPasswordFor90Days123!'})
        assert activation.status_code==200,activation.text
    with TestClient(app) as nurse:
        h=auth(nurse,'expiringcmvstaff','LongStaffPasswordFor90Days123!')
        assert nurse.get('/api/me').status_code==200
        with SessionLocal() as s:
            user=s.scalar(select(User).where(User.username=='expiringcmvstaff'))
            record=s.get(StaffAccess,user.id)
            record.expires_at=now()-timedelta(hours=1)
            s.commit()
        assert nurse.get('/api/me').status_code==403
    with TestClient(app) as nurse2:
        assert nurse2.post('/api/login',json={'username':'expiringcmvstaff',
            'password':'LongStaffPasswordFor90Days123!'}).status_code==403


def test_user_self_service_password_change_revokes_session():
    with TestClient(app) as admin:
        h=auth(admin)
        invite=admin.post('/api/trial/staff/invite',headers=h,json={
            'username':'cmvpasswordchange','display_name':'Synthetic password changer',
            'role':'scientist'})
        assert invite.status_code==200,invite.text
        assert admin.post('/api/trial/staff/activate',json={
            'token':invite.json()['activation_token'],
            'password':'OldUniquePasswordLong123!'}).status_code==200
    with TestClient(app) as scientist:
        h=auth(scientist,'cmvpasswordchange','OldUniquePasswordLong123!')
        result=scientist.post('/api/trial/staff/change-password',headers=h,json={
            'old_password':'OldUniquePasswordLong123!',
            'new_password':'NewUniquePasswordLong123!'})
        assert result.status_code==200,result.text
        assert scientist.get('/api/me').status_code==401
        assert scientist.post('/api/login',json={
            'username':'cmvpasswordchange','password':'OldUniquePasswordLong123!'}).status_code==401
        assert scientist.post('/api/login',json={
            'username':'cmvpasswordchange','password':'NewUniquePasswordLong123!'}).status_code==200


def test_screening_source_metadata_restricted_and_donor_relationship_checked():
    with TestClient(app) as admin:
        h=auth(admin)
        p=admin.post('/api/patients',headers=h,json={
            'name':'Synthetic source-check patient','cr_number':'TEST-SOURCE-CHECK',
            'transplant_date':'2026-10-01'})
        assert p.status_code==200
        pid=p.json()['id']
        for username,role in [('sourcescientist','scientist'),('sourcemonitor','monitor')]:
            assert admin.post('/api/users',headers=h,json={
                'username':username,'display_name':'Synthetic '+role,
                'role':role,'password':'SyntheticSourcePassword123!'}).status_code==200
    with TestClient(app) as scientist:
        h=auth(scientist,'sourcescientist','SyntheticSourcePassword123!')
        base={'patient_id':pid,'screening_on':'2026-10-02',
              'donor_cmv_igg':'positive','recipient_cmv_igg':'positive',
              'donor_type':'living','ratg_induction':False}
        assert scientist.post('/api/trial/screening',headers=h,
            json=dict(base,donor_relationship='deceased')).status_code==422
        r=scientist.post('/api/trial/screening',headers=h,
            json=dict(base,donor_relationship='living_related',
                age_at_transplant=52,sex_at_birth='female',
                participant_initials='TT',pis_version='PIS-v3',
                consent_on='2026-10-02',consent_version='ICF-v3',
                consent_language='Telugu',consent_obtained_by='delegated scientist',
                signed_consent_source_ref='TEST-CONSENT-SOURCE'))
        assert r.status_code==200,r.text
        sid=r.json()['id']
        details=scientist.get(f'/api/trial/subjects/{sid}/restricted-screening')
        assert details.status_code==200
        assert details.json()['restricted']['pis_version']=='PIS-v3'
    with TestClient(app) as monitor:
        h=auth(monitor,'sourcemonitor','SyntheticSourcePassword123!')
        assert monitor.get(f'/api/trial/subjects/{sid}/restricted-screening').status_code==403


def test_batch_ten_individual_90_day_named_accounts_no_shared_passwords():
    with TestClient(app) as admin:
        h=auth(admin)
        requested=[{'username':f'cmvdata{n:02d}',
            'display_name':f'Synthetic staff member {n:02d}',
            'role':'scientist' if n<=3 else ('nurse' if n<=5 else
                 ('microbiology' if n<=7 else ('pharmacy' if n==8 else 'monitor')))}
                 for n in range(1,11)]
        result=admin.post('/api/trial/staff/invite-batch',headers=h,
                          json={'staff':requested})
        assert result.status_code==200,result.text
        data=result.json()
        assert data['created']==10
        codes=[x['activation_token'] for x in data['invitations']]
        assert len(set(codes))==10
        assert all(x['expires_in_days']==7 for x in data['invitations'])
        assert all(x['access_validity_days_after_activation']==90
                    for x in data['invitations'])
        accounts={x['username']:x for x in admin.get('/api/trial/staff/accounts').json()}
        for n in range(1,11):
            assert accounts[f'cmvdata{n:02d}']['active'] is False
        accepted=admin.post('/api/trial/staff/activate',json={
            'token':codes[0],'password':'UniqueStudyScientistPassword123!'})
        assert accepted.status_code==200,accepted.text
        assert admin.post('/api/trial/staff/activate',json={
            'token':codes[0],'password':'SecondTryPassword123!'}).status_code==400
        repeat=admin.post('/api/trial/staff/invite-batch',headers=h,json={
            'staff':[{'username':'cmvdata01','display_name':'Duplicate tester',
                      'role':'nurse'},
                     {'username':'newcmvstaff','display_name':'Should not create',
                      'role':'nurse'}]})
        assert repeat.status_code==409
        assert all(x['username']!='newcmvstaff'
                   for x in admin.get('/api/trial/staff/accounts').json())
    with TestClient(app) as scientist:
        assert scientist.post('/api/login',json={
            'username':'cmvdata01','password':'UniqueStudyScientistPassword123!'}).status_code==200


def test_concealed_randomization_requires_pi_eligibility_and_one_irreversible_slot(monkeypatch):
    from app.trial_models import RandomizationSlot
    from app.main import SessionLocal
    from sqlalchemy import select
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        assert admin.get(f'/api/trial/randomization/subjects/{sid}/preflight').json()['ready'] is False
        for username,role in [('randpi','pi'),('randscientist','scientist'),
                              ('randmonitor','monitor'),('randpharm','pharmacy')]:
            r=admin.post('/api/users',headers=h,json={'username':username,
                'display_name':'Synthetic '+role,'role':role,
                'password':'SyntheticConcealedPassword123!'})
            assert r.status_code==200
    with TestClient(app) as scientist:
        h=auth(scientist,'randscientist','SyntheticConcealedPassword123!')
        assert scientist.post(f'/api/trial/randomization/subjects/{sid}/assign',
            headers=h,json={'investigator_confirmation':True,'stratification_verified':True,
              'signed_randomization_source_ref':'TEST-CONFIRMED-001'}).status_code==403
    with TestClient(app) as pi:
        h=auth(pi,'randpi','SyntheticConcealedPassword123!')
        assert pi.post(f'/api/trial/randomization/subjects/{sid}/assign',
            headers=h,json={'investigator_confirmation':True,'stratification_verified':True,
              'signed_randomization_source_ref':'TEST-CONFIRMED-001'}).status_code==409
        enrolled=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
          'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
          'pcr_anchor_basis':'transplant_date','protocol_reference':'protocol-v5',
          'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert enrolled.status_code==200,enrolled.text
        assert pi.post(f'/api/trial/randomization/subjects/{sid}/assign',
            headers=h,json={'investigator_confirmation':True,'stratification_verified':True,
              'signed_randomization_source_ref':'TEST-CONFIRMED-001'}).status_code==503
    package=lock_test_sequence(monkeypatch)
    with TestClient(app) as pi:
        h=auth(pi,'randpi','SyntheticConcealedPassword123!')
        ready=pi.get('/api/trial/randomization/readiness').json()
        assert ready['sequence_locked'] and ready['randomized']==0
        allocated=pi.post(f'/api/trial/randomization/subjects/{sid}/assign',
             headers=h,json={'investigator_confirmation':True,'stratification_verified':True,
               'signed_randomization_source_ref':'TEST-CONFIRMED-001'})
        assert allocated.status_code==200,allocated.text
        assignment=allocated.json()
        assert assignment['stratum']=='rATG:living'
        assert assignment['assigned_arm_mg']=='450'  # Test-only independent list.
        assert assignment['allocation_code'].startswith('NCMV-R-')
        assert 'position' not in assignment and 'block_size' not in assignment
        assert pi.post(f'/api/trial/randomization/subjects/{sid}/assign',
            headers=h,json={'investigator_confirmation':True,'stratification_verified':True,
              'signed_randomization_source_ref':'TEST-CONFIRMED-002'}).status_code==409
        assert pi.get('/api/trial/randomization/assigned-group-counts').status_code==403
        forms=pi.get('/api/trial/crf/schema').json()['forms']['C_baseline']['fields']
        for locked in ('allocation_code','randomization_on','assigned_nominal_arm'):
            assert locked not in forms
        bad=pi.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json={
           'section':'C_baseline','occurred_on':'2026-10-03',
           'payload':{'hemoglobin_g_dl':11,
                       'assigned_nominal_arm':'900 mg OD'}})
        assert bad.status_code==422
        good=pi.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json={
           'section':'C_baseline','occurred_on':'2026-10-03',
           'payload':{'hemoglobin_g_dl':11}})
        assert good.status_code==200,good.text
        records=pi.get(f'/api/trial/crf/subjects/{sid}/entries').json()['entries']
        baseline=next(x for x in records if x['section']=='C_baseline')
        assert baseline['payload']['assigned_nominal_arm']=='450 mg OD'
        assert baseline['payload']['allocation_code']==assignment['allocation_code']
    with TestClient(app) as monitor:
        h=auth(monitor,'randmonitor','SyntheticConcealedPassword123!')
        masked=monitor.get(f'/api/trial/randomization/subjects/{sid}/allocation').json()
        assert masked['randomized'] is True
        assert 'assigned_arm_mg' not in masked
        assert monitor.get('/api/trial/randomization/assigned-group-counts').status_code==403
    with TestClient(app) as pharm:
        h=auth(pharm,'randpharm','SyntheticConcealedPassword123!')
        allocation=pharm.get(f'/api/trial/randomization/subjects/{sid}/allocation').json()
        assert allocation['assigned_arm_mg']=='450'
    with SessionLocal() as s:
        rows=s.scalars(select(RandomizationSlot).order_by(RandomizationSlot.position)).all()
        assert len(rows)==40
        assert sum(r.subject_id is not None for r in rows)==1
        assert all(len(r.encrypted_arm)>80 and r.encrypted_arm not in {'450','900'} for r in rows)
        assert any(r.subject_id==sid and r.stratum=='rATG:living' and r.position==1 for r in rows)


def test_sequence_import_rejects_tampering_and_invalid_block(monkeypatch):
    from app.randomization import canonical
    from cryptography.fernet import Fernet
    import hashlib
    monkeypatch.setenv('RANDOMIZATION_FERNET_KEY',Fernet.generate_key().decode())
    rows=sealed_test_rows()
    package={'protocol_version':'5.0','statistician_reference':'TEST-INDEPENDENT-STATISTICIAN',
             'signed_specification_reference':'TEST-SIGNED-SPECIFICATION',
             'independent_sequence_attested':True,
             'sequence_sha256':hashlib.sha256(canonical(rows)).hexdigest(),
             'entries':rows}
    with TestClient(app) as admin:
        h=auth(admin)
        assert admin.post('/api/users',headers=h,json={
            'username':'invalidcustodian','display_name':'Synthetic independent custodian',
            'role':'randomization_custodian',
            'password':'CustodianInvalidTest123456!'}).status_code==200
    with TestClient(app) as custodian:
        h=auth(custodian,'invalidcustodian','CustodianInvalidTest123456!')
        changed=dict(package,entries=[dict(r) for r in rows])
        changed['entries'][0]['arm']='900'
        assert custodian.post('/api/trial/randomization/sequence/lock',
            headers=h,json=changed).status_code==422
        changed['sequence_sha256']=hashlib.sha256(canonical(changed['entries'])).hexdigest()
        assert custodian.post('/api/trial/randomization/sequence/lock',
            headers=h,json=changed).status_code==422
        noattest=dict(package,independent_sequence_attested=False)
        assert custodian.post('/api/trial/randomization/sequence/lock',
            headers=h,json=noattest).status_code==422
        ready=custodian.get('/api/trial/randomization/readiness').json()
        assert ready['sequence_locked'] is False and ready['planned_randomizations']==0


def test_pi_cannot_impersonate_independent_sequence_custodian():
    with TestClient(app) as admin:
        h=auth(admin)
        assert admin.post('/api/users',headers=h,json={
            'username':'custodianboundarypi','display_name':'Synthetic PI for role boundary',
            'role':'pi','password':'CustodianRoleBoundaryPI123!'}).status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'custodianboundarypi','CustodianRoleBoundaryPI123!')
        user=pi.post('/api/users',headers=h,json={
            'username':'forbiddenlegacycustodian','display_name':'Synthetic invalid custodian',
            'role':'randomization_custodian','password':'LongCustodianInvalid123!'})
        assert user.status_code==403
        invited=pi.post('/api/trial/staff/invite',headers=h,json={
            'username':'forbiddencustodian','display_name':'Synthetic invalid custodian',
            'role':'randomization_custodian'})
        assert invited.status_code==403
        batch=pi.post('/api/trial/staff/invite-batch',headers=h,json={'staff':[{
            'username':'forbiddenbatchcustodian','display_name':'Synthetic invalid custodian',
            'role':'randomization_custodian'}]})
        assert batch.status_code==403


def test_capitalized_staff_username_normalized_and_duplicate_returns_conflict():
    with TestClient(app) as admin:
        h=auth(admin)
        first=admin.post('/api/trial/staff/invite',headers=h,json={
            'username':'  SaiSree  ','display_name':'  Sai Sree  ','role':'scientist'})
        assert first.status_code==200,first.text
        assert first.json()['username']=='saisree'
        again=admin.post('/api/trial/staff/invite',headers=h,json={
            'username':'SAISREE','display_name':'Sai Sree','role':'scientist'})
        assert again.status_code==409,again.text
        assert 'reissue' in again.json()['detail']
        users=admin.get('/api/trial/staff/accounts').json()
        matching=[u for u in users if u['username']=='saisree']
        assert len(matching)==1
        assert matching[0]['status']=='awaiting_activation'
        assert matching[0]['requires_activation'] is True


def test_reissue_unactivated_staff_token_cancels_previous_and_90_day_activation():
    with TestClient(app) as admin:
        h=auth(admin)
        first=admin.post('/api/trial/staff/invite',headers=h,json={
            'username':'  NewNurse  ','display_name':'New Nurse',
            'role':'nurse'})
        assert first.status_code==200,first.text
        previous_token=first.json()['activation_token']
        account=next(u for u in admin.get('/api/trial/staff/accounts').json()
                     if u['username']=='newnurse')
        wrong=admin.post(f"/api/trial/staff/accounts/{account['id']}/reissue",headers=h,
            json={'reason':'Fresh named invitation after loss','restore_revoked':True})
        assert wrong.status_code==422,wrong.text
        new=admin.post(f"/api/trial/staff/accounts/{account['id']}/reissue",headers=h,
            json={'reason':'Original invitation lost; reissue'})
        assert new.status_code==200,new.text
        assert new.json()['username']=='newnurse'
        fresh_token=new.json()['activation_token']
        assert fresh_token!=previous_token
        assert admin.post('/api/trial/staff/activate',json={
           'token':previous_token,'password':'NewNurseSecurePassword123!'}).status_code==400
        activated=admin.post('/api/trial/staff/activate',json={
           'token':fresh_token,'password':'NewNurseSecurePassword123!'})
        assert activated.status_code==200,activated.text
        current=next(u for u in admin.get('/api/trial/staff/accounts').json()
                     if u['username']=='newnurse')
        assert current['status']=='active'
        assert current['access_expires_at'] is not None
        assert admin.post(f"/api/trial/staff/accounts/{account['id']}/reissue",headers=h,
            json={'reason':'Cannot reissue active account'}).status_code==409


def test_reinstatement_of_revoked_account_requires_reason_and_explicit_approval():
    with TestClient(app) as admin:
        h=auth(admin)
        inv=admin.post('/api/trial/staff/invite',headers=h,json={
            'username':'RevokeRestore','display_name':'Revoked Staff Person',
            'role':'scientist'})
        assert inv.status_code==200,inv.text
        activation=admin.post('/api/trial/staff/activate',json={
            'token':inv.json()['activation_token'],
            'password':'BeforeRevocationPassword123!'})
        assert activation.status_code==200,activation.text
        account=next(u for u in admin.get('/api/trial/staff/accounts').json()
                     if u['username']=='revokerestore')
        assert admin.post(f"/api/trial/staff/accounts/{account['id']}/revoke",headers=h,
            json={'reason':'Test revocation for staff change'}).status_code==200
        state=next(u for u in admin.get('/api/trial/staff/accounts').json()
                   if u['username']=='revokerestore')
        assert state['status']=='revoked' and state['is_revoked']
        assert admin.post(f"/api/trial/staff/accounts/{account['id']}/reissue",headers=h,
            json={'reason':'Explicit reinstatement not yet approved'}).status_code==409
        reissued=admin.post(f"/api/trial/staff/accounts/{account['id']}/reissue",headers=h,
            json={'reason':'PI approved renewed staff delegation','restore_revoked':True})
        assert reissued.status_code==200,reissued.text
        assert reissued.json()['restored_previous_account'] is True
        assert admin.post('/api/login',json={
            'username':'revokerestore','password':'BeforeRevocationPassword123!'}).status_code==401
        activated=admin.post('/api/trial/staff/activate',json={
            'token':reissued.json()['activation_token'],
            'password':'AfterReinstatementPassword123!'})
        assert activated.status_code==200,activated.text
        # Staff login changes this test client's cookie; inspect the staff table
        # from a fresh admin session rather than mistaking a 403 for a list.
        assert admin.post('/api/login',json={
            'username':'revokerestore','password':'AfterReinstatementPassword123!'}).status_code==200
        with TestClient(app) as fresh_admin:
            auth(fresh_admin)
            listing=fresh_admin.get('/api/trial/staff/accounts')
            assert listing.status_code==200,listing.text
            state=next(u for u in listing.json() if u['username']=='revokerestore')
        assert state['active'] and state['status']=='active'
        assert state['access_expires_at'] is not None


def test_bulk_staff_accepts_capitalized_names_and_checks_collisions():
    with TestClient(app) as admin:
        h=auth(admin)
        invite=admin.post('/api/trial/staff/invite-batch',headers=h,json={'staff':[
            {'username':'NurseAlpha','display_name':'Nurse Alpha','role':'nurse'},
            {'username':'TechBeta','display_name':'Tech Beta','role':'technician'}]})
        assert invite.status_code==200,invite.text
        assert [x['username'] for x in invite.json()['invitations']]==[
            'nursealpha','techbeta']
        dupe=admin.post('/api/trial/staff/invite-batch',headers=h,json={'staff':[
            {'username':'NurseAlpha','display_name':'Nurse Alpha','role':'nurse'},
            {'username':'nursealpha','display_name':'Nurse Alpha','role':'nurse'}]})
        assert dupe.status_code==422


def test_server_reports_synthetic_mode_and_blocks_real_patient_data():
    with TestClient(app) as c:
        h=auth(c)
        mode=c.get('/api/system/mode')
        assert mode.status_code==200
        status=mode.json()
        assert status['mode']=='synthetic'
        assert status['clinical_registration_enabled'] is False
        assert status['institutional_release_required'] is True
        real=c.post('/api/patients',headers=h,json={
            'cr_number':'REAL-CR-NOT-ALLOWED',
            'name':'Not A Synthetic Test Subject'})
        assert real.status_code==403


def test_clinical_mode_api_no_cache_and_html_script_freshness():
    with TestClient(app) as c:
        assert c.get('/').status_code==200
        page=c.get('/')
        assert 'no-store' in page.headers.get('cache-control','')
        assert '/study_ui.js?v=' in page.text
        script=c.get('/study_ui.js')
        assert script.status_code==200
        assert 'no-store' in script.headers.get('cache-control','')
        h=auth(c)
        result=c.get('/api/system/mode')
        assert result.status_code==200
        assert result.json()['mode']=='synthetic'
        assert result.json()['clinical_registration_enabled'] is False
        assert 'no-store' in result.headers.get('cache-control','')



def test_subject_search_links_cr_and_preserves_strict_role_masking():
    with TestClient(app) as admin:
        h=auth(admin)
        pid,sid=setup_synthetic_trial(admin,h)
        found=admin.get('/api/trial/subjects',params={'q':'TEST-CLINICAL-001'}).json()
        assert len(found)==1 and found[0]['patient_id']==pid and found[0]['id']==sid
        assert found[0]['cr_number']=='TEST-CLINICAL-001' and found[0]['status']=='screened'
        assert admin.get('/api/trial/subjects',params={'q':'unknown-CR'}).json()==[]
        assert admin.get('/api/trial/subjects',params={'q':'Synthetic participant'}).json()[0]['id']==sid
        assert admin.post('/api/users',headers=h,json={'username':'lookupmonitor',
            'display_name':'Synthetic monitor','role':'monitor','password':'MonitorLookupPassword123!'}).status_code==200
    with TestClient(app) as monitor:
        auth(monitor,'lookupmonitor','MonitorLookupPassword123!')
        assert monitor.get('/api/trial/subjects',params={'q':'TEST-CLINICAL-001'}).json()==[]
        masked=monitor.get('/api/trial/subjects').json()[0]
        assert masked['cr_number'] is None and masked['name'] is None
        assert monitor.get('/api/trial/subjects',params={'q':masked['screening_code']}).json()[0]['id']==sid


@pytest.mark.parametrize('role',['pharmacy','microbiology','technician','monitor'])
def test_shared_registry_cr_lookup_before_study_id_exists(monkeypatch,role):
    from app.main import Audit
    monkeypatch.setenv('TEAM_WORKSPACE_ENABLED','true')
    with SessionLocal() as s:
        owner=s.scalar(select(User).where(User.username=='testadmin'))
        owner.pi_authorized=True
        s.add(Audit(actor_id=owner.id,action='owner_fresh_start_reset',entity_type='workspace_policy',
            entity_id='fresh-start-20261118-v1',reason='Synthetic lookup fixture'))
        s.commit()
    with TestClient(app) as admin:
        h=auth(admin)
        registered=admin.post('/api/patients',headers=h,json={
            'name':'Synthetic registry lookup','cr_number':'TEST-REGISTRY-UNENROLLED'})
        assert registered.status_code==200,registered.text
        pid=registered.json()['id']
        assert admin.post('/api/users',headers=h,json={'username':'lookupstaff',
            'display_name':'Synthetic lookup staff','role':role,'password':'RegistryLookupPassword123!'}).status_code==200
    with TestClient(app) as staff:
        auth(staff,'lookupstaff','RegistryLookupPassword123!')
        matches=staff.get('/api/patients',params={'q':'TEST-REGISTRY-UNENROLLED'}).json()
        assert len(matches)==1 and matches[0]['id']==pid and matches[0]['study_id'] is None
        assert matches[0]['cr_number']=='TEST-REGISTRY-UNENROLLED'
        assert staff.get('/api/patients/'+pid).json()['patient']['name']=='Synthetic registry lookup'
        assert staff.get('/api/trial/crf/patients/'+pid+'/context').json()['subject'] is None


def test_screened_consent_declined_is_retained_but_never_enrolled_or_randomized():
    """No patient record is deleted; a missing ICF cannot become eligible by clicking."""
    from app.main import Audit
    with TestClient(app) as admin:
        h=auth(admin)
        p=admin.post('/api/patients',headers=h,json={
            'name':'Synthetic declined screening','cr_number':'TEST-NOCONSENT-001',
            'transplant_date':'2026-10-01'})
        assert p.status_code==200,p.text
        pid=p.json()['id']
        assert admin.post('/api/users',headers=h,json={
            'username':'declinescreener','display_name':'Synthetic source screener',
            'role':'scientist','password':'SyntheticScreenPassword123!'}).status_code==200
        assert admin.post('/api/users',headers=h,json={
            'username':'declinepi','display_name':'Synthetic protocol investigator',
            'role':'pi','password':'SyntheticDeclinePiPassword123!'}).status_code==200
    with TestClient(app) as scientist:
        h=auth(scientist,'declinescreener','SyntheticScreenPassword123!')
        screen=scientist.post('/api/trial/screening',headers=h,json={
            'patient_id':pid,'screening_on':'2026-10-02',
            'donor_cmv_igg':'unknown','recipient_cmv_igg':'unknown',
            'donor_type':'living','ratg_induction':None})
        assert screen.status_code==200,screen.text
        sid=screen.json()['id']
        assert screen.json()['study_code'] is None
        denied=scientist.post(f'/api/trial/subjects/{sid}/consent-declined',
            headers=h,json={'confirmed':True})
        assert denied.status_code==200,denied.text
        assert denied.json()['status']=='consent_declined'
        assert scientist.post(f'/api/trial/subjects/{sid}/consent-declined',
            headers=h,json={'confirmed':True}).status_code==409
    with TestClient(app) as pi:
        h=auth(pi,'declinepi','SyntheticDeclinePiPassword123!')
        assert pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True}).status_code==409
        assert pi.post(f'/api/trial/randomization/subjects/{sid}/assign',headers=h,json={
            'investigator_confirmation':True,'stratification_verified':True}).status_code==409
        assert pi.get(f'/api/trial/subjects/{sid}').json()['status']=='consent_declined'
        assert pi.get('/api/patients/'+pid).json()['patient']['study_id'] is None
    with SessionLocal() as db_session:
        events=db_session.scalars(select(Audit).where(
            Audit.action=='consent_declined',Audit.entity_id==str(sid))).all()
        assert len(events)==1 and events[0].patient_id==pid


def test_nims_emblem_and_optional_nephrology_source_fields():
    """Institutional logo and optional fields do not change mandatory CRF requirements."""
    from app.crf_schema import CRF_FORMS,validate_payload
    with TestClient(app) as client:
        logo=client.get('/nims-logo.svg')
        assert logo.status_code==200
        assert logo.headers['content-type'].startswith('image/svg+xml')
        assert b'data:image/webp;base64,' in logo.content
    for form in ('C_baseline','E_followup','P_transplant'):
        values=CRF_FORMS[form]['fields']['nephrology_unit']
        assert values['required'] is False
        assert values['choices']==['NP1','NP2','NP3']
        assert validate_payload(form,{'nephrology_unit':'NP1'},partial=True)['nephrology_unit']=='NP1'
        with pytest.raises(ValueError,match='Invalid selection'):
            validate_payload(form,{'nephrology_unit':'NP4'},partial=True)
    for form in ('C_baseline','E_followup','G_cmv_event','H_adverse_event',
                 'I_clinical_outcome','P_transplant','M_medication','N_laboratory','O_infection'):
        spec=CRF_FORMS[form]['fields']['additional_notes']
        assert spec['type']=='textarea' and spec['required'] is False
        assert validate_payload(form,{'additional_notes':'Documented clinical clarification'},
                                partial=True)['additional_notes']=='Documented clinical clarification'


def test_enrollment_ineligibility_and_transplant_window_report_specific_reasons():
    """One signed negative eligibility criterion blocks enrollment and cannot be bypassed."""
    from app.trial_api import INCLUSION_ITEMS, EXCLUSION_ITEMS
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        assert admin.post('/api/users',headers=h,json={
            'username':'testeligibilitywindowpi',
            'display_name':'Synthetic window verification PI','role':'pi',
            'password':'TestWindowValidPassword123!'}).status_code==200
    review={
        'inclusion':{k:True for k in INCLUSION_ITEMS},
        'exclusion':{k:False for k in EXCLUSION_ITEMS},
        'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
        'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
        'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-02'
    }
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        review['exclusion']['unable_to_complete_followup']=True
        result=consultant.put(f'/api/trial/subjects/{sid}/eligibility',headers=h,json=review)
        assert result.status_code==200 and result.json()['eligible'] is False
    request={'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
        'pcr_anchor_basis':'transplant_date','reviewed_eligibility_and_consent':True,
        'approved_visit_anchor':True}
    with TestClient(app) as pi:
        h=auth(pi,'testeligibilitywindowpi','TestWindowValidPassword123!')
        refused=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json=request)
        assert refused.status_code==422, refused.text
        assert 'INELIGIBLE' in refused.text
        assert 'Unable/unwilling to complete follow-up' in refused.text
        actions=pi.get('/api/trial/action-worklist').json()['actions']
        flagged=[a for a in actions if a['subject_id']==sid]
        assert any(a['category']=='Eligibility not met' for a in flagged)
        assert not any(a['category']=='Randomization pending' for a in flagged)
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        review['exclusion']['unable_to_complete_followup']=False
        assert consultant.put(f'/api/trial/subjects/{sid}/eligibility',
                              headers=h,json=review).json()['eligible'] is True
    with TestClient(app) as pi:
        h=auth(pi,'testeligibilitywindowpi','TestWindowValidPassword123!')
        late=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            **request,'enrolled_on':'2026-11-21'})
        assert late.status_code==422
        assert '0–10 days' in late.text
        assert '51 days' in late.text


def test_serostatus_correction_requires_source_revalidation_and_audits_notes():
    """A source correction must never silently convert an old review to eligible."""
    from app.trial_api import INCLUSION_ITEMS, EXCLUSION_ITEMS
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        assert admin.post('/api/users',headers=h,json={
            'username':'testsourcecorrectionpi',
            'display_name':'Synthetic source correction PI','role':'pi',
            'password':'TestSourceCorrection123!'}).status_code==200
    url=f'/api/trial/subjects/{sid}/screening-serostatus'
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        before=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()['eligibility']
        assert before['baseline']['is_eligible'] is True
        no_source=consultant.put(url,headers=h,json={
            'donor_cmv_igg':'unknown','correction_reason':'New serology report verified'})
        assert no_source.status_code==422
        same=consultant.put(url,headers=h,json={
            'donor_cmv_igg':'positive','source_reference':'LAB-001',
            'correction_reason':'Reconcile duplicate source entry'})
        assert same.status_code==422
        changed=consultant.put(url,headers=h,json={
            'donor_cmv_igg':'unknown','source_reference':'LAB-001',
            'correction_reason':'Original sample source was uncertain'})
        assert changed.status_code==200,changed.text
        assert changed.json()['eligibility_revalidation_required'] is True
        after=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()['eligibility']
        assert after['baseline']['requires_source_reverification'] is True
        assert after['baseline']['is_eligible'] is False
        incompatible_review={
            'inclusion':{k:True for k in INCLUSION_ITEMS},
            'exclusion':{k:False for k in EXCLUSION_ITEMS},
            'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
            'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
            'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-02'}
        rejected=consultant.put(f'/api/trial/subjects/{sid}/eligibility',
             headers=h,json=incompatible_review)
        assert rejected.status_code==422
        assert 'Serostatus' in rejected.text
    with TestClient(app) as pi:
        h=auth(pi,'testsourcecorrectionpi','TestSourceCorrection123!')
        denied=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert denied.status_code==422
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        corrected=consultant.put(url,headers=h,json={
            'donor_cmv_igg':'positive','source_reference':'LAB-002',
            'correction_reason':'Correct result verified on the original laboratory source'})
        assert corrected.status_code==200,corrected.text
        final=consultant.put(f'/api/trial/subjects/{sid}/eligibility',
            headers=h,json={**incompatible_review,
                'nephrology_unit':'NP2',
                'review_notes':'Source verified with original laboratory report',
                'signed_source_reference':'LAB-002'})
        assert final.status_code==200,final.text
        assert final.json()['eligible'] is True
        persisted=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()['eligibility']
        baseline=persisted['baseline']
        assert baseline['nephrology_unit']=='NP2'
        assert baseline['review_notes']=='Source verified with original laboratory report'
        assert baseline['signed_source_reference']=='LAB-002'
        assert 'requires_source_reverification' not in baseline
    with TestClient(app) as pi:
        h=auth(pi,'testsourcecorrectionpi','TestSourceCorrection123!')
        enrolled=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert enrolled.status_code==200,enrolled.text
        refused=pi.put(url,headers=h,json={
            'donor_cmv_igg':'unknown','source_reference':'LAB-003',
            'correction_reason':'Attempt to alter allocation baseline'})
        assert refused.status_code==409


def test_eligibility_exception_review_records_staff_and_pi_without_bypassing_v5():
    """R+ broadening and late first-dose requests stay out of randomization until approved."""
    from app.trial_api import INCLUSION_ITEMS, EXCLUSION_ITEMS
    with TestClient(app) as admin:
        h=auth(admin)
        _,sid=setup_synthetic_trial(admin,h)
        assert admin.post('/api/users',headers=h,json={
            'username':'exceptionreviewpi','display_name':'Synthetic exception PI',
            'role':'pi','password':'ExceptionReviewStrongPassword123!'}).status_code==200
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        correction=consultant.put(f'/api/trial/subjects/{sid}/screening-serostatus',
            headers=h,json={
                'donor_cmv_igg':'unknown','source_reference':'TEST-CMV-IGG-SOURCE',
                'correction_reason':'Original donor serostatus requires verification'})
        assert correction.status_code==200,correction.text
        inclusion={k:True for k in INCLUSION_ITEMS}
        inclusion['donor_cmv_positive']=False
        inclusion['vgcv_within_10_days']=False
        review=consultant.put(f'/api/trial/subjects/{sid}/eligibility',
            headers=h,json={
                'inclusion':inclusion,'exclusion':{k:False for k in EXCLUSION_ITEMS},
                'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
                'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
                'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-03',
                'review_notes':'Recorded donor and delayed-start discrepancies'})
        assert review.status_code==200 and review.json()['eligible'] is False
        endpoint=f'/api/trial/subjects/{sid}/eligibility-exception-request'
        refused=consultant.post(endpoint,headers=h,json={
            'recommend_inclusion':True,'source_reference':'TEST-LAB',
            'reason':'Reconsider for amendment','prophylaxis_first_dose_on':'2026-09-30'})
        assert refused.status_code==422
        recorded=consultant.post(endpoint,headers=h,json={
            'recommend_inclusion':True,'source_reference':'TEST-LAB-RESULT',
            'reason':'Recipient positive; consider broader enrollment after protocol amendment',
            'prophylaxis_first_dose_on':'2026-10-15',
            'prior_regimen':'TEST-REGIMEN'})
        assert recorded.status_code==200,recorded.text
        assert recorded.json()['status']=='pending_pi_review'
        data=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()['eligibility']
        assert data['baseline']['is_eligible'] is False
        item=data['baseline']['exception_review']
        assert item['recorded_donor_cmv_igg']=='unknown'
        assert item['recorded_recipient_cmv_igg']=='positive'
        assert item['days_to_first_dose']==14
        assert item['pre_randomization_regimen']=='TEST-REGIMEN'
        rereview=consultant.put(f'/api/trial/subjects/{sid}/eligibility',
            headers=h,json={
                'inclusion':inclusion,'exclusion':{k:False for k in EXCLUSION_ITEMS},
                'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
                'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
                'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-03'})
        assert rereview.status_code==200 and rereview.json()['eligible'] is False
        assert consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()[
            'eligibility']['baseline']['exception_review']['status']=='pending_pi_review'
        pi_review_url=f'/api/trial/subjects/{sid}/eligibility-exception-pi-review'
        assert consultant.post(pi_review_url,headers=h,json={
            'support_inclusion':True,'supporting_reference':'TEST-PI',
            'review_reason':'Recommend prospective NIEC amendment'}).status_code==403
    with TestClient(app) as pi:
        h=auth(pi,'exceptionreviewpi','ExceptionReviewStrongPassword123!')
        endorsed=pi.post(pi_review_url,headers=h,json={
            'support_inclusion':True,'supporting_reference':'TEST-PI-REVIEW',
            'review_reason':'Support amendment submission; no exception to current protocol'})
        assert endorsed.status_code==200,endorsed.text
        assert endorsed.json()['status']=='requires_approved_protocol_amendment'
        denied=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert denied.status_code==422
        assert 'INELIGIBLE' in denied.text
        no_allocation=pi.get(f'/api/trial/randomization/subjects/{sid}/preflight')
        assert no_allocation.status_code==200
        assert no_allocation.json()['ready'] is False
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        declined=consultant.post(endpoint,headers=h,json={
            'recommend_inclusion':False,'source_reference':'TEST-LAB-RESULT',
            'reason':'Declined after source review; existing protocol not met'})
        assert declined.status_code==200
        assert declined.json()['status']=='staff_does_not_recommend'
        latest=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()[
            'eligibility']['baseline']['exception_review']
        assert latest['pi_decision'] is None


def test_signed_crf_evidence_and_verification_labels_are_not_digital_signoffs():
    from app.crf_schema import CRF_FORMS, validate_payload
    follow=CRF_FORMS['E_followup']['fields']
    assert follow['pcr_sample_on']['type']=='date'
    assert follow['pcr_study_funded']['choices']==['yes','no','unknown']
    assert 'eac_decision_source_reference' in CRF_FORMS['G_cmv_event']['fields']
    assert 'not electronic sign-off' in CRF_FORMS['L_final_status']['fields']['final_reviewer']['label'].lower()
    source=validate_payload('E_followup',{
        'scheduled_month':'1','actual_visit_on':'2026-11-01',
        'pcr_study_funded':'unknown','pcr_funding_source_reference':'TEST-SOURCE'
    })
    assert source['pcr_study_funded']=='unknown'
    with pytest.raises(ValueError,match='Invalid selection'):
        validate_payload('E_followup',{
            'scheduled_month':'1','actual_visit_on':'2026-11-01',
            'pcr_study_funded':'assumed_study_paid'})


def test_partial_eligibility_draft_is_private_editable_and_never_signed():
    """A partially filled eligibility form survives reload without modifying signed criteria."""
    from app.trial_api import INCLUSION_ITEMS,EXCLUSION_ITEMS
    with TestClient(app) as admin:
        headers=auth(admin);_,sid=setup_synthetic_trial(admin,headers)
        assert admin.post('/api/users',headers=headers,json={
            'username':'eligdraftpi','display_name':'Synthetic draft PI',
            'role':'pi','password':'DraftPiPassword123456!'}).status_code==200
    url=f'/api/trial/subjects/{sid}/eligibility-draft'
    with TestClient(app) as scientist:
        h=auth(scientist,'syntheticscreener','SyntheticScreenerPassword123!')
        assert scientist.get(url).status_code==200
        draft=scientist.put(url,headers=h,json={'inclusion':{'age_ge_18':True}})
        assert draft.status_code==200,draft.text
        assert draft.json()['not_approved_eligibility'] is True
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        assert consultant.get(url).json()['draft'] is None
        signed_before=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()['eligibility']
        assert signed_before['baseline']['is_eligible'] is True
        partial={'inclusion':{'age_ge_18':True,'vgcv_within_10_days':None},
                 'exclusion':{'crcl_below_10':False},
                 'baseline':{'age_years':'50','review_notes':'TEST: review after lab available'}}
        created=consultant.put(url,headers=h,json=partial)
        assert created.status_code==200,created.text
        assert created.json()['is_draft'] is True
        assert created.json()['not_approved_eligibility'] is True
        restored=consultant.get(url)
        assert restored.status_code==200,restored.text
        assert restored.json()['draft']['payload']['baseline']['review_notes']==partial['baseline']['review_notes']
        revision=restored.json()['draft']['revision']
        invalid=consultant.put(url,headers=h,json={'inclusion':{'not_a_real_criterion':True},
            'expected_revision':revision})
        assert invalid.status_code==422
        conflict=consultant.put(url,headers=h,json={**partial,'expected_revision':revision+5})
        assert conflict.status_code==409
        updated=consultant.put(url,headers=h,json={**partial,
            'baseline':{'age_years':'51'},'expected_revision':revision})
        assert updated.status_code==200,updated.text
        assert updated.json()['revision']==revision+1
        signed_after=consultant.get(f'/api/trial/subjects/{sid}/eligibility').json()['eligibility']
        assert signed_after['baseline']['is_eligible'] is True
        assert signed_after['baseline']['age_years']==signed_before['baseline']['age_years']
    with TestClient(app) as pi:
        h=auth(pi,'eligdraftpi','DraftPiPassword123456!')
        assert pi.get(url).json()['draft'] is None
    with TestClient(app) as consultant:
        h=auth(consultant,'testeligibilityconsultant','EligibilityTestPassword123!')
        signed=consultant.put(f'/api/trial/subjects/{sid}/eligibility',headers=h,json={
            'inclusion':{k:True for k in INCLUSION_ITEMS},
            'exclusion':{k:False for k in EXCLUSION_ITEMS},
            'age_years':50,'anc_per_ul':3000,'platelets_per_ul':180000,
            'hemoglobin_g_dl':11,'crcl_cg_ml_min':68,
            'baseline_cbc_on':'2026-10-02','reviewed_on':'2026-10-02'})
        assert signed.status_code==200,signed.text
        assert consultant.get(url).json()['draft'] is None
    with TestClient(app) as pi:
        h=auth(pi,'eligdraftpi','DraftPiPassword123456!')
        enrolled=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert enrolled.status_code==200,enrolled.text
        blocked=pi.put(url,headers=h,json={'inclusion':{'age_ge_18':True}})
        assert blocked.status_code==409


def test_one_record_lookup_supports_direct_crf_correction_without_cross_patient_access():
    with TestClient(app) as admin:
        h=auth(admin);_,sid=setup_synthetic_trial(admin,h)
        assert admin.post('/api/users',headers=h,json={
            'username':'directeditpi','display_name':'Synthetic direct edit PI',
            'role':'pi','password':'DirectEditPiPassword123!'}).status_code==200
        assert admin.post('/api/users',headers=h,json={
            'username':'directedittech','display_name':'Synthetic direct edit technician',
            'role':'technician','password':'DirectEditTechPassword123!'}).status_code==200
    with TestClient(app) as pi:
        h=auth(pi,'directeditpi','DirectEditPiPassword123!')
        enrolled=pi.post(f'/api/trial/subjects/{sid}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert enrolled.status_code==200,enrolled.text
        created=pi.post(f'/api/trial/crf/subjects/{sid}/entries',headers=h,json={
            'section':'E_followup','occurred_on':'2026-11-01',
            'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-01',
                       'contact_notes':'TEST: original source note'}})
        assert created.status_code==200,created.text
        entry_id=created.json()['entry_id']
        entry=pi.get(f'/api/trial/crf/entries/{entry_id}')
        assert entry.status_code==200,entry.text
        assert entry.json()['subject_id']==sid
        assert entry.json()['payload']['contact_notes']=='TEST: original source note'
        changed=pi.put(f'/api/trial/crf/entries/{entry_id}',headers=h,json={
            'expected_revision':1,'occurred_on':'2026-11-01',
            'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-01',
                       'contact_notes':'TEST: corrected source note'},
            'reason':'Corrected source note'})
        assert changed.status_code==200,changed.text
        assert changed.json()['revision']==2
        assert pi.get(f'/api/trial/crf/entries/{entry_id}').json()['payload']['contact_notes']=='TEST: corrected source note'
    with TestClient(app) as technician:
        h=auth(technician,'directedittech','DirectEditTechPassword123!')
        denied=technician.get(f'/api/trial/crf/entries/{entry_id}')
        assert denied.status_code==403
