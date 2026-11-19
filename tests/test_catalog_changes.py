"""source_hash 계산과 변경 분류 (DB 없이 도는 단위 테스트)."""
import unittest

from app.catalog.load import plan_changes
from app.catalog.rows import changed_fields, content_hash, policy_row


class ContentHashTests(unittest.TestCase):
    def test_volatile_fields_do_not_change_hash(self):
        item = {"plcyNo": "1", "plcyNm": "정책", "inqCnt": 10, "lastMdfcnDt": "2026-11-01"}
        self.assertEqual(content_hash(item), content_hash({**item, "inqCnt": 999}))
        self.assertNotEqual(content_hash(item), content_hash({**item, "plcyNm": "정책(수정)"}))
        self.assertEqual(content_hash(item), content_hash(dict(reversed(list(item.items())))))   # 키 순서 무관
        self.assertEqual(len(content_hash(item)), 64)

    def test_policy_row_uses_content_hash(self):
        item = {"plcyNo": "1", "plcyNm": "정책", "inqCnt": 10}
        self.assertEqual(policy_row(item)["source_hash"], policy_row({**item, "inqCnt": 11})["source_hash"])

    def test_changed_fields(self):
        old = {"title": "a", "aply_end": "2026-12-01", "inqCnt": 1, "gone": 1}
        new = {"title": "b", "aply_end": "2026-12-01", "inqCnt": 2, "added": 1}
        self.assertEqual(changed_fields(old, new), ["added", "gone", "title"])


class PlanChangesTests(unittest.TestCase):
    def test_classifies_each_case(self):
        existing = {"a": ("h1", "ok"), "b": ("h2", "ok"), "c": ("h3", "closed"), "d": ("h4", "ok"), "e": ("h5", "closed")}
        rows = [{"id": "a", "source_hash": "h1"}, {"id": "b", "source_hash": "NEW"},
                {"id": "c", "source_hash": "h3"}, {"id": "n", "source_hash": "h9"}]
        plan = plan_changes(existing, rows)
        self.assertEqual(plan, {"created": ["n"], "updated": ["b"], "reopened": ["c"],
                                "unchanged": ["a"], "closed": ["d"]})   # 이미 닫힌 e 는 다시 닫지 않는다


if __name__ == "__main__":
    unittest.main()
