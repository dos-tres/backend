import hashlib
from datetime import UTC

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.models import AnonymousSession, utcnow

bearer = HTTPBearer(auto_error=False)


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AnonymousSession:
    if credentials is None or len(credentials.credentials) > 128:
        raise ApiError(401, "SESSION_INVALID", "유효한 세션이 필요합니다.")
    session = db.scalar(
        select(AnonymousSession).where(
            AnonymousSession.token_hash == token_digest(credentials.credentials)
        )
    )
    if session is None:
        raise ApiError(401, "SESSION_INVALID", "유효한 세션이 필요합니다.")
    expires_at = session.expires_at.replace(tzinfo=session.expires_at.tzinfo or UTC)
    if expires_at <= utcnow():
        raise ApiError(401, "SESSION_EXPIRED", "세션이 만료되었습니다. 새로 시작해주세요.")
    return session
