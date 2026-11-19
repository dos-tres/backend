"""상태 체크 응답 → 상태 요약 (추천 우선순위 입력). 순수 함수.

규칙 (docs/RECOMMENDATION.md '상태 체크 → 우선순위'):
- 영역별 level: 본인 응답 그대로 (high / mid / low). 모르겠음·답 안 함·나중에 → 우선순위에서 제외
- 바꾸고 싶은 부분을 답했다면, 고르지 않은 영역은 한 단계 낮춘다 (혼자 지내는 선호 등 존중)
- 참여(P)가 high 면 일자리(E)도 최소 mid 로 본다 (학교·일 같은 정기 활동이 없다는 뜻이므로)
- 총점·위험등급은 만들지 않는다. 특정 지원을 자동 배정하지 않고 '먼저 보여줄 순서'에만 쓴다
"""
from __future__ import annotations

from app.checkin.questions import DOMAIN_NAMES, DOMAIN_QUESTIONS, INTEREST_CODES, QUESTIONS_BY_ID

LEVELS = ("high", "mid", "low")
LOWER = {"high": "mid", "mid": "low", "low": "low"}
NOT_ANSWERED = ("unknown", "skip", "later")
WEIGHT = {"high": 2, "mid": 1, "low": 0}


class CheckinError(ValueError):
    def __init__(self, errors: dict[str, str]):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors


def _valid_codes(question_id: str) -> set[str]:
    return {o["code"] for o in QUESTIONS_BY_ID[question_id]["options"]}


def validate(answers: dict) -> dict:
    errors: dict[str, str] = {}
    known = set(QUESTIONS_BY_ID)
    for key in answers:
        if key not in known:
            errors[key] = "unknown_question"
    for q in DOMAIN_QUESTIONS:
        value = answers.get(q["id"])
        if value is not None and value not in _valid_codes(q["id"]) | set(NOT_ANSWERED):
            errors[q["id"]] = "invalid_option"
    for qid in ("satisfaction", "face_to_face"):
        value = answers.get(qid)
        if value is not None and value not in _valid_codes(qid) | set(NOT_ANSWERED):
            errors[qid] = "invalid_option"
    wishes = answers.get("change_wishes")
    if wishes is not None:
        if not isinstance(wishes, list) or not set(wishes) <= _valid_codes("change_wishes"):
            errors["change_wishes"] = "invalid_option"
        elif "none" in wishes and len(wishes) > 1:
            errors["change_wishes"] = "none_with_others"
    interests = answers.get("interests")
    if interests is not None:
        if not isinstance(interests, list) or not set(interests) <= set(INTEREST_CODES):
            errors["interests"] = "invalid_option"
        elif len(interests) > QUESTIONS_BY_ID["interests"]["max"]:
            errors["interests"] = "too_many"
    if errors:
        raise CheckinError(errors)
    return answers


def summarize(answers: dict) -> dict:
    validate(answers)
    raw: dict[str, str] = {}
    unanswered: list[str] = []
    for q in DOMAIN_QUESTIONS:
        value = answers.get(q["id"])
        if value in LEVELS:
            raw[q["domain"]] = value
        else:
            unanswered.append(q["domain"])

    wishes = answers.get("change_wishes")
    wish_set = set(wishes or []) - {"none"}
    levels = dict(raw)
    lowered: list[str] = []
    if wishes is not None:   # 답한 경우에만 적용 (답하지 않으면 그대로)
        for d in list(levels):
            if d not in wish_set and levels[d] != "low":
                levels[d] = LOWER[levels[d]]
                lowered.append(d)
    if levels.get("P") == "high" and WEIGHT.get(levels.get("E", "low"), 0) < WEIGHT["mid"]:
        levels["E"] = "mid"   # 정기 활동이 없으면 일자리 쪽도 함께

    order = "EPOCU"
    priority = sorted((d for d, lv in levels.items() if lv != "low"),
                      key=lambda d: (-WEIGHT[levels[d]], d in lowered, order.index(d)))

    face = answers.get("face_to_face")
    notes = []
    for d in priority:
        notes.append(f"{DOMAIN_NAMES[d]}: {'도움이 더 필요해 보여요' if levels[d] == 'high' else '조금 신경 쓰여요'}")
    if lowered:
        notes.append("바꾸고 싶다고 고르지 않은 부분은 덜 앞세워 보여드려요: "
                     + ", ".join(DOMAIN_NAMES[d] for d in lowered))
    if face == "high":
        notes.append("직접 만나는 활동은 부담이 덜한 것부터 보여드려요")
    return {
        "levels": levels,                     # 영역별 high / mid / low (답한 영역만)
        "priority_domains": priority,         # 먼저 보여줄 영역 순서 (low 제외)
        "unanswered_domains": unanswered,     # 모르겠음·답 안 함·나중에·미응답
        "lowered_domains": lowered,           # 바꾸고 싶은 부분에 없어서 한 단계 낮춘 영역
        "change_wishes": sorted(wish_set) if wishes is not None else None,
        "face_to_face": face if face in LEVELS else None,
        "satisfaction": answers.get("satisfaction") if answers.get("satisfaction") in ("good", "normal", "bad") else None,
        "interests": list(answers.get("interests") or []),
        "notes": notes,
        "disclaimer": "서비스 자체 상태 체크 결과예요. 진단이나 위험 등급이 아니에요.",
    }
