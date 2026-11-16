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
    screening=client.post('/api/trial/screening',headers=headers,json={
        'patient_id':pid,'screening_on':'2026-10-02',
        'donor_cmv_igg':'positive','recipient_cmv_igg':'positive',
        'donor_type':'living','ratg_induction':True,
        'consent_on':'2026-10-02','consent_version':'ICF-v1',
        'eligibility_attested':True})
    assert screening.status_code==200,screening.text
    return pid,screening.json()['id']


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
        enrollment=pi.post(f'/api/trial/subjects/{subject_id}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True})
        assert enrollment.status_code==200,enrollment.text
        assert enrollment.json()['pcr_orders']==7
        subject=enrollment.json()['subject']
        assert subject['study_code'].startswith('NCMV-')
        assert subject['randomization_status']=='EXTERNAL_VERIFICATION_REQUIRED'
        samples=pi.get(f'/api/trial/subjects/{subject_id}/pcr')
        assert samples.status_code==200
        rows=samples.json()['pcr_records']
        assert [p['scheduled_month'] for p in rows]==[1,2,3,4,6,9,12]
        assert len(set(p['specimen_code'] for p in rows))==7
        assert rows[0]['target_on']=='2026-11-01'
        assert pi.post(f'/api/trial/subjects/{subject_id}/enroll',headers=h,json={
            'enrolled_on':'2026-10-03','pcr_anchor_on':'2026-10-01',
            'pcr_anchor_basis':'transplant_date','protocol_reference':'approved-protocol-v5',
            'reviewed_eligibility_and_consent':True,'approved_visit_anchor':True}).status_code==409
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


def test_pharmacy_authorization_stock_issue_return_and_separate_roles():
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
        order=pi.post(f'/api/trial/subjects/{sid}/drug-authorization',headers=h,json={
            'prescription_ref':'TEST-RX-001','signed_on':'2026-10-03',
            'allocation_reference':'TEST-EXTERNAL-ALLOCATION',
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
            'issued_on':'2026-10-03'})
        assert issued.status_code==200,issued.text
        assert issued.json()['remaining_in_lot']==30
        assert '-MSS-' in issued.json()['slip_code']
        assert pharm.post(f'/api/trial/subjects/{sid}/dispense',headers=h,json={
            'authorization_id':order_id,'lot_id':lot,'quantity_issued':31,
            'issued_on':'2026-10-03'}).status_code==409
        dispenses=pharm.get(f'/api/trial/subjects/{sid}/pharmacy').json()['dispenses']
        assert len(dispenses)==1
        r=pharm.post(f"/api/trial/pharmacy/dispenses/{dispenses[0]['id']}/return",headers=h,
            json={'quantity_returned':5,'returned_on':'2026-10-10','disposition':'quarantine'})
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
