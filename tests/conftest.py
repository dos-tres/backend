import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    # TEST_DATABASE_URL은 테스트마다 초기화되는 전용 DB에만 지정합니다.
    database_url = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return Settings(_env_file=None, app_env="test", database_url=database_url)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def authorization(client):
    data = client.post("/api/v1/sessions").json()
    return {"Authorization": f"Bearer {data['access_token']}"}
