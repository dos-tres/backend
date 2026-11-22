from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from sqlalchemy.engine import make_url
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "staging", "production"] = "local"
    database_url: SecretStr = SecretStr("")
    allowed_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 대화용 LLM (OpenAI). 파이프라인 분류와 같은 키 이름을 쓴다. 키가 없으면 /api/chat 은 503 (위기 안내는 키 없이도 동작)
    # GMS_KEY 는 예전 이름(SSAFY GMS, 종료). OPENAI_API_KEY 가 있으면 그쪽을 먼저 쓴다
    llm_api_key: SecretStr = Field(SecretStr(""), validation_alias=AliasChoices("llm_api_key", "OPENAI_API_KEY", "GMS_KEY"))
    llm_base_url: str = Field("https://api.openai.com/v1",
                              validation_alias=AliasChoices("llm_base_url", "OPENAI_BASE_URL", "LLM_BASE_URL"))
    llm_model: str = Field("gpt-4.1-mini", validation_alias=AliasChoices("llm_model", "LLM_MODEL"))
    llm_timeout_seconds: float = Field(20.0, gt=0, le=60)

    # 챗봇 신청: 대신 제출할 수 있는 항목 → 테스트 구글폼 주소 JSON (Git 제외 *.local.json, docs/APPLY.md 11장). 비우면 신청 가능한 항목 없음
    apply_forms_path: str = Field("", validation_alias=AliasChoices("apply_forms_path", "APPLY_FORMS_PATH"))

    @field_validator("llm_base_url", "llm_model", mode="before")
    @classmethod
    def empty_means_default(cls, value, info):
        # .env.example 처럼 빈 값이면 기본값을 쓴다
        if value in (None, ""):
            return cls.model_fields[info.field_name].default
        return value

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
