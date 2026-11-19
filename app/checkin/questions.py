"""첫 이용 상태 체크 문항 (docs/requirements.md 2장 초안 기준).

- 다섯 관점(경제·참여·외출·교류·지원망)마다 한 문항, 한 번에 하나씩, 선택지 중심
- 모든 문항에 '모르겠어요 / 답하지 않을래요 / 나중에 할게요' 제공
- 서비스 자체 상태 체크다. 공인 진단척도나 고립 진단이 아니며 총점·위험등급을 만들지 않는다
- 문구·선택지는 팀 리뷰에서 확정 전인 초안 (docs/RECOMMENDATION.md '상태 체크')
"""
from __future__ import annotations

DOMAIN_NAMES = {"E": "경제", "P": "참여", "O": "외출", "C": "교류", "U": "지원망"}

# 문항·선택지를 바꾸면 올린다. 저장된 응답(checkin_responses.question_version)이 어느 문항에 대한 답인지 구분한다
QUESTION_VERSION = "draft-2026-11-19"

# 모든 문항 공통 선택지. 고르면 그 영역은 우선순위 계산에서 빠진다
COMMON_OPTIONS = [
    {"code": "unknown", "label": "모르겠어요"},
    {"code": "skip", "label": "답하지 않을래요"},
    {"code": "later", "label": "나중에 할게요"},
]

# level: high = 지금 도움이 더 필요해 보이는 쪽, mid = 조금, low = 괜찮음
DOMAIN_QUESTIONS = [
    {"id": "economy", "domain": "E", "text": "요즘 생활비나 취업 준비 비용이 얼마나 부담돼요?",
     "options": [{"code": "high", "label": "많이 부담돼요"}, {"code": "mid", "label": "조금 부담돼요"},
                 {"code": "low", "label": "괜찮아요"}]},
    {"id": "participation", "domain": "P", "text": "최근 학교·일·모임처럼 정기적으로 하는 활동이 있나요?",
     "options": [{"code": "high", "label": "없어요"}, {"code": "mid", "label": "가끔 있어요"},
                 {"code": "low", "label": "있어요"}]},
    {"id": "outing", "domain": "O", "text": "요즘 필요한 일 외에도 밖에 나가는 편인가요?",
     "options": [{"code": "high", "label": "거의 안 나가요"}, {"code": "mid", "label": "가끔 나가요"},
                 {"code": "low", "label": "자주 나가요"}]},
    {"id": "conversation", "domain": "C", "text": "편하게 이야기 나누는 시간이 충분하다고 느껴요?",
     "options": [{"code": "high", "label": "부족해요"}, {"code": "mid", "label": "보통이에요"},
                 {"code": "low", "label": "충분해요"}]},
    {"id": "support", "domain": "U", "text": "곤란한 일이 생겼을 때 도움을 부탁할 사람이 있나요?",
     "options": [{"code": "high", "label": "없어요"}, {"code": "mid", "label": "잘 모르겠어요"},
                 {"code": "low", "label": "있어요"}]},
]

EXTRA_QUESTIONS = [
    {"id": "satisfaction", "text": "지금 생활에 얼마나 만족해요?", "multiple": False,
     "options": [{"code": "good", "label": "만족해요"}, {"code": "normal", "label": "보통이에요"},
                 {"code": "bad", "label": "아쉬워요"}]},
    {"id": "change_wishes", "text": "바꾸고 싶은 부분이 있나요? (여러 개 선택)", "multiple": True,
     "options": [{"code": "E", "label": "돈·일 걱정을 덜고 싶어요"}, {"code": "P", "label": "꾸준히 하는 활동이 생겼으면 해요"},
                 {"code": "O", "label": "밖에 더 나가고 싶어요"}, {"code": "C", "label": "이야기 나눌 사람이 더 있었으면 해요"},
                 {"code": "U", "label": "기댈 곳이 있었으면 해요"}, {"code": "none", "label": "지금은 바꾸고 싶은 게 없어요"}]},
    {"id": "face_to_face", "text": "사람을 직접 만나는 활동이 부담돼요?", "multiple": False,
     "options": [{"code": "high", "label": "많이 부담돼요"}, {"code": "mid", "label": "조금 부담돼요"},
                 {"code": "low", "label": "괜찮아요"}]},
    {"id": "interests", "text": "어떤 도움이 필요해요? (최대 3개)", "multiple": True, "max": 3,
     "options": [{"code": k, "label": k} for k in (
         "일자리·취업", "창업", "집·주거", "생활비·금융", "교육·자격증", "마음건강·상담",
         "몸 건강·식사", "문화·여가", "사람 만나기·모임", "해외 경험")]},
]

QUESTIONS_BY_ID = {q["id"]: q for q in DOMAIN_QUESTIONS + EXTRA_QUESTIONS}
INTEREST_CODES = tuple(o["code"] for o in QUESTIONS_BY_ID["interests"]["options"])


def all_questions() -> dict:
    return {
        "notice": "서비스 자체 상태 체크예요. 진단이 아니고, 답하지 않아도 돼요. 언제든 다시 바꿀 수 있어요.",
        "common_options": COMMON_OPTIONS,
        "domain_questions": DOMAIN_QUESTIONS,
        "extra_questions": EXTRA_QUESTIONS,
    }
