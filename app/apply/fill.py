"""기본 정보로 채울 수 있는 문항 찾기 (docs/APPLY.md 11장 표).

문항 제목의 단어로 정한다. 동의 문항은 절대 채우지 않는다. 채운 값은 사용자에게 확인받고, 고치면 FE 가 고친 값으로 보낸다.
"""
from __future__ import annotations

import re

from app.apply.gform import Question
from app.catalog.regions import region_name

# (문항 제목 정규식, 채울 값 이름) — 위에서부터 처음 맞는 것
RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"성명|이름|성함"), "name"),
    (re.compile(r"생년월일|생일"), "birth_date"),
    (re.compile(r"나이|연령"), "age"),
    (re.compile(r"성별"), "sex"),
    (re.compile(r"연락처|휴대폰|핸드폰|전화|휴대전화"), "phone"),
    (re.compile(r"이메일|메일|e-?mail", re.I), "email"),
    (re.compile(r"거주|사는\s*곳|사시는\s*곳|주소|지역"), "region"),
]
NEEDS_DONG = re.compile(r"동\s*까지|OO동|○○동|읍·?면·?동")
DRAFTABLE = re.compile(r"이유|동기|계기|소개|기대|각오|목표|하고\s*싶은|바라는|사연|포부|자유롭게|의견")


def _region_name(sigungu_cd: str | None) -> str | None:
    if not sigungu_cd:
        return None
    name = region_name(sigungu_cd)
    return name[1] if name else None


def _value(key: str, applicant: dict, profile: dict) -> str | None:
    if key in ("name", "phone", "email"):
        return applicant.get(key) or None
    if key == "birth_date":
        b = applicant.get("birth_date")
        return b.replace("-", ".") if b else None
    if key == "age":
        return str(profile["age"]) if profile.get("age") is not None else None
    if key == "sex":
        return profile.get("sex")
    if key == "region":
        return _region_name(profile.get("sigungu_cd"))
    return None


def split(questions: list[Question], applicant: dict | None, profile: dict | None):
    """→ (filled: 기본 정보로 채운 문항, ask: 물어야 할 문항(prefill·can_draft 포함))."""
    applicant, profile = applicant or {}, profile or {}
    filled, ask = [], []
    for q in questions:
        key = next((k for pattern, k in RULES if pattern.search(q.label)), None) if q.kind != "agree" else None
        value = _value(key, applicant, profile) if key else None
        if value and q.kind in ("choice",) and value not in q.options:
            value = None   # 성별 등: 선택지와 맞을 때만
        prefill = None
        if key == "region" and value and NEEDS_DONG.search(q.label):
            prefill, value = f"{value} ", None   # 구까지 채워 두고 동은 묻는다
        if value:
            filled.append({"question_id": q.id, "label": q.label, "value": value})
            continue
        ask.append({"question": q, "prefill": prefill,
                    "can_draft": q.kind == "long" and key is None and bool(DRAFTABLE.search(q.label))})
    return filled, ask


DRAFT_TOPICS = [("동기", "지원 동기"), ("이유", "신청 이유"), ("계기", "신청 계기"), ("소개", "자기소개"),
                ("기대", "기대하는 점"), ("목표", "목표"), ("각오", "각오")]
ASKS = re.compile(r"(요|세요|까|니까|나요|가요)\s*[.!?]*$")


def prompt_for(q: Question, prefill: str | None, can_draft: bool) -> str:
    """조이가 물을 말풍선 문구 (서버가 만든다)."""
    if q.kind == "agree":
        return "개인정보 동의 내용을 읽어 보고 직접 골라 주세요."
    if can_draft:
        topic = next((name for word, name in DRAFT_TOPICS if word in q.label), "이 문항")
        return f"{topic}{_eul(topic)} 적어야 하네요. 초안 써 드릴까요?"
    if prefill:
        return f"사는 동까지 알려 주세요. ({prefill.strip()} ○○동)"
    label = _short(q.label)
    if ASKS.search(label):   # 문항이 이미 묻는 말이면 그대로 ("…알려주세요.")
        text = label.rstrip(" !.") + ("" if label.rstrip().endswith("?") else ".")
    elif q.kind == "choice":
        text = f"{label}{_eul(label)} 골라 주세요."
    elif q.kind == "multi":
        text = f"{label}{_eul(label)} 모두 골라 주세요."
    else:
        text = f"{label}{_eul(label)} 알려 주세요."
    return text if q.required else f"{text} (안 적어도 돼요)"


def _eul(word: str) -> str:
    """을/를: 마지막 글자에 받침이 있으면 '을'."""
    last = word.rstrip()[-1:] if word.strip() else ""
    if "가" <= last <= "힣":
        return "을" if (ord(last) - 0xAC00) % 28 else "를"
    return "를"


def _short(label: str) -> str:
    text = re.sub(r"\s*\(.*?\)\s*", " ", label).strip(" !:")
    return text[:60]
