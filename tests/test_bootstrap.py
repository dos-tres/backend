import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(_env_file=None))
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def test_health_and_docs(self):
        response = self.client.get("/healthz")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("swagger-ui", self.client.get("/docs").text)
        self.assertIn("/healthz", self.client.get("/openapi.json").json()["paths"])

    def test_http_errors(self):
        self.assertEqual(self.client.get("/missing").json(), {
            "error": {"code": "HTTP_404", "message": "Not Found"}})
        response = self.client.post("/healthz")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json()["error"]["code"], "HTTP_405")
        self.assertIn("GET", response.headers["allow"])

    def test_validation_and_internal_errors(self):
        # Test-only routes; these are never exposed by the production app.
        api = self.app.app

        @api.get("/validated")
        def validated(count: int):
            return {"count": count}

        @api.get("/broken")
        def broken():
            raise RuntimeError("private-value")

        @api.get("/unauthorized")
        def unauthorized():
            raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})

        response = self.client.get("/validated?count=secret")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertNotIn("secret", response.text)
        response = self.client.get("/broken", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["error"]["code"], "INTERNAL_SERVER_ERROR")
        self.assertNotIn("private-value", response.text)
        self.assertEqual(response.headers["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(self.client.get("/unauthorized").headers["www-authenticate"], "Bearer")

    def test_cors(self):
        for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
            response = self.client.options("/healthz", headers={
                "Origin": origin, "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Content-Type"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], origin)
            self.assertNotIn("access-control-allow-credentials", response.headers)
        response = self.client.options("/healthz", headers={
            "Origin": "https://untrusted.example", "Access-Control-Request-Method": "GET"})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            env = Path(directory) / ".env"
            env.write_text('APP_ENV=staging\nALLOWED_ORIGINS=["https://preview.example"]\n')
            with patch.dict(os.environ, {}, clear=True):
                self.assertEqual(Settings(_env_file=env).app_env, "staging")
                with patch.dict(os.environ, {"APP_ENV": "production"}):
                    settings = Settings(_env_file=env)
                    self.assertEqual(settings.app_env, "production")
                    self.assertEqual(settings.allowed_origins, ["https://preview.example"])
        for origin in ("*", "https://example.com/path", "https://user@example.com", "https://example.com:bad"):
            with self.subTest(origin=origin), self.assertRaises(ValidationError):
                Settings(_env_file=None, allowed_origins=[origin])
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, app_env="invalid")


if __name__ == "__main__":
    unittest.main()
