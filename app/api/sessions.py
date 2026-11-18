import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies import current_session, token_digest
from app.core.database import get_db
from app.models import AnonymousSession, Profile, utcnow
from app.schemas import SessionCreated

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionCreated, status_code=201)
def create_session(request: Request, db: Session = Depends(get_db)):
    token = secrets.token_urlsafe(32)
    session = AnonymousSession(
        token_hash=token_digest(token),
        expires_at=utcnow() + timedelta(hours=request.app.state.settings.session_ttl_hours),
        profile=Profile(),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionCreated(session_id=session.id, access_token=token, expires_at=session.expires_at)


@router.delete("/current", status_code=204)
def delete_session(
    session: AnonymousSession = Depends(current_session), db: Session = Depends(get_db)
):
    db.delete(session)
    db.commit()
    return Response(status_code=204)
