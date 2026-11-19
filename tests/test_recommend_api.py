"""상태 체크·추천 API (DB 없이 → 서비스 JSON 대체 경로)."""
import unittest

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

PERSONA = {
    "profile": {"age": 24, "sex": "여", "sigungu_cd": "11620", "job": "구직 중", "situations": ["미혼"]},
    "checkin": {"economy": "mid", "participation": "high", "outing": "high", "conversation": "high",
                "support": "high", "change_wishes": ["E", "O", "C", "U"], "face_to_face": "mid",
                "interests": ["일자리·취업", "마음건강·상담"]},
}


class RecommendApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(Settings(_env_file=None, database_url="")))

    def test_questions_and_summary(self):
        questions = self.client.get("/api/checkin/questions")
        self.assertEqual(questions.status_code, 200)
        self.assertEqual(len(questions.json()["domain_questions"]), 5)
        summary = self.client.post("/api/checkin/summary", json={"answers": {"support": "high"}})
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["priority_domains"], ["U"])
        bad = self.client.post("/api/checkin/summary", json={"answers": {"support": "maybe"}})
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(bad.json()["error"]["code"], "HTTP_422")

    def test_recommendations_without_database_use_serving_files(self):
        response = self.client.post("/api/recommendations", json=PERSONA)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "file")
        self.assertTrue(1 <= len(data["policies"]) <= 6)
        self.assertTrue(1 <= len(data["programs"]) <= 4)
        first = data["policies"][0]
        for key in ("id", "title", "why", "domains", "access_type", "scope", "summary", "apply_url"):
            self.assertIn(key, first)
        self.assertTrue(first["why"])
        self.assertIn("확인", data["notice"])
        self.assertTrue(all(p["kind"] == "program" for p in data["programs"]))

    def test_income_condition_and_program_notice(self):
        data = self.client.post("/api/recommendations", json=PERSONA).json()
        self.assertIsNone(data["programs_notice"])   # 서울은 프로그램이 있다
        for p in data["policies"]:
            self.assertIn("income_condition", p)
        # 서울 밖 대부분은 센터 프로그램 데이터가 없다 → 0건 이유를 알린다
        daejeon = {**PERSONA, "profile": {**PERSONA["profile"], "sigungu_cd": "30170"}}
        data = self.client.post("/api/recommendations", json=daejeon).json()
        self.assertEqual(data["programs"], [])
        self.assertEqual(data["programs_notice"]["code"], "no_program_data")
        self.assertTrue(data["policies"])

    def test_same_input_same_result(self):
        a = self.client.post("/api/recommendations", json=PERSONA).json()
        b = self.client.post("/api/recommendations", json=PERSONA).json()
        self.assertEqual([p["id"] for p in a["policies"]], [p["id"] for p in b["policies"]])

    def test_validation(self):
        bad_region = {**PERSONA, "profile": {**PERSONA["profile"], "sigungu_cd": "서울"}}
        self.assertEqual(self.client.post("/api/recommendations", json=bad_region).status_code, 422)
        # 형식은 맞지만 원본에 없는 옛 코드 (광주·전남 통합 전 곡성 46720 → 지금은 12720)
        old_code = {**PERSONA, "profile": {**PERSONA["profile"], "sigungu_cd": "46720"}}
        response = self.client.post("/api/recommendations", json=old_code)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["message"], "Unknown sigungu_cd")
        new_code = {**PERSONA, "profile": {**PERSONA["profile"], "sigungu_cd": "12720"}}
        self.assertEqual(self.client.post("/api/recommendations", json=new_code).status_code, 200)
        bad_answer = {**PERSONA, "checkin": {"economy": "very"}}
        self.assertEqual(self.client.post("/api/recommendations", json=bad_answer).status_code, 422)
        self.assertIn("/api/recommendations", self.client.get("/openapi.json").json()["paths"])


if __name__ == "__main__":
    unittest.main()
