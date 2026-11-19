"""회원 테이블 (migration 0004) 기본값·제약·삭제 연쇄. PostgreSQL 통합 테스트, TEST_DATABASE_URL 필요."""
import os
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.checkin.questions import QUESTION_VERSION
from app.checkin.summary import summarize
from app.database import Database
from app.users.models import CheckinResponse, User, UserConsent, UserProfile

TEST_URL = os.environ.get("TEST_DATABASE_URL", dotenv_values(".env").get("TEST_DATABASE_URL"))


@unittest.skipUnless(TEST_URL, "TEST_DATABASE_URL not set; PostgreSQL integration skipped")
class UserTablesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if make_url(TEST_URL).database != "dos_tres_test":
            raise RuntimeError("Integration tests require the dedicated dos_tres_test PostgreSQL database")
        with patch.dict(os.environ, {"DATABASE_URL": TEST_URL}):
            command.upgrade(Config("alembic.ini"), "head")
        cls.database = Database(TEST_URL)

    @classmethod
    def tearDownClass(cls):
        cls.database.dispose()

    def setUp(self):
        with self.database.sessions() as session:
            session.execute(delete(User))
            session.commit()

    tearDown = setUp

    def new_user(self, session):
        user = User()
        session.add(user)
        session.flush()
        return user

    def test_defaults(self):
        with self.database.sessions() as session:
            user = self.new_user(session)
            session.add(UserProfile(user_id=user.id, birth_year=2000, sex="여", sigungu_cd="12720", job="농어업"))
            session.commit()
            session.expire_all()
            self.assertEqual(session.get(User, user.id).status, "active")
            profile = session.get(UserProfile, user.id)
            self.assertEqual((profile.situations, profile.interests), ([], []))
            self.assertIsNotNone(profile.updated_at)

    def test_check_constraints(self):
        bad_rows = [
            lambda uid: UserProfile(user_id=uid, sex="기타"),
            lambda uid: UserProfile(user_id=uid, sigungu_cd="서울"),
            lambda uid: UserProfile(user_id=uid, birth_year=1800),
            lambda uid: UserConsent(user_id=uid, consent_type="marketing", version="v1"),
            lambda uid: CheckinResponse(user_id=uid, question_version=QUESTION_VERSION, answers={}, summary={},
                                        completed=False, source="phone"),
        ]
        for make in bad_rows:
            with self.subTest(row=make), self.database.sessions() as session:
                user = self.new_user(session)
                session.add(make(user.id))
                with self.assertRaises(IntegrityError):
                    session.flush()
                session.rollback()
        with self.database.sessions() as session, self.assertRaises(IntegrityError):
            session.add(User(status="deleted"))
            session.flush()

    def test_deleting_user_removes_personal_data(self):
        answers = {"economy": "high", "support": "high", "interests": ["마음건강·상담"]}
        with self.database.sessions() as session:
            user = self.new_user(session)
            session.add_all([
                UserProfile(user_id=user.id, sigungu_cd="11620", situations=["한부모가정"], interests=["집·주거"]),
                UserConsent(user_id=user.id, consent_type="sensitive_info", version="draft"),
                UserConsent(user_id=user.id, consent_type="checkin_storage", version="draft"),
                CheckinResponse(user_id=user.id, question_version=QUESTION_VERSION, answers=answers,
                                summary=summarize(answers), completed=False),
            ])
            session.commit()
            for model in (UserProfile, UserConsent, CheckinResponse):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 1 if model is not UserConsent else 2)
            session.delete(session.get(User, user.id))
            session.commit()
            for model in (UserProfile, UserConsent, CheckinResponse):
                self.assertEqual(session.scalar(select(func.count()).select_from(model)), 0, model.__tablename__)


if __name__ == "__main__":
    unittest.main()
