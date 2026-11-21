"""LLM 사용량 제한 (app/limits.py, 대화·초안)."""
import unittest
from datetime import date

from fastapi.testclient import TestClient

from app.config import Settings
from app.limits import RateLimited, UsageLimiter
from app.main import create_app


class Clock:
    def __init__(self):
        self.t, self.d = 1000.0, date(2026, 11, 22)


class LimiterTests(unittest.TestCase):
    def test_per_minute_window(self):
        c = Clock()
        lim = UsageLimiter(2, 0, 0, clock=lambda: c.t, today=lambda: c.d)
        lim.hit("a")
        lim.hit("a")
        with self.assertRaises(RateLimited) as ctx:
            lim.hit("a")
        self.assertEqual(ctx.exception.scope, "minute")
        lim.hit("b")              # 다른 접속자는 따로
        c.t += 61
        lim.hit("a")              # 1분 지나면 다시

    def test_per_day_and_total_reset_next_day(self):
        c = Clock()
        lim = UsageLimiter(0, 2, 3, clock=lambda: c.t, today=lambda: c.d)
        lim.hit("a")
        lim.hit("a")
        with self.assertRaises(RateLimited):
            lim.hit("a")
        lim.hit("b")
        with self.assertRaises(RateLimited) as ctx:
            lim.hit("c")          # 서버 전체 3회
        self.assertEqual(ctx.exception.scope, "total")
        c.d = date(2026, 11, 23)
        lim.hit("a")


class ApiLimitTests(unittest.TestCase):
    def test_chat_429_but_crisis_always_answers(self):
        client = TestClient(create_app(Settings(_env_file=None, llm_limit_per_minute=1)))
        msg = {"messages": [{"role": "user", "content": "안녕하세요"}]}
        self.assertEqual(client.post("/api/chat", json=msg).status_code, 503)   # LLM 없음 (1회 사용)
        r = client.post("/api/chat", json=msg)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["error"]["code"], "RATE_LIMITED")
        self.assertIn("Retry-After", r.headers)
        crisis = client.post("/api/chat", json={"messages": [{"role": "user", "content": "죽고 싶어요"}]})
        self.assertEqual(crisis.status_code, 200)
        self.assertEqual(crisis.json()["mode"], "crisis")

    def test_draft_is_limited(self):
        client = TestClient(create_app(Settings(_env_file=None, llm_limit_per_minute=1)))
        body = {"item_id": "x", "question_id": "q1"}
        self.assertEqual(client.post("/api/apply/draft", json=body).status_code, 404)
        self.assertEqual(client.post("/api/apply/draft", json=body).status_code, 429)


if __name__ == "__main__":
    unittest.main()
