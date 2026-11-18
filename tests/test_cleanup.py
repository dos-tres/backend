from datetime import timedelta

from sqlalchemy import func, select

from app.cleanup import purge_expired
from app.models import AnonymousSession, Profile, utcnow
from tests.conftest import authorization


def test_cleanup_deletes_only_expired_sessions_and_profiles(client):
    authorization(client)
    active = authorization(client)
    with client.app.state.session_factory() as db:
        expired = db.scalar(select(AnonymousSession).order_by(AnonymousSession.created_at))
        expired.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert purge_expired(db) == 1
        assert purge_expired(db) == 0
        assert db.scalar(select(func.count()).select_from(Profile)) == 1
    assert client.get("/api/v1/profile", headers=active).status_code == 200
