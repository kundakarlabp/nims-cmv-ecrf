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
