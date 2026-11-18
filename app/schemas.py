from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

Interest = Literal["employment", "housing", "education", "finance", "participation", "wellbeing"]


class TimestampModel(BaseModel):
    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_timestamps(self, value):
        if isinstance(value, datetime):
            return value.replace(tzinfo=value.tzinfo or UTC).isoformat()
        return value


class SessionCreated(TimestampModel):
    session_id: str
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    age: int | None = Field(default=None, ge=0, le=120, strict=True)
    region: str | None = Field(default=None, min_length=1, max_length=50)
    employment_status: Literal["student", "employed", "job_seeking", "other"] | None = None
    housing_status: Literal["with_family", "renting", "owning", "other"] | None = None
    interests: list[Interest] = Field(default_factory=list, max_length=6)

    @field_validator("interests")
    @classmethod
    def unique_interests(cls, values: list[Interest]) -> list[Interest]:
        return list(dict.fromkeys(values))


class ProfileResponse(ProfileInput, TimestampModel):
    model_config = ConfigDict(from_attributes=True)
    updated_at: datetime


class ErrorDetail(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
