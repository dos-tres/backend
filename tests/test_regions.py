"""거주지 선택 목록(/api/regions)과 옛 코드 매칭 (DB 없이 → 서비스 JSON 대체 경로)."""
import unittest
from datetime import date

from fastapi.testclient import TestClient

from app.catalog.regions import LEGACY, REGION_CODES, REGIONS, match_codes
from app.catalog.repository import data_region_codes, from_files
from app.config import Settings
from app.main import create_app

TODAY = date(2026, 11, 20)


class RegionListTests(unittest.TestCase):
    def test_list_matches_data(self):
        # 서비스 데이터에 나오는 코드는 모두 목록 또는 옛 코드 표에 있어야 한다 (새 코드가 생기면 여기서 실패)
        self.assertEqual(data_region_codes() - REGION_CODES - set(LEGACY), set())
        self.assertFalse(REGION_CODES & set(LEGACY))
        for new_codes in LEGACY.values():
            self.assertLessEqual(set(new_codes), REGION_CODES)

    def test_list_shape(self):
        self.assertEqual(len(REGIONS), len(REGION_CODES))
        for code, sido, sigungu in REGIONS:
            self.assertRegex(code, r"^\d{5}$")
            self.assertTrue(sido and sigungu, code)
        labels = {code: f"{sido} {sigungu}" for code, sido, sigungu in REGIONS}
        self.assertEqual(labels["12720"], "전남광주통합특별시 곡성군")
        self.assertEqual(labels["41597"], "경기도 화성시 동탄구")
        self.assertEqual(labels["28290"], "인천광역시 검단구")
        self.assertEqual(labels["51110"], "강원특별자치도 춘천시")
        self.assertNotIn("41590", REGION_CODES)   # 일반구가 있는 시는 구 코드만

    def test_match_codes(self):
        self.assertEqual(match_codes("11440"), ("11440",))
        self.assertEqual(set(match_codes("41597")), {"41597", "41590"})
        self.assertEqual(set(match_codes("28125")), {"28125", "28110", "28140"})
        self.assertEqual(set(match_codes("30200")), {"30200", "30000"})

    def test_legacy_policies_reach_new_districts(self):
        # 화성시(41590)·천안시(44130)로만 표시된 정책이 구 단위 사용자에게도 나온다
        for new, old in (("41597", "41590"), ("44131", "44130")):
            ids = {r["id"] for r in from_files(new, 25, TODAY) if r["kind"] == "policy"}
            legacy_only = {r["id"] for r in from_files(old, 25, TODAY) if r["kind"] == "policy"}
            self.assertTrue(legacy_only, old)
            self.assertLessEqual(legacy_only, ids, new)


class RegionApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(Settings(_env_file=None, database_url="")))

    def test_regions_endpoint(self):
        response = self.client.get("/api/regions")
        self.assertEqual(response.status_code, 200)
        regions = response.json()["regions"]
        self.assertEqual(len(regions), len(REGIONS))
        self.assertIn({"code": "11440", "sido": "서울특별시", "sigungu": "마포구", "label": "서울특별시 마포구"}, regions)

    def test_every_listed_code_is_accepted(self):
        body = {"profile": {"age": 25}, "checkin": {"economy": "high"}}
        for region in self.client.get("/api/regions").json()["regions"]:
            body["profile"]["sigungu_cd"] = region["code"]
            self.assertEqual(self.client.post("/api/recommendations", json=body).status_code, 200, region)
        for old in ("41590", "44130", "30000", "46720"):
            body["profile"]["sigungu_cd"] = old
            self.assertEqual(self.client.post("/api/recommendations", json=body).status_code, 422, old)


if __name__ == "__main__":
    unittest.main()
