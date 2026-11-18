from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["local", "test", "staging", "production"] = "local"
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    database_url: SecretStr = SecretStr("sqlite:///./dulset.db")
    session_ttl_hours: int = Field(default=168, ge=1, le=720)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, values: list[str]) -> list[str]:
        for origin in values:
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.path
                or url.query
                or url.fragment
                or "*" in origin
            ):
                raise ValueError("ALLOWED_ORIGINS must contain exact HTTP(S) origins")
        return values

    @model_validator(mode="after")
    def validate_database(self) -> "Settings":
        try:
            database = make_url(self.database_url.get_secret_value())
        except Exception:
            raise ValueError("DATABASE_URL is invalid") from None
        if database.drivername not in {"sqlite", "postgresql+psycopg"}:
            raise ValueError("Use sqlite or postgresql+psycopg")
        if self.app_env in {"staging", "production"}:
            if database.drivername != "postgresql+psycopg":
                raise ValueError("Deployed environments require external PostgreSQL")
            if not self.allowed_origins or any(
                not value.startswith("https://") for value in self.allowed_origins
            ):
                raise ValueError("Deployed environments require explicit HTTPS origins")
        return self
