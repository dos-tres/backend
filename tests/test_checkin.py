import unittest

from app.checkin.questions import DOMAIN_QUESTIONS, all_questions
from app.checkin.summary import CheckinError, summarize

ALL_HIGH = {q["id"]: "high" for q in DOMAIN_QUESTIONS}


class CheckinSummaryTests(unittest.TestCase):
    def test_questions_cover_five_domains_with_skip_options(self):
        data = all_questions()
        self.assertEqual([q["domain"] for q in data["domain_questions"]], ["E", "P", "O", "C", "U"])
        self.assertEqual({o["code"] for o in data["common_options"]}, {"unknown", "skip", "later"})
        self.assertIn("진단이 아니", data["notice"])

    def test_levels_follow_own_answers_without_score_or_grade(self):
        result = summarize({"economy": "high", "outing": "mid", "support": "low"})
        self.assertEqual(result["levels"], {"E": "high", "O": "mid", "U": "low"})
        self.assertEqual(result["priority_domains"], ["E", "O"])
        self.assertEqual(result["unanswered_domains"], ["P", "C"])
        for key in ("score", "total", "risk", "grade"):
            self.assertNotIn(key, result)

    def test_unknown_skip_later_are_excluded(self):
        result = summarize({"economy": "unknown", "participation": "skip", "outing": "later", "conversation": "high"})
        self.assertEqual(result["priority_domains"], ["C"])
        self.assertEqual(result["unanswered_domains"], ["E", "P", "O", "U"])

    def test_not_wanting_change_lowers_domain(self):
        result = summarize({**ALL_HIGH, "change_wishes": ["E", "U"]})
        self.assertEqual(result["levels"]["C"], "mid")
        self.assertEqual(result["levels"]["E"], "high")
        self.assertEqual(result["priority_domains"][:2], ["E", "U"])
        self.assertEqual(set(result["lowered_domains"]), {"P", "O", "C"})
        none = summarize({**ALL_HIGH, "change_wishes": ["none"]})
        self.assertTrue(all(level == "mid" for level in none["levels"].values()))

    def test_no_regular_activity_also_raises_jobs(self):
        result = summarize({"participation": "high", "economy": "low"})
        self.assertEqual(result["levels"]["E"], "mid")
        self.assertEqual(result["priority_domains"], ["P", "E"])

    def test_invalid_answers(self):
        with self.assertRaises(CheckinError) as caught:
            summarize({"economy": "very", "mystery": "x", "interests": ["a", "b"],
                       "change_wishes": ["none", "E"]})
        self.assertEqual(set(caught.exception.errors), {"economy", "mystery", "interests", "change_wishes"})
        with self.assertRaises(CheckinError):
            summarize({"interests": ["창업", "집·주거", "문화·여가", "해외 경험"]})


if __name__ == "__main__":
    unittest.main()
