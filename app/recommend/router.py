"""상태 체크·추천 API.

GET  /api/regions             거주지 선택 목록 (시군구 code·label)
GET  /api/checkin/questions   상태 체크 문항 (FE 설문 화면)
POST /api/checkin/summary     응답 → 상태 요약 (저장하지 않음)
POST /api/recommendations     기본 정보 + 상태 체크 응답 → 정책 6개 + 청년센터 프로그램 4개

로그인·저장이 없는 MVP 라 요청 내용을 서버에 남기지 않는다.
DB(catalog_items)가 없거나 실패하면 서비스 JSON으로 추천한다 (응답 source 로 구분).
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.catalog.regions import region_list
from app.checkin.questions import all_questions
from app.checkin.summary import CheckinError, summarize
from app.recommend.rules import JOB, SCHOOL
from app.recommend.service import UnknownRegion, recommend

router = APIRouter(prefix="/api", tags=["recommend"])

Situation = Literal["임신·출산", "육아", "군인", "기혼", "미혼", "한부모가정", "장애인", "기초생활수급자",
                    "자립준비청년", "가족돌봄청년", "농업인", "중소기업재직", "지역인재"]


class Profile(BaseModel):
    age: int = Field(..., ge=0, le=120, description="만 나이")
    sex: Literal["남", "여"] | None = None
    sigungu_cd: str = Field(..., pattern=r"^\d{5}$", description="거주지 시군구 코드 (일반구가 있는 시는 구 코드, 예: 41117)")
    job: Literal[tuple(JOB)] | None = Field(None, description="지금 하는 일")  # type: ignore[valid-type]
    school: Literal[tuple(SCHOOL)] | None = Field(None, description="학생이면 학교")  # type: ignore[valid-type]
    situations: list[Situation] = Field(default_factory=list, description="해당하는 상황 (여성은 성별에서 자동)")


class CheckinRequest(BaseModel):
    answers: dict[str, Any] = Field(default_factory=dict)


class RecommendRequest(BaseModel):
    profile: Profile
    checkin: dict[str, Any] = Field(default_factory=dict, description="상태 체크 응답 (문항 id → 선택지 code)")


def optional_db(request: Request) -> Iterator[Session | None]:
    """DB가 설정돼 있으면 세션, 없으면 None (추천은 서비스 JSON으로 대신한다)."""
    database = request.app.state.database
    if database is None:
        yield None
        return
    with database.sessions() as session:
        yield session


@router.get("/regions")
def regions() -> dict:
    """거주지 선택 목록. FE는 이 code 를 profile.sigungu_cd 로 그대로 보낸다."""
    return {"regions": region_list()}


@router.get("/checkin/questions")
def checkin_questions() -> dict:
    return all_questions()


@router.post("/checkin/summary")
def checkin_summary(body: CheckinRequest) -> dict:
    try:
        return summarize(body.answers)
    except CheckinError as exc:
        raise HTTPException(status_code=422, detail="Invalid check-in answers") from exc


@router.post("/recommendations")
def recommendations(body: RecommendRequest, session: Session | None = Depends(optional_db)) -> dict:
    try:
        return recommend(session, body.profile.model_dump(), body.checkin)
    except CheckinError as exc:
        raise HTTPException(status_code=422, detail="Invalid check-in answers") from exc
    except UnknownRegion as exc:
        # 옛 행정코드(예: 광주·전남 통합 전 46xxx)를 쓰면 여기로 온다. 코드 목록은 원본(온통청년) 기준
        raise HTTPException(status_code=422, detail="Unknown sigungu_cd") from exc
