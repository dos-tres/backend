"""merge.py 단축 링크 풀기: 신청 링크가 bit.ly 등이면 최종 주소(구글폼 등)로 바꾼다. 네트워크는 쓰지 않는다."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline" / "programs" / "crawl"))

import merge  # noqa: E402

FORM = "https://docs.google.com/forms/d/e/TEST/viewform"


def orang_row(urls):
    return {"sprtInfoId": "1", "centers": "", "branch_name": "", "region_cds": "11110", "title": "t", "category": "",
            "status": "모집중", "aply_text": "", "aply_start": "", "aply_end": "", "prog_start": "", "prog_end": "",
            "prog_text": "", "place": "", "content": "", "content_urls": " ".join(urls), "list_url": "",
            "image_url": "", "first_seen": "", "last_seen": ""}


class ShortLinkTest(unittest.TestCase):
    def test_resolves_short_link_to_form(self):
        links = merge.ShortLinks(fetch=lambda u: FORM)
        row = merge.from_orang(orang_row(["https://bit.ly/abc", "https://www.instagram.com/x"]), links)
        self.assertEqual(row["apply_urls"], FORM)

    def test_resolved_non_form_is_not_a_form(self):
        # naver.me → 지도처럼 신청폼이 아닌 곳이면 신청폼으로 치지 않는다 (링크 앞 2개로 대체)
        links = merge.ShortLinks(fetch=lambda u: "https://map.naver.com/p/1")
        row = merge.from_orang(orang_row(["https://naver.me/abc"]), links)
        self.assertEqual(row["apply_urls"], "https://map.naver.com/p/1")
        self.assertFalse(merge.is_form("https://map.naver.com/p/1"))

    def test_unresolved_short_link_stays_as_form_candidate(self):
        links = merge.ShortLinks(fetch=lambda u: None)
        row = merge.from_orang(orang_row(["https://www.instagram.com/x", "https://zrr.kr/abc"]), links)
        self.assertEqual(row["apply_urls"], "https://zrr.kr/abc")
        self.assertEqual(links.failed, 1)

    def test_non_short_links_are_not_fetched(self):
        calls = []
        links = merge.ShortLinks(fetch=lambda u: calls.append(u))
        links.resolve(FORM)
        links.resolve("https://youth.seoul.go.kr/crm/front/index.do")
        self.assertEqual(calls, [])

    def test_cache_is_used_and_saved(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "short.json"
            path.write_text(json.dumps({"https://bit.ly/old": FORM}), encoding="utf-8")
            calls = []
            links = merge.ShortLinks(path, fetch=lambda u: calls.append(u) or "https://form.naver.com/response/x")
            self.assertEqual(links.resolve("https://bit.ly/old"), FORM)
            self.assertEqual(links.resolve("https://naver.me/new"), "https://form.naver.com/response/x")
            self.assertEqual(calls, ["https://naver.me/new"])
            links.save()
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(set(saved), {"https://bit.ly/old", "https://naver.me/new"})

    def test_failure_is_not_cached(self):
        links = merge.ShortLinks(fetch=lambda u: None)
        links.resolve("https://bit.ly/x")
        self.assertEqual(links.cache, {})

    def test_gnuboard_uses_resolver(self):
        links = merge.ShortLinks(fetch=lambda u: FORM)
        post = {"posted_at": "2026-11-01", "first_seen": "2026-11-01", "list_text": "", "title": "모집",
                "content": "신청: https://bit.ly/abc", "region_cds": "43150", "site": "s", "bo_table": "b",
                "wr_id": "1", "board_kind": "program", "centers": "", "center_names": "c", "note": "",
                "image_urls": "", "board_label": "프로그램", "last_seen": "", "url": ""}
        self.assertEqual(merge.from_gnuboard(post, links)["apply_urls"], FORM)

    def test_js_redirect_pattern(self):
        html = '<meta http-equiv="refresh" content="0; url=https://docs.google.com/forms/d/e/X/viewform">'
        self.assertEqual(merge.JS_REDIRECT_RE.search(html).group(1), "https://docs.google.com/forms/d/e/X/viewform")
        self.assertEqual(merge.JS_REDIRECT_RE.search('location.href = "https://a.kr/p"').group(1), "https://a.kr/p")


if __name__ == "__main__":
    unittest.main()
