"""POST /api/apply/start · /api/apply/draft · /api/apply/submit — 챗봇으로 신청하기 ① 대신 제출 (docs/APPLY.md 9장).

applicant(이름·생년월일·연락처)는 신청할 때만 받고, 저장하거나 로그에 남기지 않는다.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.apply import gform, registry, service
from app.checkin.summary import CheckinError, validate
from app.limits import client_key
from app.recommend.router import Profile, optional_db

router = APIRouter(prefix="/api/apply", tags=["apply"])


class Applicant(BaseModel):
    name: str | None = Field(None, max_length=30)
    birth_date: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    phone: str | None = Field(None, max_length=20)
    email: str | None = Field(None, max_length=100)


class StartRequest(BaseModel):
    item_id: str = Field(..., max_length=120)
    applicant: Applicant | None = None
    profile: Profile | None = None


class DraftMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=1000)


class DraftRequest(BaseModel):
    item_id: str = Field(..., max_length=120)
    question_id: str = Field(..., max_length=10)
    messages: list[DraftMessage] = Field(default_factory=list, max_length=40)
    profile: Profile | None = None
    checkin: dict[str, Any] = Field(default_factory=dict)
    previous: str | None = Field(None, max_length=2000)
    preview: bool = Field(False, description="true 면 LLM 을 부르지 않고 AI 에 보낼 글(ai_input)만 돌려준다")


class SubmitRequest(BaseModel):
    form_revision: str | None = Field(None, pattern=r"^[a-f0-9]{64}$")
    item_id: str = Field(..., max_length=120)
    applicant: Applicant | None = None
    answers: dict[str, str | list[str]] = Field(..., description="문항 id → 답 (filled 의 값 + questions 의 답)")


def forms(request: Request) -> dict[str, dict]:
    return registry.from_settings(request.app.state.settings)


def _error(status: int, code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, **extra}})


@router.post("/start")
def start(body: StartRequest, request: Request, session: Session | None = Depends(optional_db)):
    return service.start(session, forms(request), body.item_id,
                         body.applicant.model_dump() if body.applicant else None,
                         body.profile.model_dump() if body.profile else None)


@router.post("/draft")
def draft(body: DraftRequest, request: Request, session: Session | None = Depends(optional_db)):
    try:
        validate(body.checkin)
    except CheckinError:
        return _error(422, "VALIDATION_ERROR", "Invalid check-in answers")
    request.app.state.limiter.hit(client_key(request))   # LLM 사용량 제한 (429 RATE_LIMITED)
    try:
        return service.draft(session, request.app.state.chat_model, forms(request), body.item_id,
                             body.question_id, [m.model_dump() for m in body.messages],
                             body.profile.model_dump() if body.profile else None, body.checkin, body.previous,
                             preview=body.preview)
    except service.NotAvailable:
        return _error(404, "APPLY_NOT_AVAILABLE", "No draft for this item or question")
    except gform.FormError as exc:
        return _error(409, "APPLY_FORM_" + exc.reason.upper(), "Form is not available")


@router.post("/submit")
def submit(body: SubmitRequest, request: Request, session: Session | None = Depends(optional_db)):
    try:
        return service.submit(session, forms(request), body.item_id, body.answers, expected_revision=body.form_revision)
    except service.NotAvailable:
        return _error(404, "APPLY_NOT_AVAILABLE", "This item cannot be submitted by the assistant")
    except service.FormChanged:
        return _error(409,"APPLY_FORM_CHANGED","Form questions changed; review again")
    except gform.InvalidAnswers as exc:
        return _error(422, "APPLY_INVALID", "Some answers are missing or invalid", missing=exc.missing,
                      invalid=exc.invalid)
    except gform.FormClosed:
        return _error(409, "APPLY_FORM_CLOSED", "The form is closed")
    except (gform.FormError, gform.SubmitFailed):
        return _error(502, "APPLY_SUBMIT_FAILED", "Could not submit the form")
