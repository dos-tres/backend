from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import current_session
from app.core.database import get_db
from app.models import AnonymousSession
from app.schemas import ProfileInput, ProfileResponse

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileResponse)
def get_profile(session: AnonymousSession = Depends(current_session)):
    return session.profile


@router.put("", response_model=ProfileResponse)
def replace_profile(
    payload: ProfileInput,
    session: AnonymousSession = Depends(current_session),
    db: Session = Depends(get_db),
):
    for key, value in payload.model_dump().items():
        setattr(session.profile, key, value)
    db.commit()
    db.refresh(session.profile)
    return session.profile
