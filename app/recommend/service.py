"""추천 조합: 상태 체크 요약 → 후보 조회 → 규칙(rules.py)으로 순위 → 응답 형태."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.catalog.repository import find_candidates, known_sigungu_codes
from app.catalog.rows import scope_of
from app.checkin.summary import summarize
from app.recommend.rules import rank

from app.catalog.presentation import presentation_fields, catalog_today

TOP_POLICIES = 6
TOP_PROGRAMS = 4


def _short(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def income_condition(payload: dict) -> dict | None:
    """정책 소득 조건. 추천에서는 거르지 않고, 사용자가 신청하려 할 때 확인하도록 그대로 넘긴다.

    - None: 소득 무관 (확인할 것 없음)
    - annual_income: 연소득 상한이 숫자로 있음 (max_manwon, 만원) → 예/아니요 한 번만 물으면 된다
    - other: 중위소득 % 등 원문 설명 (text) → 그대로 보여준다
    """
    kind = (payload.get("earnCndSeCd_nm") or "").strip()
    if kind == "연소득" and payload.get("earn_max_clean"):
        amount = int(payload["earn_max_clean"])
        return {"kind": "annual_income", "max_manwon": amount, "text": f"연소득 {amount:,}만 원 이하"}
    text = " ".join((payload.get("earnEtcCn") or "").split())
    if kind == "기타" and text:
        return {"kind": "other", "max_manwon": None, "text": text}
    return None


NO_PROGRAM_DATA = {
    "code": "no_program_data",
    "message": "아직 이 지역 청년센터 프로그램 정보를 모으지 못했어요. 가까운 청년센터에 직접 물어봐 주세요.",
}
NO_PROGRAM_MATCH = {
    "code": "no_program_match",
    "message": "지금 조건에 맞는 청년센터 프로그램을 찾지 못했어요.",
}


def to_item(points: float, why: list[str], row: dict, sigungu_cd: str, today: date | None = None) -> dict:
    p = row["payload"]
    item = {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "why": why,
        "score": points,
        "domains": row["domains"],
        "situations": row["situations"],
        "access_type": row["access_type"],
        "deadline": row["deadline"].isoformat() if row["deadline"] else None,
        "scope": scope_of(row, sigungu_cd),
    }
    if row["kind"] == "policy":
        item.update({
            "summary": _short(p.get("plcyExplnCn"), 200),
            "support": _short(p.get("plcySprtCn"), 300),
            "institution": p.get("sprvsnInstCdNm") or p.get("operInstCdNm") or "",
            "apply_period": p.get("aplyYmd") or p.get("aplyPrdSeCd_nm") or "",
            "apply_url": p.get("aplyUrlAddr") or "",
            "reference_url": p.get("refUrlAddr1") or "",
            "income_condition": income_condition(p),
        })
    else:
        item.update({
            "summary": _short(p.get("summary"), 200),
            "center": p.get("center_names") or "",
            "place": p.get("place") or "",
            "apply_period": p.get("aply_text") or (f"~{p['aply_end']}" if p.get("aply_end") else "상시"),
            "url": p.get("url") or "",
            "apply_urls": p.get("apply_urls") or "",
            "evergreen": bool(p.get("evergreen")),   # 오래된 상시 글: '이용 전 센터에 확인' 표시
        })
    from app.catalog.program_facts import presentation
    item.update(presentation(row))
    item.update(presentation_fields(row, today))
    item['apply_period'] = item['application_period']
    return item


class UnknownRegion(ValueError):
    """원본 데이터에 없는 시군구 코드 (옛 행정코드 등). 0건을 조용히 돌려주지 않고 요청 오류로 알린다."""


def recommend(session: Session | None, profile: dict, answers: dict, today: date | None = None) -> dict:
    today = today or catalog_today()
    summary = summarize(answers)
    if profile["sigungu_cd"] not in known_sigungu_codes():
        raise UnknownRegion(profile["sigungu_cd"])
    rows, source = find_candidates(session, profile["sigungu_cd"], profile.get("age"), today)
    program_rows = [r for r in rows if r["kind"] == "program"]
    policies = rank([r for r in rows if r["kind"] == "policy"], profile, summary, TOP_POLICIES)
    programs = rank(program_rows, profile, summary, TOP_PROGRAMS)
    # 프로그램이 0건일 때 이유를 알린다: 그 지역 데이터가 아예 없음(서울 밖 대부분) / 있지만 조건에 안 맞음
    programs_notice = None
    if not programs:
        programs_notice = NO_PROGRAM_MATCH if program_rows else NO_PROGRAM_DATA
    return {
        "summary": summary,
        "policies": [to_item(s, w, r, profile["sigungu_cd"], today) for s, w, r in policies],
        "programs": [to_item(s, w, r, profile["sigungu_cd"], today) for s, w, r in programs],
        "programs_notice": programs_notice,
        "candidates": {"policy": sum(r["kind"] == "policy" for r in rows),
                       "program": len(program_rows)},
        "source": source,
        "notice": "추천은 신청 자격을 확정하지 않아요. 신청 전에 공식 공고에서 조건을 꼭 확인해 주세요.",
    }
