from datetime import timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.main import create_app
from app.models import AnonymousSession, Profile, utcnow
from tests.conftest import authorization


def test_health_readiness_and_cors(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready"}
    headers = {"Origin": "http://localhost:5173", "Access-Control-Request-Method": "PUT"}
    assert client.options("/api/v1/profile", headers=headers).status_code == 200
    headers["Origin"] = "https://untrusted.example"
    assert client.options("/api/v1/profile", headers=headers).status_code == 400


def test_readiness_fails_without_migrations(tmp_path):
    settings = Settings(
        _env_file=None, app_env="test", database_url=f"sqlite:///{tmp_path}/empty.db"
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/healthz").status_code == 200
        response = client.get("/readyz")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_profile_isolation_persistence_and_deletion(client, settings):
    first, second = authorization(client), authorization(client)
    payload = {"age": 27, "region": "대전", "interests": ["housing", "employment"]}
    saved = client.put("/api/v1/profile", headers=first, json=payload)
    assert saved.status_code == 200
    assert saved.json()["age"] == 27
    assert saved.json()["updated_at"].endswith("+00:00")
    assert client.get("/api/v1/profile", headers=second).json()["age"] is None
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get("/api/v1/profile", headers=first).json()["region"] == "대전"
    # 세션 ID를 추측해 타인 프로필을 지정하는 입력은 허용하지 않습니다.
    assert (
        client.put("/api/v1/profile", headers=first, json={"session_id": "other"}).status_code
        == 422
    )
    assert client.delete("/api/v1/sessions/current", headers=first).status_code == 204
    assert client.get("/api/v1/profile", headers=first).status_code == 401
    assert client.get("/api/v1/profile", headers=second).status_code == 200
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(Profile)) == 1


def test_token_is_hashed_and_session_id_is_not_credential(client):
    result = client.post("/api/v1/sessions")
    assert result.status_code == 201
    data = result.json()
    assert result.headers["cache-control"] == "no-store"
    with client.app.state.session_factory() as db:
        session = db.get(AnonymousSession, data["session_id"])
        assert session.token_hash != data["access_token"]
        assert len(session.token_hash) == 64
    headers = {"Authorization": f"Bearer {data['session_id']}"}
    assert client.get("/api/v1/profile", headers=headers).status_code == 401


def test_invalid_and_expired_session(client):
    for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic invalid"}):
        response = client.get("/api/v1/profile", headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    headers = authorization(client)
    with client.app.state.session_factory() as db:
        session = db.scalar(select(AnonymousSession))
        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    response = client.get("/api/v1/profile", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SESSION_EXPIRED"


@pytest.mark.parametrize("payload", [{"age": -1}, {"age": True}, {"interests": ["unknown"]}])
def test_invalid_profile_does_not_overwrite_existing(client, payload):
    headers = authorization(client)
    client.put("/api/v1/profile", headers=headers, json={"age": 27})
    response = client.put("/api/v1/profile", headers=headers, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert client.get("/api/v1/profile", headers=headers).json()["age"] == 27


def test_full_profile_replacement_can_clear_answers(client):
    headers = authorization(client)
    client.put("/api/v1/profile", headers=headers, json={"age": 27, "region": "대전"})
    response = client.put("/api/v1/profile", headers=headers, json={})
    assert response.json()["age"] is None
    assert response.json()["region"] is None
    assert response.json()["interests"] == []


def test_database_failure_is_sanitized(client):
    command.downgrade(Config("alembic.ini"), "base")
    response = client.post("/api/v1/sessions")
    assert response.status_code == 503
    assert "INSERT" not in response.text
    assert "token_hash" not in response.text


def test_404_has_common_error_format(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]


def test_unexpected_failure_is_sanitized(client):
    @client.app.get("/test-failure")
    def fail():
        raise RuntimeError("private failure details")

    response = client.get("/test-failure", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert "private failure details" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
