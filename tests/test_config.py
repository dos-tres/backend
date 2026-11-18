import pytest
from pydantic import ValidationError

from app.core.config import Settings


@pytest.mark.parametrize("origins", [["*"], ["http://localhost:5173/"], ["https://x.example/path"]])
def test_exact_cors_origins(origins):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="test", allowed_origins=origins)


def test_production_requires_postgres_and_https():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql+psycopg://example:password@db.example/dulset",
        allowed_origins=["https://dulset.example"],
    )
    assert "password" not in repr(settings)
