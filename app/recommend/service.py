"""추천 조합: 상태 체크 요약 → 후보 조회 → 규칙(rules.py)으로 순위 → 응답 형태."""
from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.catalog.repository import find_candidates
from app.catalog.rows import scope_of
from app.checkin.summary import summarize
from app.recommend.rules import rank

TOP_POLICIES = 6
TOP_PROGRAMS = 4


def _short(text: str | None, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def to_item(points: float, why: list[str], row: dict, sigungu_cd: str) -> dict:
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
    return item


def recommend(session: Session | None, profile: dict, answers: dict, today: date | None = None) -> dict:
    today = today or date.today()
    summary = summarize(answers)
    rows, source = find_candidates(session, profile["sigungu_cd"], profile.get("age"), today)
    policies = rank([r for r in rows if r["kind"] == "policy"], profile, summary, TOP_POLICIES)
    programs = rank([r for r in rows if r["kind"] == "program"], profile, summary, TOP_PROGRAMS)
    return {
        "summary": summary,
        "policies": [to_item(s, w, r, profile["sigungu_cd"]) for s, w, r in policies],
        "programs": [to_item(s, w, r, profile["sigungu_cd"]) for s, w, r in programs],
        "candidates": {"policy": sum(r["kind"] == "policy" for r in rows),
                       "program": sum(r["kind"] == "program" for r in rows)},
        "source": source,
        "notice": "추천은 신청 자격을 확정하지 않아요. 신청 전에 공식 공고에서 조건을 꼭 확인해 주세요.",
    }
