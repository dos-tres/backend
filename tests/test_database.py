import os
import unittest
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from fastapi import Depends
from fastapi.testclient import TestClient
from dotenv import dotenv_values
from pydantic import ValidationError
from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import Settings
from app.database import Database, get_db
from app.main import create_app

TEST_URL = os.environ.get("TEST_DATABASE_URL", dotenv_values(".env").get("TEST_DATABASE_URL"))


class DatabaseUnitTests(unittest.TestCase):
    def test_unconfigured_database_keeps_liveness(self):
        app = create_app(Settings(_env_file=None, database_url=""))
        with TestClient(app) as client:
            self.assertEqual(client.get("/healthz").status_code, 200)
            response = client.get("/readyz")
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"error": {
                "code": "DATABASE_UNAVAILABLE", "message": "Database unavailable"}})
            self.assertIn("/readyz", client.get("/openapi.json").json()["paths"])

    def test_database_setting_is_secret_and_postgresql_only(self):
        url = "postgresql+psycopg://user:private-password@localhost/test"
        settings = Settings(_env_file=None, database_url=url)
        self.assertNotIn("private-password", repr(settings))
        with self.assertRaises(ValidationError) as caught:
            Settings(_env_file=None, database_url="sqlite:///private-password")
        self.assertNotIn("private-password", str(caught.exception))


@unittest.skipUnless(TEST_URL, "TEST_DATABASE_URL not set; PostgreSQL integration skipped")
class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = TEST_URL
        parsed = make_url(cls.url)
        # Refuse migrations against a development DB, even if misconfigured.
        if parsed.database != "dos_tres_test" or parsed.drivername != "postgresql+psycopg":
            raise RuntimeError("Integration tests require the dedicated dos_tres_test PostgreSQL database")
        development_url = Settings().database_url.get_secret_value()
        if development_url and make_url(development_url) == parsed:
            raise RuntimeError("Test and development database URLs must differ")

    def test_migrations_upgrade_downgrade_and_catalog_table(self):
        config = Config("alembic.ini")
        with patch.dict(os.environ, {"DATABASE_URL": self.url}):
            command.upgrade(config, "head")
            database = Database(self.url)
            try:
                with database.engine.connect() as connection:
                    self.assertEqual(connection.scalar(text("SELECT version_num FROM alembic_version")), "0004")
                    self.assertEqual(sorted(inspect(connection).get_table_names()),
                                     ["alembic_version", "catalog_item_changes", "catalog_items", "checkin_responses",
                                      "user_consents", "user_profiles", "users"])
                command.check(config)
                command.downgrade(config, "base")
                with database.engine.connect() as connection:
                    self.assertEqual(connection.scalar(text("SELECT count(*) FROM alembic_version")), 0)
                command.upgrade(config, "head")
                command.upgrade(config, "head")
            finally:
                database.dispose()

    def test_readiness_session_cleanup_and_shutdown(self):
        app = create_app(Settings(_env_file=None, database_url=self.url))
        api = app.app
        sessions = []
        observer = Database(self.url)
        try:
            before = inspect(observer.engine).get_table_names()
        finally:
            observer.dispose()

        @api.get("/test-session")
        def session_route(session: Session = Depends(get_db)):
            sessions.append(session)
            # This local setting would leak to a reused connection without rollback.
            session.execute(text("SET LOCAL application_name = 'uncommitted-test'"))
            raise RuntimeError("test-only failure")

        with patch.object(Database, "dispose", autospec=True, side_effect=Database.dispose) as dispose:
            with TestClient(app, raise_server_exceptions=False) as client:
                database = api.state.database
                response = client.get("/readyz")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"status": "ok"})
                self.assertEqual(inspect(database.engine).get_table_names(), before)
                self.assertEqual(client.get("/test-session").status_code, 500)
                self.assertEqual(client.get("/test-session").status_code, 500)
                self.assertIsNot(sessions[0], sessions[1])
                self.assertEqual(database.engine.pool.checkedout(), 0)
                with database.sessions() as session:
                    self.assertNotEqual(session.scalar(text("SHOW application_name")), "uncommitted-test")
            dispose.assert_called_once_with(database)
            self.assertIsNone(api.state.database)

    def test_real_connection_failure_is_sanitized(self):
        # PostgreSQL is reachable but this role cannot authenticate.
        broken_url = make_url(self.url).set(username="nonexistent_test_role", password="private-test-value")
        app = create_app(Settings(_env_file=None, database_url=broken_url.render_as_string(hide_password=False)))
        with TestClient(app) as client:
            response = client.get("/readyz", headers={"Origin": "http://localhost:5173"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {"error": {
                "code": "DATABASE_UNAVAILABLE", "message": "Database unavailable"}})
            self.assertNotIn("private-test-value", response.text)
            self.assertNotIn("nonexistent_test_role", response.text)
            self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
            self.assertEqual(client.get("/healthz").status_code, 200)
