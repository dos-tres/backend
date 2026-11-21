"""POST /api/chat — AI 비서 대화 한 턴.

로그인·저장이 없는 MVP: FE 가 대화(messages)·기본 정보(profile)·상태 체크 답(checkin)을 매번 보낸다.
서버는 대화 내용을 저장하거나 로그에 남기지 않는다. 자세한 계약: docs/CHAT.md
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.apply import registry as apply_registry
from app.chat import safety
from app.chat.service import respond
from app.limits import client_key
from app.checkin.summary import CheckinError
from app.recommend.router import Profile, optional_db
from app.recommend.service import UnknownRegion

router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=1000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, max_length=40, description="지금까지 대화. 마지막은 user")
    profile: Profile | None = Field(None, description="기본 정보. 없으면 추천·검색 대신 needs=['profile']")
    checkin: dict[str, Any] = Field(default_factory=dict, description="지금까지 확인된 상태 체크 답")


@router.post("/chat")
def chat(body: ChatRequest, request: Request, session: Session | None = Depends(optional_db)) -> dict:
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=422, detail="Last message must be from user")
    if not safety.is_crisis(body.messages[-1].content):   # 위기 안내는 LLM 을 안 쓰므로 제한하지 않는다
        request.app.state.limiter.hit(client_key(request))
    try:
        data = respond(session, request.app.state.chat_model, [m.model_dump() for m in body.messages],
                       body.profile.model_dump() if body.profile else None, body.checkin)
        apply_registry.mark(data.get("results"), apply_registry.from_settings(request.app.state.settings))
        return data
    except CheckinError as exc:
        raise HTTPException(status_code=422, detail="Invalid check-in answers") from exc
    except UnknownRegion as exc:
        raise HTTPException(status_code=422, detail="Unknown sigungu_cd") from exc
