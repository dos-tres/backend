"""페르소나로 추천 결과 확인 (DB·서버 없이, 서비스 JSON 으로).

  python scripts/recommend_demo.py
  python scripts/recommend_demo.py --date 2026-11-19

API(POST /api/recommendations)와 같은 규칙(app/recommend/rules.py)과 상태 체크 요약(app/checkin/summary.py)을 쓴다.
후보 조회만 DB 대신 서비스 JSON(data/runtime/serving → 없으면 data/seed/serving)에서 한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.catalog.rows import build_rows, matches_basic, scope_of  # noqa: E402
from app.checkin.summary import summarize  # noqa: E402
from app.recommend.rules import rank  # noqa: E402
from pipeline import paths  # noqa: E402

PERSONAS = [
    {"name": "A. 서울 관악구 24세 여성, 취준 1년째, 집에만 있음",
     "profile": {"age": 24, "sex": "여", "sigungu_cd": "11620", "job": "구직 중", "situations": ["미혼"]},
     "checkin": {"economy": "mid", "participation": "high", "outing": "high", "conversation": "high", "support": "high",
                 "change_wishes": ["E", "O", "C", "U"], "face_to_face": "mid",
                 "interests": ["일자리·취업", "마음건강·상담"]}},
    {"name": "B. 대전 유성구 31세 남성, 기혼·아이 1명, 외벌이로 빠듯함",
     "profile": {"age": 31, "sex": "남", "sigungu_cd": "30200", "job": "회사원", "situations": ["기혼", "육아"]},
     "checkin": {"economy": "high", "participation": "low", "outing": "mid", "conversation": "low", "support": "low",
                 "change_wishes": ["E"], "face_to_face": "low", "interests": ["집·주거", "생활비·금융"]}},
    {"name": "C. 수원 영통구 27세 남성, 직장인, 대체로 괜찮음",
     "profile": {"age": 27, "sex": "남", "sigungu_cd": "41117", "job": "회사원", "situations": ["미혼", "중소기업재직"]},
     "checkin": {"economy": "low", "participation": "low", "outing": "low", "conversation": "mid", "support": "low",
                 "change_wishes": ["C"], "face_to_face": "low", "interests": ["문화·여가", "사람 만나기·모임"]}},
    {"name": "D. 부산 해운대구 36세 여성, 한부모, 혼자 있는 게 편함 (대면 부담 큼)",
     "profile": {"age": 36, "sex": "여", "sigungu_cd": "26350", "job": "아르바이트·단기",
                 "situations": ["한부모가정", "육아", "미혼"]},
     "checkin": {"economy": "high", "participation": "high", "outing": "mid", "conversation": "mid", "support": "high",
                 "change_wishes": ["E", "U"], "face_to_face": "high", "interests": ["생활비·금융", "마음건강·상담"]}},
    {"name": "E. 수원 영통구 19세 남성, 자립준비청년, 일부 문항은 나중에",
     "profile": {"age": 19, "sex": "남", "sigungu_cd": "41117", "job": "학생", "school": "고등학생",
                 "situations": ["자립준비청년", "미혼"]},
     "checkin": {"economy": "high", "participation": "later", "outing": "unknown", "conversation": "high",
                 "support": "high", "interests": ["집·주거", "사람 만나기·모임"]}},
]


def load_rows() -> list[dict]:
    def file(name):
        runtime = paths.SERVING_DIR / name
        return runtime if runtime.exists() else paths.SEED_SERVING_DIR / name
    rows = build_rows("policy", json.loads(file("policies_serving.json").read_text(encoding="utf-8")))
    return rows + build_rows("program", json.loads(file("programs_serving.json").read_text(encoding="utf-8")))


def show(title: str, ranked, sigungu_cd: str) -> None:
    print(f"  ▶ {title}")
    if not ranked:
        print("      (없음)")
    for points, why, row in ranked:
        extra = ""
        if row["kind"] == "program":
            when = "상시·이용 전 확인" if row["payload"].get("evergreen") else (
                f"~{row['deadline']}" if row["deadline"] else "상시")
            extra = f" · {row['payload'].get('center_names', '')[:14]} {when}"
        print(f"   {points:5.1f} [{row['access_type'] or '-':5}|{','.join(row['domains']):4}|{scope_of(row, sigungu_cd)}] "
              f"{row['title'][:44]}{extra}")
        print(f"         └ {' / '.join(why) or '-'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()
    rows = load_rows()
    print(f"기준일 {args.date} · 정책 {sum(r['kind'] == 'policy' for r in rows)}건 · 프로그램 {sum(r['kind'] == 'program' for r in rows)}건")
    for persona in PERSONAS:
        profile, summary = persona["profile"], summarize(persona["checkin"])
        pool = [r for r in rows if matches_basic(r, profile["sigungu_cd"], profile["age"], args.date)]
        print("=" * 100)
        print(persona["name"])
        print(f"  상태 요약: {summary['levels']} → 우선 {summary['priority_domains']} "
              f"(낮춘 영역 {summary['lowered_domains']}, 미응답 {summary['unanswered_domains']}, 대면 부담 {summary['face_to_face']})")
        show(f"정책 (후보 {sum(r['kind'] == 'policy' for r in pool)}건)",
             rank([r for r in pool if r["kind"] == "policy"], profile, summary, 6), profile["sigungu_cd"])
        show(f"청년센터 프로그램 (후보 {sum(r['kind'] == 'program' for r in pool)}건)",
             rank([r for r in pool if r["kind"] == "program"], profile, summary, 4), profile["sigungu_cd"])


if __name__ == "__main__":
    main()
