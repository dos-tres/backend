"""대화에서 사용자가 직접 찾는 지원 검색 (LLM 없음).

추천(app/recommend)과 같은 기본 필터(나이·거주지·마감)와 자격 규칙을 쓰되,
사용자가 직접 찾은 것이므로 특정 대상 사업(예: 자살시도자 치료비)도 보여준다(allow_special).
검색어는 LLM 이 사용자 말에서 뽑은 것이지만, 결과는 DB/서비스 JSON 에 있는 항목만 나온다.
"""
from __future__ import annotations

import math
from datetime import date

from sqlalchemy.orm import Session

from app.catalog.repository import find_candidates
from app.catalog.rows import scope_of
from app.recommend.rules import eligible
from app.recommend.service import NO_PROGRAM_DATA, NO_PROGRAM_MATCH, TOP_POLICIES, TOP_PROGRAMS, to_item

MAX_KEYWORDS = 5


def _fields(row: dict) -> tuple[str, str, str]:
    p = row["payload"]
    if row["kind"] == "policy":
        tags = " ".join([p.get("plcyKywdNm") or "", p.get("mclsfNm") or "", p.get("lclsfNm") or ""])
        body = " ".join([p.get("plcyExplnCn") or "", p.get("plcySprtCn") or ""])
    else:
        tags = " ".join([*(p.get("topics") or []), p.get("category") or ""])
        body = p.get("summary") or ""
    return row["title"], tags, body


# 거의 모든 항목에 나와 검색 의미가 없음 (점검: '지역·청년센터'로 찾으면 관련 없는 것까지 다 나옴)
GENERIC = {"지원", "청년", "사업", "정책", "프로그램", "모집", "신청", "지역", "센터", "청년센터", "관련", "정보"}


def clean_keywords(keywords) -> list[str]:
    """여러 단어 검색어는 단어로 나눈다 ('월세 대출' → '월세', '대출'). 너무 흔한 단어는 뺀다."""
    out = []
    for k in keywords or []:
        for word in str(k).split():
            if 2 <= len(word) <= 20 and word not in GENERIC and word not in out:
                out.append(word)
    return out[:MAX_KEYWORDS]


def match(row: dict, keywords: list[str]) -> tuple[float, list[str]]:
    """첫 검색어(사용자가 찾는 핵심 단어)가 들어간 항목만 고른다. 나머지 검색어는 점수만 더한다.

    점검: '우주비행사·훈련·우주'로 찾으면 '훈련'만 맞는 관련 없는 10건이 나왔다 → 핵심 단어가 없으면 0건.
    """
    title, tags, body = _fields(row)
    if keywords and not any(keywords[0] in field for field in (title, tags, body)):
        return 0.0, []
    points, hits = 0.0, []
    for k in keywords:
        p = 3 if k in title else 2 if k in tags else 1 if k in body else 0
        if p:
            points += p
            hits.append(k)
    return points, hits


def search(session: Session | None, profile: dict, keywords: list[str], today: date | None = None) -> dict:
    today = today or date.today()
    keywords = clean_keywords(keywords)
    rows, source = find_candidates(session, profile["sigungu_cd"], profile.get("age"), today)
    found = {"policy": [], "program": []}
    for row in rows:
        if not keywords or not eligible(row, profile, allow_special=True):
            continue
        points, hits = match(row, keywords)
        if not points:
            continue
        scope = scope_of(row, profile["sigungu_cd"])
        points += {"시군구": 1.0, "광역": 0.5}.get(scope, 0)
        points += min(math.log10((row["payload"].get("inqCnt") or 0) + 1), 4) * 0.1
        found[row["kind"]].append((round(points, 1), ["'" + "', '".join(hits) + "' 검색 결과"], row))
    out = {}
    for kind, top in (("policy", TOP_POLICIES), ("program", TOP_PROGRAMS)):
        found[kind].sort(key=lambda x: (-x[0], x[2]["id"]))
        seen, picked = set(), []
        for s, w, r in found[kind]:
            key = "".join(ch for ch in r["title"] if ch.isalnum())[:12]   # 같은 사업 중복 정리 (추천과 같은 기준)
            if key in seen:
                continue
            seen.add(key)
            picked.append(to_item(s, w, r, profile["sigungu_cd"]))
            if len(picked) >= top:
                break
        out[kind] = picked
    # 추천과 같은 안내: 이 지역 센터 프로그램 데이터가 아예 없으면 no_program_data
    has_program_data = any(r["kind"] == "program" for r in rows)
    programs_notice = None if out["program"] else (NO_PROGRAM_MATCH if has_program_data else NO_PROGRAM_DATA)
    return {"keywords": keywords, "policies": out["policy"], "programs": out["program"],
            "programs_notice": programs_notice, "source": source}
