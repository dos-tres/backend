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

    # 대화용 LLM (OpenAI 호환). 파이프라인 분류와 같은 키 이름을 쓴다. 키가 없으면 /api/chat 은 503 (위기 안내는 키 없이도 동작)
    llm_api_key: SecretStr = Field(SecretStr(""), validation_alias=AliasChoices("llm_api_key", "GMS_KEY", "OPENAI_API_KEY"))
    llm_base_url: str = Field("https://gms.ssafy.io/gmsapi/api.openai.com/v1",
                              validation_alias=AliasChoices("llm_base_url", "OPENAI_BASE_URL", "LLM_BASE_URL"))
    llm_model: str = Field("gpt-4.1-mini", validation_alias=AliasChoices("llm_model", "LLM_MODEL"))
    llm_timeout_seconds: float = Field(20.0, gt=0, le=60)

    # 챗봇 신청: 대신 제출할 수 있는 항목 → 테스트 구글폼 주소 JSON (Git 제외 *.local.json, docs/APPLY.md 11장). 비우면 신청 가능한 항목 없음
    apply_forms_path: str = Field("", validation_alias=AliasChoices("apply_forms_path", "APPLY_FORMS_PATH"))
    # 배포용: 같은 내용을 JSON 문자열로 (서버에는 파일을 올리지 않는다). 둘 다 있으면 합친다
    apply_forms_json: SecretStr = Field(SecretStr(""), validation_alias=AliasChoices("apply_forms_json", "APPLY_FORMS_JSON"))

    # 배포: FE 빌드(dist) 폴더. index.html 이 있으면 API 와 같은 주소에서 화면을 제공한다 (app/web.py). 로컬 개발은 비움
    web_dir: str = Field("", validation_alias=AliasChoices("web_dir", "WEB_DIR"))

    # 배포: 앱 안 스케줄러 (시작 후 1번 + 매일 scheduler_hour 시, 서버 시간대 기준). 로컬·테스트는 끔 (app/scheduler.py)
    scheduler_enabled: bool = Field(False, validation_alias=AliasChoices("scheduler_enabled", "SCHEDULER_ENABLED"))
    scheduler_hour: int = Field(4, ge=0, le=23, validation_alias=AliasChoices("scheduler_hour", "SCHEDULER_HOUR"))
    # 배포: 시작할 때 운영 DB 테이블 만들기(alembic upgrade head) + 비어 있으면 기본 데이터 적재. DATABASE_URL 이 있을 때만
    db_auto_migrate: bool = Field(False, validation_alias=AliasChoices("db_auto_migrate", "DB_AUTO_MIGRATE"))

    # LLM 을 부르는 요청(대화·초안) 사용량 제한 (app/limits.py). 0이면 그 제한을 끈다. 위기 안내는 제한하지 않는다
    llm_limit_per_minute: int = Field(10, ge=0, validation_alias=AliasChoices("llm_limit_per_minute", "LLM_LIMIT_PER_MINUTE"))
    llm_limit_per_day: int = Field(100, ge=0, validation_alias=AliasChoices("llm_limit_per_day", "LLM_LIMIT_PER_DAY"))
    llm_limit_total_per_day: int = Field(2000, ge=0, validation_alias=AliasChoices("llm_limit_total_per_day", "LLM_LIMIT_TOTAL_PER_DAY"))

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
