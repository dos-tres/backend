"""회원 테이블 (migration 0004). 테이블 설명: docs/DATABASE.md

지금 만든 것: 로그인 방식과 상관없는 회원·프로필·동의·상태 체크 응답.
아직 API·인증이 없어서 이 테이블에 쓰는 코드는 없다. 가입·로그인을 만들 때 함께 쓴다.

원칙
- 회원을 지우면(users 행 삭제) 연결된 개인 데이터가 모두 지워진다 (ON DELETE CASCADE).
- 민감한 값(상황: 장애·수급·한부모 등, 상태 체크 응답, 대화)은 user_consents 에 동의가 있을 때만 저장한다.
  DB는 이것을 강제하지 못하므로 저장하는 서비스 코드에서 확인한다.
- 프로필은 추천 API 의 profile(app/recommend/router.py Profile)과 같은 값을 쓴다. 나이 대신 출생연도를 저장한다.

로그인 방식(소셜·이메일·정부 서비스 연동)이 정해지지 않아 로그인 수단·세션 테이블은 아래에 주석으로만 둔다.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Identity, Index, SmallInteger,
                        String, func, text)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

USER_STATUSES = ("active", "withdrawn")
CONSENT_TYPES = (
    "terms",            # 이용약관
    "privacy",          # 개인정보 수집·이용 (기본 프로필)
    "sensitive_info",   # 민감 정보: 상황(장애·수급·한부모 등) 저장
    "checkin_storage",  # 상태 체크 응답 저장
    "chat_history",     # 대화 내용 저장
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class User(Base):
    """회원. 로그인 수단과 분리해 두어, 로그인 방식이 바뀌거나 여러 개가 되어도 이 테이블은 그대로 둔다."""
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # 탈퇴 요청 시각 (삭제 유예를 둘 경우)

    __table_args__ = (CheckConstraint(_in("status", USER_STATUSES), name="status"),)


class UserProfile(Base):
    """추천에 쓰는 기본 정보 (회원당 1행). 값 목록은 추천 API Profile 과 같다."""
    __tablename__ = "user_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               primary_key=True)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger)        # 나이는 해마다 바뀌므로 출생연도로 저장
    sex: Mapped[str | None] = mapped_column(String(2))                   # 남 / 여
    sigungu_cd: Mapped[str | None] = mapped_column(String(5))            # 원본(온통청년) 코드 체계. 예: 곡성 12720
    job: Mapped[str | None] = mapped_column(String(20))                  # rules.JOB 키 (구직 중, 회사원 …)
    school: Mapped[str | None] = mapped_column(String(20))               # rules.SCHOOL 키 (고등학생, 대학생, 대학원생)
    situations: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False,
                                                  server_default=text("'{}'::varchar[]"))   # sensitive_info 동의 필요
    interests: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False,
                                                 server_default=text("'{}'::varchar[]"))    # 상태 체크 관심 분야
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("birth_year IS NULL OR birth_year BETWEEN 1900 AND 2100", name="birth_year"),
        CheckConstraint("sex IS NULL OR sex IN ('남', '여')", name="sex"),
        CheckConstraint("sigungu_cd IS NULL OR sigungu_cd ~ '^[0-9]{5}$'", name="sigungu_cd"),
    )


class UserConsent(Base):
    """동의 이력. 동의·철회를 덮어쓰지 않고 쌓는다. 현재 동의 = 같은 종류의 가장 최근 행이 철회되지 않음."""
    __tablename__ = "user_consents"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False)
    consent_type: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)        # 동의한 약관·안내문 버전
    agreed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(_in("consent_type", CONSENT_TYPES), name="consent_type"),
        Index("ix_user_consents_user_id_consent_type", "user_id", "consent_type"),
    )


class CheckinResponse(Base):
    """상태 체크 응답 이력 (checkin_storage 동의 필요). 덮어쓰지 않고 쌓는다 — 다시 하거나 고치면 새 행."""
    __tablename__ = "checkin_responses"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
                                               nullable=False)
    question_version: Mapped[str] = mapped_column(String(30), nullable=False)   # app.checkin.questions.QUESTION_VERSION
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False)                # 문항 id → 선택지 code (/api/checkin 형식)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False)                # app.checkin.summary.summarize 결과
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False)            # 다섯 영역 문항을 모두 지나갔는지 (부분 응답 구분)
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="survey")   # survey / chat
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("source IN ('survey', 'chat')", name="source"),
        Index("ix_checkin_responses_user_id_created_at", "user_id", "created_at"),
    )


# ──────────────────────────────────────────────────────────────────────────────────────────────
# 계획: 로그인 수단·세션 (로그인 방식이 정해지면 주석을 풀고 migration 을 추가한다)
#
# 이렇게 하려고 했다:
# - 회원(users)과 로그인 수단을 나눈다. 한 회원이 카카오·구글·이메일 등 여러 수단을 연결할 수 있고,
#   방식이 바뀌어도 users 와 그 아래 개인 데이터는 그대로 둔다.
# - provider_subject 는 각 제공자가 주는 고유 id(소셜 로그인의 sub 등). 이메일·전화번호를 식별자로 쓰지 않는다.
# - 세션은 서버에 저장하는 불투명 토큰. 원문은 저장하지 않고 SHA-256 해시만 둔다. 로그아웃·강제 만료는 revoked_at.
#   (JWT 만 쓰면 로그아웃·탈퇴 즉시 무효화가 어려워서 서버 세션을 기본으로 생각했다)
# - 정부 서비스 연동(본인확인 등)을 쓰면 provider 에 추가하고, 받은 개인정보는 저장하지 않는 쪽으로 검토한다.
# - 로그인 없이 먼저 써 보고 나중에 가입하는 흐름을 넣으면, 익명 사용자도 users 행을 만들고
#   provider='anonymous' 세션만 둔 뒤 가입할 때 identity 를 연결한다 (기록이 그대로 이어진다).
#
# PROVIDERS = ("kakao", "naver", "google", "email", "gov", "anonymous")   # 확정 전 후보
#
# class UserIdentity(Base):
#     __tablename__ = "user_identities"
#
#     id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
#     user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
#                                                nullable=False)
#     provider: Mapped[str] = mapped_column(String(20), nullable=False)
#     provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
#     last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
#
#     __table_args__ = (
#         UniqueConstraint("provider", "provider_subject", name="uq_user_identities_provider_subject"),
#         Index("ix_user_identities_user_id", "user_id"),
#     )
#
#
# class AuthSession(Base):
#     __tablename__ = "auth_sessions"
#
#     id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
#     user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
#                                                nullable=False)
#     token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)   # SHA-256 hex, 원문 저장 안 함
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
#     expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
#     revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
#
#     __table_args__ = (Index("ix_auth_sessions_user_id", "user_id"), Index("ix_auth_sessions_expires_at", "expires_at"))
# ──────────────────────────────────────────────────────────────────────────────────────────────
