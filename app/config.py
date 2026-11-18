from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from sqlalchemy.engine import make_url
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "staging", "production"] = "local"
    database_url: SecretStr = SecretStr("")
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value():
            return value
        try:
            url = make_url(value.get_secret_value())
            if url.drivername != "postgresql+psycopg" or not url.database:
                raise ValueError
        except Exception:
            raise ValueError("Use a PostgreSQL psycopg URL with a database name") from None
        return value

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("Use exact HTTP(S) origins without paths or wildcards")
            # Accessing port also rejects invalid port values at startup.
            parsed.port
        return origins
