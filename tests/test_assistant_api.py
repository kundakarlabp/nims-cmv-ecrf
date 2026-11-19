"""Verify assistant adapter inherits the established clinical auth path."""
from fastapi.testclient import TestClient
from app.main import app, current, AuthContext


def test_assistant_endpoints_require_named_login():
    with TestClient(app) as client:
        for path in ("/api/assistant/capabilities", "/api/assistant/subjects?q=NCMV001",
                     "/api/assistant/subjects/1/crf"):
            assert client.get(path).status_code == 401
        assert client.post("/api/assistant/subjects/1/entries", json={}).status_code == 401


def test_assistant_contract_has_no_anonymous_bridge_or_allocation_action():
    with TestClient(app) as client:
        try:
            app.dependency_overrides[current] = lambda: AuthContext(
                user_id="synthetic-user", role="pi", name="Test",
                csrf_hash="synthetic-hash")
            response = client.get("/api/assistant/capabilities")
            assert response.status_code == 200
            value = response.json()
            assert value["external_chat_connection_active"] is False
            assert value["requires_csrf_for_writes"] is True
            assert "randomize" not in value["operations"]
            assert "submit_confirmed_crf" in value["operations"]
            assert client.get("/api/assistant/subjects?q=a").status_code == 422
            assert client.get("/api/assistant/subjects?q=%20%20%20").status_code == 422
            # An explicit confirmation is mandatory before looking up a study record.
            payload={"study_code":"NCMV001","section":"C_baseline",
                     "occurred_on":"2026-11-19","payload":{},
                     "confirm_submission":False}
            response=client.post("/api/assistant/subjects/1/entries",json=payload)
            assert response.status_code == 422
            assert "confirmation" in response.json()["detail"].lower()
        finally:
            app.dependency_overrides.pop(current,None)


def test_assistant_router_has_no_credential_or_arbitrary_command_interface():
    paths=[r.path for r in app.routes if r.path.startswith("/api/assistant")]
    assert "/api/assistant/capabilities" in paths
    assert not any("token" in p or "command" in p or "shell" in p for p in paths)


def test_authenticated_synthetic_crf_draft_submit_and_revision_audit():
    """End-to-end route test: no third-party token, no patient data, no allocation."""
    from datetime import date
    from sqlalchemy import select
    from app.main import Base, ENGINE, SessionLocal, User, Patient, PH, Audit
    from app.trial_models import TrialSubject

    Base.metadata.drop_all(ENGINE)
    Base.metadata.create_all(ENGINE)
    try:
        with SessionLocal() as db:
            user=User(username="assistedpi",display_name="Synthetic PI",role="pi",
                      password_hash=PH.hash("SyntheticAssistantPassword123!"))
            db.add(user);db.flush()
            patient=Patient(name="Synthetic assistant subject",
                            cr_number="TEST-ASSISTANT-001",created_by=user.id,
                            transplant_date=date(2026,10,1))
            db.add(patient);db.flush()
            subject=TrialSubject(patient_id=patient.id,created_by=user.id,
                     screening_code="NCMV-S-00001",study_code="NCMV001",
                     screening_on=date(2026,10,2),enrolled_on=date(2026,10,3),
                     pcr_anchor_on=date(2026,10,1),pcr_anchor_basis="transplant_date",
                     donor_cmv_igg="positive",recipient_cmv_igg="positive",
                     donor_type="living",ratg_induction=True,status="enrolled")
            db.add(subject);db.commit();sid=subject.id;pid=patient.id
        with TestClient(app) as client:
            login=client.post("/api/login",json={
                "username":"assistedpi","password":"SyntheticAssistantPassword123!"})
            assert login.status_code==200,login.text
            headers={"X-CSRF-Token":login.json()["csrf_token"]}
            matches=client.get("/api/assistant/subjects",params={"q":"NCMV001"})
            assert matches.status_code==200,matches.text
            assert len(matches.json())==1 and matches.json()[0]["id"]==sid
            draft={"study_code":"NCMV001","occurred_on":"2026-10-03",
                   "occurrence_key":"MAIN",
                   "payload":{"weight_kg":64,"source_reference":"TEST-ASSISTANT-SOURCE"}}
            url=f"/api/assistant/subjects/{sid}/drafts/C_baseline"
            assert client.put(url,json=draft).status_code==403  # CSRF
            mismatch=client.put(url,headers=headers,json={**draft,"study_code":"NCMV999"})
            assert mismatch.status_code==409
            saved=client.put(url,headers=headers,json=draft)
            assert saved.status_code==200,saved.text
            assert saved.json()["revision"]==1
            assert saved.json()["is_draft"] is True
            assert client.put(url,headers=headers,json=draft).status_code==409
            submit_url=f"/api/assistant/subjects/{sid}/entries"
            entry={"study_code":"NCMV001","section":"C_baseline",
                   "occurred_on":"2026-10-03",
                   "payload":{"weight_kg":64,"source_reference":"TEST-ASSISTANT-SOURCE"}}
            assert client.post(submit_url,headers=headers,json=entry).status_code==422
            submitted=client.post(submit_url,headers=headers,
                                  json={**entry,"confirm_submission":True})
            assert submitted.status_code==200,submitted.text
            eid=submitted.json()["entry_id"]
            assert client.post(submit_url,headers=headers,
                               json={**entry,"confirm_submission":True}).status_code==409
            readback=client.get(f"/api/assistant/subjects/{sid}/crf")
            assert readback.status_code==200,readback.text
            assert "TEST-ASSISTANT-SOURCE" in readback.text
            correction={"study_code":"NCMV001","expected_revision":1,
                        "occurred_on":"2026-10-03",
                        "payload":{"weight_kg":65,"source_reference":"TEST-CORRECTED"},
                        "reason":"Corrected using the signed synthetic baseline"}
            correct_url=f"/api/assistant/entries/{eid}"
            assert client.put(correct_url,headers=headers,json=correction).status_code==422
            corrected=client.put(correct_url,headers=headers,
                                 json={**correction,"confirm_correction":True})
            assert corrected.status_code==200,corrected.text
            assert corrected.json()["revision"]==2
            assert client.put(correct_url,headers=headers,
                              json={**correction,"confirm_correction":True}).status_code==409
            with SessionLocal() as db:
                actions=[a.action for a in db.scalars(
                    select(Audit).where(Audit.patient_id==pid)).all()]
            assert "crf_submit" in actions and "crf_correct" in actions
    finally:
        Base.metadata.drop_all(ENGINE)
