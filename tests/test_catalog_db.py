"""catalog_items 적재·조회 (PostgreSQL 통합 테스트, TEST_DATABASE_URL 필요)."""
import json
import os
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url

from app.catalog.load import upsert_catalog
from app.catalog.models import CatalogItem, CatalogItemChange
from app.catalog.repository import from_db, from_files
from app.catalog.rows import build_rows
from app.config import Settings
from app.database import Database
from app.main import create_app

TEST_URL = os.environ.get("TEST_DATABASE_URL", dotenv_values(".env").get("TEST_DATABASE_URL"))
SEED = Path(__file__).resolve().parents[1] / "data" / "seed" / "serving"
TODAY = date(2026, 11, 19)


def seed_rows(kind):
    name = "policies_serving.json" if kind == "policy" else "programs_serving.json"
    return build_rows(kind, json.loads((SEED / name).read_text(encoding="utf-8")))


@unittest.skipUnless(TEST_URL, "TEST_DATABASE_URL not set; PostgreSQL integration skipped")
class CatalogDatabaseTests(unittest.TestCase):
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
            session.execute(delete(CatalogItemChange))
            session.execute(delete(CatalogItem))
            session.commit()

    tearDown = setUp

    def count(self, session, **where):
        stmt = select(func.count()).select_from(CatalogItem)
        for key, value in where.items():
            stmt = stmt.where(getattr(CatalogItem, key) == value)
        return session.scalar(stmt)

    def test_upsert_close_missing_and_guard(self):
        policies = seed_rows("policy")
        with self.database.sessions() as session:
            result = upsert_catalog(session, "policy", policies)
            session.commit()
            self.assertEqual(result["created"], len(policies))
            self.assertEqual(self.count(session, kind="policy", status="ok"), len(policies))

            # 같은 데이터를 다시 넣어도 행이 늘지 않는다 (upsert)
            result = upsert_catalog(session, "policy", policies)
            session.commit()
            self.assertEqual(self.count(session), len(policies))
            self.assertEqual(result["unchanged"], len(policies))

            # 일부가 빠지면 closed 로 바뀌고 행은 남는다
            kept = policies[: int(len(policies) * 0.8)]
            result = upsert_catalog(session, "policy", kept)
            session.commit()
            self.assertEqual(result["closed"], len(policies) - len(kept))
            self.assertEqual(self.count(session, status="closed"), len(policies) - len(kept))

            # 건수가 절반 아래로 줄면 수집 이상으로 보고 중단 (기존 데이터 유지)
            with self.assertRaises(RuntimeError):
                upsert_catalog(session, "policy", policies[:10])
            session.rollback()
            self.assertEqual(self.count(session, status="ok"), len(kept))

    def history(self, session, item_id):
        return session.scalars(select(CatalogItemChange).where(CatalogItemChange.item_id == item_id)
                               .order_by(CatalogItemChange.id)).all()

    def test_change_history(self):
        programs = seed_rows("program")
        target = programs[0]
        with self.database.sessions() as session:
            upsert_catalog(session, "program", programs)
            session.commit()
            before = session.get(CatalogItem, target["id"]).updated_at
            self.assertEqual([c.change_type for c in self.history(session, target["id"])], ["created"])

            # 같은 데이터 → 이력·updated_at 그대로
            upsert_catalog(session, "program", programs)
            session.commit()
            session.expire_all()
            self.assertEqual(len(self.history(session, target["id"])), 1)
            self.assertEqual(session.get(CatalogItem, target["id"]).updated_at, before)

            # 제목이 바뀌면 updated 이력에 이전 payload·바뀐 필드가 남는다
            new_payload = {**target["payload"], "title": target["payload"]["title"] + " (수정)"}
            changed = build_rows("program", {"programs": [new_payload]})[0]
            result = upsert_catalog(session, "program", [changed, *programs[1:]])
            session.commit()
            session.expire_all()
            self.assertEqual(result["updated"], 1)
            last = self.history(session, target["id"])[-1]
            self.assertEqual(last.change_type, "updated")
            self.assertEqual(last.changed_fields, ["title"])
            self.assertEqual(last.old_payload["title"], target["payload"]["title"])
            row = session.get(CatalogItem, target["id"])
            self.assertEqual(row.title, changed["title"])
            self.assertGreater(row.updated_at, before)

            # 빠지면 closed, 다시 나타나면 reopened
            upsert_catalog(session, "program", programs[1:])
            upsert_catalog(session, "program", programs)
            session.commit()
            session.expire_all()
            types =[c.change_type for c in self.history(session, target["id"])]
            self.assertEqual(types, ["created", "updated", "closed", "reopened"])
            reopened = self.history(session, target["id"])[-1]
            self.assertEqual(reopened.changed_fields, ["title"])   # 닫히기 전 수정본 → 원래 제목으로 돌아옴
            self.assertEqual(session.get(CatalogItem, target["id"]).status, "ok")

    def test_volatile_field_updates_payload_without_history(self):
        policies = seed_rows("policy")
        target = policies[0]
        with self.database.sessions() as session:
            upsert_catalog(session, "policy", policies)
            session.commit()
            before = session.get(CatalogItem, target["id"]).updated_at
            bumped = build_rows("policy", {"policies": [{**target["payload"],
                                                         "inqCnt": (target["payload"].get("inqCnt") or 0) + 7}]})[0]
            self.assertEqual(bumped["source_hash"], target["source_hash"])
            result = upsert_catalog(session, "policy", [bumped, *policies[1:]])
            session.commit()
            session.expire_all()
            self.assertEqual(result["unchanged"], len(policies))
            row = session.get(CatalogItem, target["id"])
            self.assertEqual(row.payload["inqCnt"], bumped["payload"]["inqCnt"])
            self.assertEqual(row.updated_at, before)
            self.assertEqual(len(self.history(session, target["id"])), 1)

    def test_derived_column_change_is_written_without_history(self):
        """원본은 같은데 변환 규칙이 바뀌어 파생 컬럼(deadline)만 달라져도 DB에 반영된다."""
        policies = seed_rows("policy")
        target = next(r for r in policies if r["deadline"] is not None)
        with self.database.sessions() as session:
            upsert_catalog(session, "policy", policies)
            session.commit()
            old_rule = {**target, "deadline": None}   # 예전 규칙으로 만든 행이 DB에 있는 상황
            upsert_catalog(session, "policy", [old_rule if r["id"] == target["id"] else r for r in policies])
            session.commit()
            result = upsert_catalog(session, "policy", policies)
            session.commit()
            session.expire_all()
            self.assertEqual(result["unchanged"], len(policies))
            self.assertEqual(session.get(CatalogItem, target["id"]).deadline, target["deadline"])
            self.assertEqual(len(self.history(session, target["id"])), 1)   # created 만

    def test_db_query_matches_file_fallback(self):
        with self.database.sessions() as session:
            upsert_catalog(session, "policy", seed_rows("policy"))
            upsert_catalog(session, "program", seed_rows("program"))
            session.commit()
            for sigungu, age in (("11620", 24), ("30200", 31), ("41117", 19), ("26350", 36)):
                db_ids = {r["id"] for r in from_db(session, sigungu, age, TODAY)}
                file_ids = {r["id"] for r in from_files(sigungu, age, TODAY)}
                self.assertEqual(db_ids, file_ids, sigungu)

    def test_api_uses_database_when_loaded(self):
        with self.database.sessions() as session:
            upsert_catalog(session, "policy", seed_rows("policy"))
            upsert_catalog(session, "program", seed_rows("program"))
            session.commit()
        app = create_app(Settings(_env_file=None, database_url=TEST_URL))
        body = {"profile": {"age": 24, "sex": "여", "sigungu_cd": "11620", "job": "구직 중"},
                "checkin": {"support": "high", "interests": ["마음건강·상담"]}}
        with TestClient(app) as client:
            data = client.post("/api/recommendations", json=body).json()
        self.assertEqual(data["source"], "db")
        self.assertTrue(data["policies"])


if __name__ == "__main__":
    unittest.main()
