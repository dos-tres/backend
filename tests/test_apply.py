"""챗봇으로 신청하기 ① 대신 제출 (docs/APPLY.md). 가짜 구글폼 페이지·가짜 제출·가짜 LLM 으로 확인한다 (네트워크·키·DB 불필요).

폼 페이지는 실제 테스트 폼과 같은 구조로 만든 가짜 값이다(실제 폼 주소·번호 아님).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

from app.apply import fill, gform
from app.config import Settings
from app.main import create_app

FORM_ID = "FAKEFORMID_abc-123"
VIEW = f"https://docs.google.com/forms/d/e/{FORM_ID}/viewform"
CLOSED = f"https://docs.google.com/forms/d/e/{FORM_ID}/closedform"
CONSENT = "[개인정보 동의 내용]\n■ 수집·이용 목적: 테스트"
ITEMS = [
    [1, "성명", None, 0, [[101, None, 1]]],
    [2, "만 나이", None, 0, [[102, None, 1, None, [[1, 7, ["0.0", "120.0"], "숫자만 적어 주세요."]]]]],
    [3, "성별", None, 2, [[103, [["남"], ["여"]], 1]]],
    [4, "연락처", "ex) 010-xxxx-xxxx", 0, [[104, None, 1]]],
    [5, "거주지역 (ex.OO구 OO동) (반드시 \"동\"까지 필수기재 해주세요!)", None, 1, [[105, None, 1]]],
    [6, "베이킹 클래스에 신청하신 이유를 적어주세요 !", "정성껏 작성해주세요", 1, [[106, None, 1]]],
    [7, "프로그램을 알게 된 경로를 알려주세요.", None, 2,
     [[107, [["센터 블로그"], ["지인추천"], [None, None, None, None, 1]], 0]]],
    [8, "안내", "설명 글", 6, None],
    [9, "개인정보 수집·이용 동의 여부", CONSENT, 2, [[109, [["동의합니다."], ["동의하지 않습니다."]], 1]]],
]


def page(items=ITEMS, title="[둘셋 테스트] 베이킹 클래스"):
    info = ["설명입니다", items, None, None, None, None, None, None, title]
    data = [None, info, "/forms", title]
    return (f'<html><script>var FB_PUBLIC_LOAD_DATA_ = {json.dumps(data, ensure_ascii=False)};</script>'
            f'<form action="https://docs.google.com/forms/d/e/{FORM_ID}/formResponse" method="POST">'
            f'<input type="hidden" name="entry.103_sentinel" value="">'
            f'<input type="hidden" name="partialResponse" value="[null,null,&quot;-123&quot;]">'
            f'<input type="hidden" name="fbzx" value="-123"></html>')


CLOSED_PAGE = "<div class='a'>[둘셋 테스트] 상담 신청서</div><div class='b'>예산 소진으로 더 이상 신청을 받지 않습니다.</div>"


def response(text, url, status=200):
    r = MagicMock()
    r.text, r.url, r.status_code = text, url, status
    return r


PROFILE = {"age": 24, "sex": "여", "sigungu_cd": "11620", "job": "구직 중"}
APPLICANT = {"name": "김둘셋", "birth_date": "2002-03-05", "phone": "010-0000-0000"}
FULL = {"q1": "김둘셋", "q2": "24", "q3": "여", "q4": "010-0000-0000", "q5": "관악구 신림동",
        "q6": "사람들과 함께 무언가를 만들어 보고 싶습니다.", "q8": "동의합니다."}


class ParseTests(unittest.TestCase):
    def test_reads_questions(self):
        form = gform.parse(page(), VIEW)
        self.assertEqual([q.kind for q in form.questions], ["short", "short", "choice", "short", "long", "long",
                                                            "choice", "agree"])   # 설명 글은 빠짐
        self.assertEqual(form.questions[1].hint, "숫자만 적어 주세요.")
        self.assertTrue(form.questions[6].other)
        self.assertFalse(form.questions[6].required)
        self.assertEqual(form.questions[7].description, CONSENT)
        self.assertEqual(form.submit_url, f"https://docs.google.com/forms/d/e/{FORM_ID}/formResponse")
        self.assertEqual(form.fbzx, "-123")

    def test_closed_form_with_message(self):
        with self.assertRaises(gform.FormClosed) as ctx:
            gform.parse(CLOSED_PAGE, CLOSED)
        self.assertEqual(ctx.exception.message, "예산 소진으로 더 이상 신청을 받지 않습니다.")

    def test_login_required_and_unsupported(self):
        with self.assertRaises(gform.FormNotSupported):
            gform.parse("<html></html>", "https://accounts.google.com/v3/signin/identifier?continue=x")
        with self.assertRaises(gform.FormNotSupported):
            gform.parse(page(ITEMS + [[10, "", None, 8, None]]), VIEW)            # 여러 페이지
        with self.assertRaises(gform.FormNotSupported):
            gform.parse(page(ITEMS + [[11, "파일", None, 13, [[111, None, 1]]]]), VIEW)   # 파일 올리기
        with self.assertRaises(gform.FormUnreachable):
            gform.parse("<html>no data</html>", VIEW)


class FillTests(unittest.TestCase):
    def test_fills_known_and_never_consent(self):
        form = gform.parse(page(), VIEW)
        filled, ask = fill.split(form.questions, APPLICANT, PROFILE)
        self.assertEqual({f["question_id"]: f["value"] for f in filled},
                         {"q1": "김둘셋", "q2": "24", "q3": "여", "q4": "010-0000-0000"})
        asked = {a["question"].id: a for a in ask}
        self.assertEqual(set(asked), {"q5", "q6", "q7", "q8"})
        self.assertEqual(asked["q5"]["prefill"], "관악구 ")       # 동까지 요구 → 구까지만 채우고 묻는다
        self.assertTrue(asked["q6"]["can_draft"])
        self.assertFalse(asked["q5"]["can_draft"])
        self.assertEqual(asked["q8"]["question"].kind, "agree")

    def test_without_info_asks_everything_and_sex_only_if_option_matches(self):
        form = gform.parse(page(), VIEW)
        filled, ask = fill.split(form.questions, None, {"age": 24, "sex": None, "sigungu_cd": "11620"})
        self.assertEqual([f["question_id"] for f in filled], ["q2"])
        self.assertIn("q1", [a["question"].id for a in ask])

    def test_personal_questions_carry_fill_key_without_applicant(self):
        # applicant 를 안 보내도 FE 가 기기 값으로 채울 칸을 알 수 있다 (개인정보가 start 로 오지 않음)
        form = gform.parse(page(), VIEW)
        filled, ask = fill.split(form.questions, None, PROFILE)
        keys = {a["question"].id: a["fill_key"] for a in ask}
        self.assertEqual(keys["q1"], "name")
        self.assertEqual(keys["q4"], "phone")
        self.assertIsNone(keys["q6"])
        self.assertEqual(next(f for f in filled if f["question_id"] == "q2")["fill_key"], "age")
        filled, _ = fill.split(form.questions, APPLICANT, PROFILE)
        self.assertEqual(next(f for f in filled if f["question_id"] == "q1")["fill_key"], "name")


class PayloadTests(unittest.TestCase):
    def setUp(self):
        self.form = gform.parse(page(), VIEW)

    def test_payload_and_other_option(self):
        payload = gform.build_payload(self.form, {**FULL, "q7": "친구가 알려 줌"})
        self.assertIn(("entry.101", "김둘셋"), payload)
        self.assertIn(("entry.107", gform.OTHER), payload)
        self.assertIn(("entry.107.other_option_response", "친구가 알려 줌"), payload)
        self.assertIn(("entry.109", "동의합니다."), payload)

    def test_missing_and_invalid(self):
        with self.assertRaises(gform.InvalidAnswers) as ctx:
            gform.build_payload(self.form, {**FULL, "q3": "모름", "q8": None})
        self.assertEqual(ctx.exception.missing, ["q8"])
        self.assertEqual(ctx.exception.invalid, ["q3"])


class RegistryTests(unittest.TestCase):
    def test_env_json_and_file_merge(self):
        from app.apply import registry
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "forms.local.json"
            path.write_text(json.dumps({"_note": "x", "a": {"form_url": "file-a"}, "b": {"form_url": "file-b"}}),
                            encoding="utf-8")
            forms = registry.load(str(path), json.dumps({"b": {"form_url": "env-b"}, "c": {"form_url": "env-c"}}))
        self.assertEqual({k: v["form_url"] for k, v in forms.items()}, {"a": "file-a", "b": "env-b", "c": "env-c"})
        self.assertEqual(registry.load("", "not json"), {})
        self.assertEqual(registry.load("missing.json", ""), {})
        settings = Settings(_env_file=None, apply_forms_json=json.dumps({"demo:open": {"form_url": VIEW}}))
        self.assertEqual(list(registry.from_settings(settings)), ["demo:open"])


class FakeModel:
    def __init__(self, data):
        self.data, self.calls = data, []

    def complete_json(self, system, messages):
        self.calls.append((system, messages))
        return self.data


class ApplyApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / "forms.local.json"
        path.write_text(json.dumps({"_note": "x", "demo:open": {"form_url": VIEW}}), encoding="utf-8")
        self.app = create_app(Settings(_env_file=None, apply_forms_path=str(path)))
        self.client = TestClient(self.app)
        self.get = patch.object(gform.requests, "get", return_value=response(page(), VIEW)).start()
        self.post = patch.object(gform.requests, "post", return_value=response("ok", VIEW, 200)).start()

    def tearDown(self):
        patch.stopall()
        self.tmp.cleanup()

    def test_start_fills_and_asks(self):
        r = self.client.post("/api/apply/start", json={"item_id": "demo:open", "applicant": APPLICANT,
                                                       "profile": PROFILE})
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["available"])
        self.assertEqual(d["channel"], "form")
        self.assertEqual([f["question_id"] for f in d["filled"]], ["q1", "q2", "q3", "q4"])
        q = {x["id"]: x for x in d["questions"]}
        self.assertEqual(q["q5"]["prefill"], "관악구 ")
        self.assertTrue(q["q6"]["can_draft"])
        self.assertIn("초안", q["q6"]["prompt"])
        self.assertEqual(q["q8"]["kind"], "agree")
        self.assertEqual(q["q8"]["description"], CONSENT)
        self.assertTrue(q["q7"]["other"])
        self.post.assert_not_called()   # 시작만으로는 절대 제출하지 않는다

    def test_start_closed(self):
        self.get.return_value = response(CLOSED_PAGE, CLOSED)
        d = self.client.post("/api/apply/start", json={"item_id": "demo:open"}).json()
        self.assertFalse(d["available"])
        self.assertEqual(d["reason"], "closed")
        self.assertIn("예산 소진", d["replies"][1])
        self.assertEqual([c["label"] for c in d["choices"]], ["비슷한 지원 찾기", "다른 추천 보기"])

    def test_unregistered_catalog_form_is_read_only(self):
        d = self.client.post("/api/apply/start", json={"item_id": "program:orang:75755"}).json()
        self.assertTrue(d["available"])
        self.assertTrue(d["read_only"])
        self.assertFalse(d["submission_ready"])
        self.get.assert_called_once()

    def test_start_unreachable(self):
        self.get.side_effect = requests.ConnectionError()
        d = self.client.post("/api/apply/start", json={"item_id": "demo:open"}).json()
        self.assertEqual(d["reason"], "unreachable")

    def test_non_replica_submission_is_blocked_even_with_complete_answers(self):
        for item_id, answers in [("demo:open", FULL), ("demo:open", {}), ("program:x", FULL)]:
            r=self.client.post("/api/apply/submit",json={"item_id":item_id,"answers":answers})
            self.assertEqual((r.status_code,r.json()["error"]["code"]),(404,"APPLY_NOT_AVAILABLE"))
        self.post.assert_not_called()

    def test_non_replica_is_readable_but_not_submittable(self):
        data=self.client.post("/api/apply/start",json={"item_id":"demo:open"}).json()
        self.assertTrue(data["available"])
        self.assertTrue(data["read_only"])
        self.assertFalse(data["submission_ready"])
        self.assertTrue(data["questions"])

    def test_draft_uses_llm_without_personal_info(self):
        model = FakeModel({"draft": "베이킹을 통해 사람들과 함께 무언가를 만들어 보고 싶습니다."})
        self.app.app.state.chat_model = model
        r = self.client.post("/api/apply/draft", json={
            "item_id": "demo:open", "question_id": "q6", "profile": PROFILE,
            "checkin": {"conversation": "high", "interests": ["문화·여가"]},
            "messages": [{"role": "user", "content": "요즘 사람을 잘 안 만나요"}]})
        self.assertEqual(r.status_code, 200)
        self.assertIn("베이킹", r.json()["draft"])
        system, messages = model.calls[0]
        sent = system + messages[0]["content"]
        self.assertIn("요즘 사람을 잘 안 만나요", sent)
        for secret in ("김둘셋", "010-0000-0000", "2002-03-05"):
            self.assertNotIn(secret, sent)

    def test_start_without_applicant_gives_fill_keys(self):
        d = self.client.post("/api/apply/start", json={"item_id": "demo:open", "profile": PROFILE}).json()
        q = {x["id"]: x for x in d["questions"]}
        self.assertEqual((q["q1"]["fill_key"], q["q4"]["fill_key"]), ("name", "phone"))
        self.assertNotIn("fill_key", q["q6"])

    def test_draft_keeps_placeholders_and_masks_leaked_contacts(self):
        model = FakeModel({"draft": "안녕하세요, [이름]입니다. 함께 만들어 보고 싶습니다."})
        self.app.app.state.chat_model = model
        d = self.client.post("/api/apply/draft", json={
            "item_id": "demo:open", "question_id": "q6",
            "messages": [{"role": "user", "content": "[이름]이라고 소개해 줘. 연락은 010-1234-5678, a.b@test.com"}]}
        ).json()
        self.assertEqual(d["placeholders"], ["[이름]"])
        sent = model.calls[0][1][0]["content"]
        self.assertIn("[이름]", sent)
        self.assertIn("[연락처]", sent)
        self.assertIn("[이메일]", sent)
        self.assertNotIn("010-1234-5678", sent)
        self.assertNotIn("a.b@test.com", sent)

    def test_draft_preview_does_not_call_llm(self):
        model = FakeModel({"draft": "x"})
        self.app.app.state.chat_model = model
        d = self.client.post("/api/apply/draft", json={
            "item_id": "demo:open", "question_id": "q6", "preview": True,
            "messages": [{"role": "user", "content": "요즘 빵 만들기에 빠졌어요"}]}).json()
        self.assertIn("요즘 빵 만들기에 빠졌어요", d["ai_input"])
        self.assertNotIn("draft", d)
        self.assertEqual(model.calls, [])
        self.app.app.state.chat_model = None   # LLM 이 없어도 미리 보기는 된다
        r = self.client.post("/api/apply/draft", json={"item_id": "demo:open", "question_id": "q6", "preview": True})
        self.assertEqual(r.status_code, 200)

    def test_draft_errors(self):
        r = self.client.post("/api/apply/draft", json={"item_id": "demo:open", "question_id": "q6"})
        self.assertEqual(r.status_code, 503)   # LLM 없음 → 예시 초안으로 대신하지 않음
        self.app.app.state.chat_model = FakeModel({"draft": "x"})
        r = self.client.post("/api/apply/draft", json={"item_id": "demo:open", "question_id": "q1"})
        self.assertEqual(r.status_code, 404)   # 짧은 답 문항은 초안 대상 아님

    def test_recommendations_mark_apply_channel(self):
        d = self.client.post("/api/recommendations", json={"profile": PROFILE, "checkin": {}}).json()
        items = d["policies"] + d["programs"]
        self.assertTrue(items)
        self.assertTrue(all("apply_channel" in i and i["apply_channel"] is None for i in items))


if __name__ == "__main__":
    unittest.main()
