"""AI 비서 대화 (POST /api/chat). 가짜 LLM 으로 결정적으로 확인한다 (키·DB 불필요)."""
import unittest
from unittest.mock import MagicMock, patch

import requests
from fastapi.testclient import TestClient

from app.chat import safety
from app.chat.llm import LLMUnavailable, OpenAICompatible
from app.config import Settings
from app.main import create_app

PROFILE = {"age": 30, "sex": "여", "sigungu_cd": "26350", "job": "쉬는 중"}


class FakeModel:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def complete_json(self, system, messages):
        self.calls.append(messages)
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


def user(text):
    return [{"role": "user", "content": text}]


class ChatApiTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(_env_file=None))   # DB 없음 → serving JSON, LLM 없음
        self.client = TestClient(self.app)

    def use(self, data):
        model = FakeModel(data)
        self.app.app.state.chat_model = model
        return model

    def post(self, **body):
        return self.client.post("/api/chat", json=body)

    def test_selected_program_uses_safe_profile_and_stored_facts(self):
        model=self.use({'replies':['이력서 첨삭과 면접 준비를 도와줘요.'],'intent':'recommend','offer':'search'})
        response=self.post(messages=user('여기서는 어떤 도움을 받을 수 있어?'),profile=PROFILE,selected_item_id='program:orang:75646')
        data=response.json()
        self.assertEqual(response.status_code,200)
        self.assertIsNone(data['results'])
        self.assertEqual(data['choices'],[])
        context=' '.join(m['content'] for m in model.calls[0] if m['role']=='system')
        self.assertIn('서울청년센터 중구',context)
        self.assertIn('sigungu_cd',context)
        self.assertNotIn('source_content',context)

    def test_inquiry_script_is_not_a_call_and_offers_schedule(self):
        self.use({'replies':['unused'],'intent':'chat'})
        data=self.post(messages=user('자기소개서를 미리 써 가야 하는지 물어볼 말 정리해줘'),selected_item_id='program:orang:75646').json()
        self.assertIn('전화는 대신 걸 수 없지만',data['replies'][0])
        self.assertIn('서울청년센터 중구',data['replies'][1])
        self.assertEqual(data['choices'][0]['text'],'문의 일정 등록')

    def test_crisis_answers_with_resources_without_llm(self):
        for text in ("자살 관련 지원받고 싶어요", "요즘 그냥 죽고 싶다는 생각이 들어", "다 끝내고 싶어"):
            response = self.post(messages=user(text))   # LLM 이 없어도 동작
            self.assertEqual(response.status_code, 200, text)
            data = response.json()
            self.assertEqual(data["mode"], "crisis")
            self.assertIn("109", data["replies"][1])   # 짧은 공감 다음 말풍선에 바로 연락처
            self.assertIn("109", [r["contact"] for r in data["safety"]["resources"]])
            self.assertTrue(data["choices"])
        model = self.use({"reply": "x", "intent": "chat"})
        self.post(messages=user("죽고 싶어요"))
        self.assertEqual(model.calls, [])

    def test_without_llm_is_503_not_fake_answer(self):
        response = self.post(messages=user("안녕하세요"))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "AI_UNAVAILABLE")
        self.use(LLMUnavailable("timeout"))
        self.assertEqual(self.post(messages=user("안녕하세요")).status_code, 503)
        self.use({"reply": "", "intent": "chat"})
        self.assertEqual(self.post(messages=user("안녕하세요")).status_code, 503)

    def test_extracts_only_valid_checkin_answers(self):
        self.use({"replies": ["많이 외로웠겠어요.", "요즘 밖에는 자주 나가요?"], "intent": "share_state",
                  "checkin": {"support": "high", "economy": "bogus", "unknown": "high"},
                  "interests": ["마음건강·상담", "없는 분야"], "next_question": "outing"})
        data = self.post(messages=user("기댈 사람이 아무도 없어요. 상담 같은 거 받아보고 싶어요"),
                         checkin={"economy": "mid"}).json()
        self.assertEqual(data["mode"], "share_state")
        self.assertEqual(data["checkin_update"], {"support": "high", "interests": ["마음건강·상담"]})
        self.assertEqual(data["checkin"], {"economy": "mid", "support": "high", "interests": ["마음건강·상담"]})
        self.assertEqual({c["question_id"] for c in data["choices"]}, {"outing"})
        self.assertIn("skip", [c["code"] for c in data["choices"]])
        self.assertIsNone(data["results"])

    def test_buttons_only_when_bubble_asks_that_question(self):
        self.use({"replies": ["힘들겠어요. 몸 건강·식사 쪽 지원이 필요할까요?"], "intent": "share_state", "next_question": "economy"})
        self.assertEqual(self.post(messages=user("밥 챙겨 먹기도 힘들어요")).json()["choices"], [])
        self.use({"replies": ["그렇군요. 생활비 부담은 어때요?"], "intent": "share_state", "next_question": "economy"})
        self.assertEqual(self.post(messages=user("음")).json()["choices"][0]["question_id"], "economy")

    def test_does_not_ask_known_question_again(self):
        self.use({"reply": "그렇군요", "intent": "chat", "next_question": "economy"})
        data = self.post(messages=user("음"), checkin={"economy": "high"}).json()
        self.assertNotIn("economy", [c.get("question_id") for c in data["choices"]])   # 대신 막다른 답이라 제안 버튼

    def test_recommend_needs_profile_then_uses_rule_engine(self):
        self.use({"replies": ["찾아볼게요.", "원하면 집·주거 지원을 찾아볼까요?"], "intent": "recommend",
                  "checkin": {"economy": "high"}, "offer": "search", "interests": ["집·주거"]})
        data = self.post(messages=user("나한테 맞는 지원 추천해줘")).json()
        self.assertEqual(data["needs"], ["profile"])
        self.assertEqual(data["replies"], ["나이랑 사는 곳을 알려 주면 바로 찾아볼게요."])   # 기본 정보만 묻고
        self.assertEqual(data["choices"], [])                                             # 버튼은 내지 않음
        self.assertIsNone(data["results"])
        self.use({"reply": "찾아볼게요", "intent": "recommend", "checkin": {"economy": "high"}})
        data = self.post(messages=user("나한테 맞는 지원 추천해줘"), profile=PROFILE).json()
        self.assertEqual(data["results"]["type"], "recommend")
        self.assertTrue(data["results"]["policies"])
        self.assertEqual(data["results"]["programs_notice"]["code"], "no_program_data")   # 부산
        self.assertEqual(data["results"]["source"], "file")

    def test_explicit_search_can_show_special_target_support(self):
        # 사용자가 직접 찾으면 자동 추천에서는 빼는 특정 대상 사업도 보여준다
        self.use({"replies": ["더 궁금한 거 있으면 말해 줘요."], "intent": "search", "search_keywords": ["자살시도", "x"]})
        data = self.post(messages=user("응급실 치료비 지원 찾아줘"), profile=PROFILE).json()
        self.assertEqual(data["results"]["type"], "search")
        # 결과 말풍선은 서버가 실제 결과로 만들고, LLM 말은 그 뒤에 하나
        self.assertTrue(data["replies"][0].startswith("'자살시도'로 찾아봤어요!"), data["replies"])
        self.assertEqual(data["replies"][-1], "더 궁금한 거 있으면 말해 줘요.")
        self.assertEqual(data["results"]["programs_notice"]["code"], "no_program_data")   # 부산
        self.assertIn("정책만 보여 드려요", data["replies"][0])
        self.assertEqual([c["label"] for c in data["choices"]], ["맞춤 추천 받기"])
        self.assertEqual(data["results"]["keywords"], ["자살시도"])
        titles = [p["title"] for p in data["results"]["policies"]]
        self.assertTrue(any("자살시도" in t for t in titles), titles)
        self.assertIn("검색 결과", data["results"]["policies"][0]["why"][0])

    def test_replies_are_cleaned_and_old_format_accepted(self):
        self.use({"replies": ["  첫 번째   말풍선 ", 3, "", "두 번째", "세 번째는 버림"], "intent": "chat"})
        self.assertEqual(self.post(messages=user("안녕")).json()["replies"][:2], ["첫 번째 말풍선", "두 번째"])
        self.use({"reply": "예전 형식도 받아요", "intent": "chat"})
        self.assertEqual(self.post(messages=user("안녕")).json()["replies"][0], "예전 형식도 받아요")

    def test_offer_becomes_button_instead_of_question(self):
        self.use({"replies": ["그랬군요.", "원하면 제가 맞는 지원을 찾아볼까요?"], "intent": "share_state",
                  "checkin": {"economy": "high"}, "offer": "recommend", "next_question": "outing"})
        data = self.post(messages=user("돈이 너무 부족해요")).json()
        self.assertEqual(data["choices"], [])
        self.use({"replies": ["원하면 찾아볼까요?"], "intent": "share_state", "interests": ["집·주거"], "offer": "search"})
        data = self.post(messages=user("집 문제가 걱정이에요")).json()
        self.assertEqual(data["choices"], [])

    def test_unrequested_recommend_becomes_offer(self):
        # 상황만 말했는데 LLM 이 추천으로 넘어가 나이·사는 곳을 묻는 경우 → 상황 이야기 + 제안 버튼
        self.use({"replies": ["막막할 때가 있죠. 나이와 사는 곳을 알려 줄래요?"], "intent": "recommend",
                  "checkin": {"economy": "high"}})
        data = self.post(messages=user("요즘 너무 막막해요. 뭘 해야 할지 모르겠어요")).json()
        self.assertEqual(data["mode"], "share_state")
        self.assertEqual(data["needs"], [])
        self.assertEqual(data["replies"][0], "막막할 때가 있죠.")
        self.assertNotIn("나이", " ".join(data["replies"]))
        self.assertEqual(data["choices"], [])
        self.assertEqual(data["checkin"]["economy"], "high")   # 알아들은 답은 그대로

    def test_drops_reasked_question_and_repeated_result(self):
        self.use({"replies": ["밖에 거의 안 나간다니 답답하겠어요. 요즘 필요한 일 외에도 밖에 나가는 편인가요?"],
                  "intent": "share_state", "checkin": {"outing": "high"}})
        data = self.post(messages=user("요즘 집 밖에 거의 안 나가요")).json()
        self.assertEqual(data["replies"], ["밖에 거의 안 나간다니 답답하겠어요.", "어떤 도움이 있으면 좋을지 조금 더 이야기해 줄래요?"])   # 질문이 빠져 제안이 붙음
        self.use({"replies": ["월세 지원 관련 정보를 찾아봤어요."], "intent": "search", "search_keywords": ["월세"]})
        data = self.post(messages=user("월세 지원 있어요?"), profile=PROFILE).json()
        self.assertEqual(len(data["replies"]), 2)
        self.assertEqual(data["replies"][1], "더 좁히고 싶은 조건 있으면 말해 줘요.")

    def test_scenario_fixes(self):
        # 2026-11-20 여러 턴 시나리오 점검(docs/CHAT_SCENARIOS.md)에서 찾은 문제들
        # 1) "추천해 줘요"를 상황 이야기로만 받음 → 추천으로
        self.use({"replies": ["많이 힘들겠어요."], "intent": "share_state", "checkin": {"economy": "high"}})
        data = self.post(messages=user("생활비가 빠듯해요. 받을 수 있는 지원 추천해 줘요"), profile=PROFILE).json()
        self.assertEqual(data["results"]["type"], "recommend")
        # 2) 반말·줄임말 요청("있냐")도 요청으로 → 제안으로 바꾸지 않고 검색
        self.use({"replies": ["찾아볼게요."], "intent": "search", "search_keywords": ["월세"]})
        data = self.post(messages=user("월세지원있냐"), profile=PROFILE).json()
        self.assertEqual(data["results"]["type"], "search")
        # 3) 제안으로 바꿀 때 나이·사는 곳을 묻는 문장, "찾아볼게요"는 남기지 않음
        self.use({"replies": ["주거 지원을 찾으려면 나이와 사는 곳을 알려 주세요.", "찾아볼게요."], "intent": "search",
                  "interests": ["집·주거"]})
        data = self.post(messages=user("집 문제가 걱정이에요")).json()
        self.assertEqual(data["replies"], ["알겠어요.", "지금 가장 신경 쓰이는 건 어떤 부분이에요?"])
        # 4) 방금 알아들은 문항을 말을 바꿔 다시 묻는 문장은 뺌 (다른 질문은 남김)
        self.use({"replies": ["힘들겠어요. 생활비 부담은 어느 정도인가요?"], "intent": "share_state",
                  "checkin": {"economy": "high"}})
        self.assertEqual(self.post(messages=user("돈이 없어요")).json()["replies"], ["힘들겠어요.", "어떤 도움이 있으면 좋을지 조금 더 이야기해 줄래요?"])
        self.use({"replies": ["그렇군요. 사람 만나는 건 부담돼요?"], "intent": "share_state", "checkin": {"economy": "high"}})
        self.assertIn("사람 만나는 건 부담돼요?", self.post(messages=user("돈이 없어요")).json()["replies"][0])
        # 5) 검색은 첫 검색어(핵심)가 들어간 항목만 → 관련 없는 결과 대신 0건
        self.use({"replies": ["찾아볼게요."], "intent": "search", "search_keywords": ["우주비행사", "훈련"]})
        data = self.post(messages=user("우주비행사 훈련 지원 있어요?"), profile=PROFILE).json()
        self.assertEqual((data["results"]["policies"], data["results"]["programs"]), ([], []))
        self.assertIn("없었어요", data["replies"][0])

    def test_dead_end_gets_offer_except_closing_or_after_crisis(self):
        self.use({"replies": ["그건 아직 제가 못 해요."], "intent": "chat"})
        data = self.post(messages=user("내년 공고 나오면 알려 줘요")).json()
        self.assertEqual(data["replies"], ["그건 아직 제가 못 해요.", "어떤 도움이 있으면 좋을지 조금 더 이야기해 줄래요?"])
        self.assertEqual(data["choices"], [])
        self.use({"replies": ["네, 언제든 불러 주세요!"], "intent": "chat"})
        self.assertEqual(self.post(messages=user("고마워요 여기까지 할게요")).json()["choices"], [])
        after_crisis = [{"role": "user", "content": "다 끝내고 싶어요"}, {"role": "assistant", "content": "… 109 …"},
                        {"role": "user", "content": "음"}]
        self.use({"replies": ["편하게 이야기해 주세요."], "intent": "chat"})
        self.assertEqual(self.post(messages=after_crisis).json()["replies"], ["편하게 이야기해 주세요."])

    def test_does_not_ask_profile_when_known(self):
        self.use({"replies": ["집 근처 지원을 찾으려면 사는 지역을 알려 주세요."], "intent": "recommend"})
        data = self.post(messages=user("이 중에 집 근처 거 있어요?"), profile=PROFILE).json()
        self.assertNotIn("지역을 알려", " ".join(data["replies"]))
        self.use({"replies": ["맞춤 지원 추천해 줄게요. 조금만 기다려 주세요."], "intent": "recommend"})
        data = self.post(messages=user("추천해 줘"), profile=PROFILE).json()
        self.assertNotIn("기다려", " ".join(data["replies"]))

    def test_no_search_results_suggests_next_step(self):
        self.use({"replies": ["이런 게 있어요."], "intent": "search", "search_keywords": ["존재하지않는검색어"]})
        data = self.post(messages=user("없는 거 찾아줘"), profile=PROFILE).json()
        self.assertIn("없었어요", data["replies"][0])
        self.assertNotIn("이런 게 있어요.", data["replies"])   # 결과를 전제로 쓴 LLM 말은 버림
        self.assertEqual([c["label"] for c in data["choices"]], ["맞춤 추천 받기"])

    def test_validation(self):
        self.use({"reply": "네", "intent": "chat"})
        last_assistant = [{"role": "user", "content": "안녕"}, {"role": "assistant", "content": "안녕하세요"}]
        self.assertEqual(self.post(messages=last_assistant).status_code, 422)
        self.assertEqual(self.post(messages=[]).status_code, 422)
        self.assertEqual(self.post(messages=user("가" * 1001)).status_code, 422)
        self.assertEqual(self.post(messages=user("안녕"), checkin={"economy": "very"}).status_code, 422)
        old_region = {**PROFILE, "sigungu_cd": "46720"}
        self.assertEqual(self.post(messages=user("안녕"), profile=old_region).status_code, 422)


class SafetyTests(unittest.TestCase):
    # 2026-11-19 점검 세트. 처음 규칙은 31개 중 16개만 잡았다 (간접 표현 누락). 문구를 바꿀 때 이 세트를 늘려 간다
    POSITIVE = (
        "자살하고 싶어요", "자살 충동이 들어요", "죽고싶다", "요즘 죽고 싶다는 생각만 해", "그냥 죽어버리고 싶어", "살기 싫어",
        "더 살고 싶지 않아요", "사라지고 싶어", "없어지고 싶어요", "그만 살고 싶어", "다 그만두고 싶어 인생을",
        "세상을 떠나고 싶어", "잠들어서 안 깨어났으면 좋겠어", "아침이 안 왔으면 좋겠어", "내가 없으면 다들 편할 텐데",
        "목숨을 끊고 싶어", "스스로 목숨을", "극단적인 선택을 생각해", "극단적 선택", "유서를 써놨어", "손목을 그었어",
        "자해를 했어요", "몸에 상처를 내요", "뛰어내리고 싶어", "약을 한꺼번에 먹을까", "더 이상 못 버티겠어",
        "다 끝내고 싶어", "살아갈 이유가 없어", "삶의 의미가 없어요", "태어나지 말걸", "죽는 게 나을 것 같아",
        "죽을 것 같아요 너무 힘들어서",
    )
    NEGATIVE = (
        "오늘 너무 피곤해요", "배고파 죽겠어", "웃겨 죽겠다", "죽이 맛있어요", "월세 지원 찾아줘", "취업이 안 돼서 힘들어요",
        "친구가 없어요", "자살골 넣은 선수 봤어?", "시험 끝내고 싶어", "이 일 끝내고 싶어요", "살 빼고 싶어", "집에만 있어요",
        "너무 외로워요", "힘들어 죽겠다 진짜 일 많아", "알바 그만두고 싶어", "오늘 일 다 끝내고 싶어요",
    )

    def test_crisis_patterns(self):
        missed = [t for t in self.POSITIVE if not safety.is_crisis(t)]
        false_alarms = [t for t in self.NEGATIVE if safety.is_crisis(t)]
        self.assertEqual(missed, [])
        self.assertEqual(false_alarms, [])


class LLMClientTests(unittest.TestCase):
    def client(self):
        return OpenAICompatible("test-key", "https://llm.example/v1", "test-model", timeout=1)

    def response(self, status, payload):
        r = MagicMock(status_code=status)
        r.json.return_value = payload
        return r

    def test_parses_json_content(self):
        ok = self.response(200, {"choices": [{"message": {"content": '{"reply": "안녕", "intent": "chat"}'}}]})
        with patch("app.chat.llm.requests.post", return_value=ok) as post:
            self.assertEqual(self.client().complete_json("sys", user("hi")), {"reply": "안녕", "intent": "chat"})
        self.assertLessEqual(post.call_args.kwargs["timeout"], 1)   # 전체 시간 예산 안에서

    def test_timeout_is_total_budget_not_per_attempt(self):
        with patch("app.chat.llm.requests.post", side_effect=requests.Timeout()) as post:
            with self.assertRaises(LLMUnavailable):
                self.client().complete_json("sys", user("hi"))
        self.assertEqual(post.call_count, 1)   # 시간 초과면 다시 시도하지 않는다
        with patch("app.chat.llm.requests.post", side_effect=requests.ConnectionError()) as post:
            with self.assertRaises(LLMUnavailable):
                OpenAICompatible("k", "https://llm.example/v1", "m", timeout=10).complete_json("sys", user("hi"))
        self.assertEqual(post.call_count, 2)   # 연결 오류는 한 번 더

    def test_errors_raise_unavailable(self):
        cases = [
            requests.Timeout(),
            self.response(500, {}),
            self.response(401, {}),
            self.response(200, {"choices": [{"message": {"content": "not json"}}]}),
            self.response(200, {"choices": [{"message": {"content": "[1, 2]"}}]}),
        ]
        for case in cases:
            kwargs = {"side_effect": case} if isinstance(case, Exception) else {"return_value": case}
            with self.subTest(case=case), patch("app.chat.llm.requests.post", **kwargs):
                with self.assertRaises(LLMUnavailable):
                    self.client().complete_json("sys", user("hi"))


if __name__ == "__main__":
    unittest.main()
