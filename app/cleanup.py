"""만료 세션과 연결 프로필 삭제: uv run python -m app.cleanup"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import build_engine
from app.models import AnonymousSession, utcnow


def purge_expired(db: Session) -> int:
    expired = db.scalars(select(AnonymousSession).where(AnonymousSession.expires_at <= utcnow()))
    count = 0
    for session in expired:
        db.delete(session)
        count += 1
    db.commit()
    return count


def main():
    engine = build_engine(Settings().database_url.get_secret_value())
    try:
        with Session(engine) as db:
            print(f"Deleted expired sessions: {purge_expired(db)}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
