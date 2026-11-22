"""FE 빌드 화면 제공 (app/web.py). 가짜 dist 폴더로 확인한다."""
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


class WebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "index.html").write_text("<html>둘셋</html>", encoding="utf-8")
        (root / "assets").mkdir()
        (root / "assets" / "app-abc.js").write_text("console.log(1)", encoding="utf-8")
        self.client = TestClient(create_app(Settings(_env_file=None, web_dir=str(root))))

    def tearDown(self):
        self.tmp.cleanup()

    def test_serves_index_and_assets(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("둘셋", r.text)
        self.assertEqual(r.headers.get("cache-control"), "no-cache")
        self.assertEqual(self.client.get("/assets/app-abc.js").text, "console.log(1)")

    def test_unknown_page_falls_back_to_index(self):
        r = self.client.get("/policy/123")   # 새로고침해도 화면
        self.assertEqual(r.status_code, 200)
        self.assertIn("둘셋", r.text)

    def test_api_routes_win_and_unknown_api_is_json_404(self):
        self.assertEqual(self.client.get("/healthz").json(), {"status": "ok"})
        self.assertEqual(self.client.get("/api/regions").status_code, 200)
        r = self.client.get("/api/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json()["error"]["code"], "HTTP_404")

    def test_off_without_web_dir(self):
        client = TestClient(create_app(Settings(_env_file=None)))
        self.assertEqual(client.get("/").status_code, 404)


if __name__ == "__main__":
    unittest.main()
