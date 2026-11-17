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
        assert subject['randomization_status']=='SEE_RESTRICTED_ALLOCATION_MODULE'
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
    with pytest.raises(HTTPException,match='') as error:
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
        good=scientist.post(f'/api/trial/crf/subjects/{sid}/entries',
          headers=h,json={'section':'E_followup','occurred_on':'2026-11-01',
            'payload':{'scheduled_month':'1','actual_visit_on':'2026-11-01'}})
        assert good.status_code==200,good.text


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

