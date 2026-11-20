"""추천 규칙: 자격 확인 → 점수 → 목록 정리. 순수 함수 (DB 없이 테스트 가능).

입력
  row      catalog_items 행 (app/catalog/rows.py 형식: kind, title, domains, situations, access_type, payload …)
  profile  기본 정보: age, sex, sigungu_cd, job, school, situations
  summary  상태 체크 요약 (app/checkin/summary.py)

LLM 을 쓰지 않는다. 같은 입력이면 항상 같은 결과이고, 항목마다 추천 이유(why)를 돌려준다.
가중치는 MVP 초안 — 근거와 변경 기록은 docs/RECOMMENDATION.md '추천 알고리즘'.
"""
from __future__ import annotations

import math
import re

from app.catalog.rows import scope_of

DOMAIN_REASON = {
    "E": {"high": "생활비·취업 준비 부담이 크다고 했어요", "mid": "생활비·취업 준비가 조금 부담된다고 했어요"},
    "P": {"high": "정기적으로 하는 활동이 없다고 했어요", "mid": "정기 활동이 가끔 있다고 했어요"},
    "O": {"high": "밖에 거의 안 나간다고 했어요", "mid": "가끔 밖에 나간다고 했어요"},
    "C": {"high": "이야기 나눌 시간이 부족하다고 했어요", "mid": "이야기 나눌 시간이 보통이라고 했어요"},
    "U": {"high": "도움을 부탁할 사람이 없다고 했어요", "mid": "도움을 부탁할 사람이 있는지 잘 모르겠다고 했어요"},
}
LEVEL_POINTS = {"high": 30, "mid": 18}

# ── 관심 분야 → 정책 중분류(mclsfNm) + 정책명 (프로그램은 LLM 이 고른 topics 를 그대로 쓴다)
MIND = re.compile(r"마음|심리|상담|우울|자살|고립|은둔|중독|정신")
MEET = re.compile(r"모임|커뮤니티|소셜|동아리|네트워킹|만남|아지트|청년공간|라운지|쉼터|다이닝")
ABROAD = re.compile(r"국제|해외|글로벌|한류|참전국|외교")
INTERESTS = {
    "일자리·취업": {"mclsf": {"취업", "재직자"}},
    "창업": {"mclsf": {"창업"}},
    "집·주거": {"mclsf": {"전월세 및 주거급여 지원", "주택 및 거주지", "기숙사"}},
    "생활비·금융": {"mclsf": {"취약계층 및 금융지원"}},
    "교육·자격증": {"mclsf": {"교육비지원", "미래역량강화", "온·오프라인교육", "온라인교육"}},
    "마음건강·상담": {"mclsf": {"건강"}, "name": MIND},
    "몸 건강·식사": {"mclsf": {"건강"}, "name_not": MIND},
    "문화·여가": {"mclsf": {"문화활동 및 생활지원", "문화활동"}, "domains": {"O", "P"}},
    "사람 만나기·모임": {"mclsf": {"청년참여", "문화활동 및 생활지원", "정책인프라구축"}, "name": MEET,
                         "name_not": ABROAD, "or_domains": {"P", "C"}},
    "해외 경험": {"mclsf": {"청년국제교류"}},
}

# ── 지금 하는 일 → 정책 취업요건(jobCd_nm), 학생이면 학력요건(schoolCd_nm)
JOB = {
    "구직 중": {"미취업자"}, "회사원": {"재직자"}, "아르바이트·단기": {"단기근로자", "일용근로자"},
    "프리랜서": {"프리랜서"}, "창업·자영업": {"(예비)창업자", "자영업자"}, "농어업": {"영농종사자"},
    "학생": {"미취업자"}, "쉬는 중": {"미취업자"},
}
SCHOOL = {"고등학생": {"고교 재학", "고졸 예정"}, "대학생": {"대학 재학", "대졸 예정"}, "대학원생": {"석·박사"}}
JOB_SITUATIONS = {"농어업": {"농업인"}}   # 회사원의 '중소기업재직'은 추가 질문으로 profile.situations 에 들어온다

# ── 상황: 자격 상황은 정책에 붙은 것을 모두 충족 / 생애 단계는 하나만 겹쳐도 됨
GATE = {"한부모가정", "장애인", "기초생활수급자", "자립준비청년", "가족돌봄청년", "군인", "농업인",
        "중소기업재직", "지역인재", "여성"}
STAGE = {"기혼", "미혼", "임신·출산", "육아"}

MAX_PER_DOMAIN = 3

# ── 특정 대상만 신청할 수 있는데 기본 정보로 확인할 수 없는 사업 (제목 기준).
# 자격 조건 원문(addAplyQlfcCndCn)은 '국가유공자 우대'처럼 여러 대상 중 하나로 적힌 경우가 많아 쓰지 않는다.
# 예: 자살시도자 치료비(응급실 내원자), 중독자 치료, 전세사기 피해자, 외국인근로자, 다문화·북한이탈 청년, 제대군인,
#     경계선지능인. (보호종료·발달장애처럼 상황 태그로 거를 수 있는 대상은 GATE 가 처리한다)
SPECIAL_TARGET = re.compile(
    r"자살\s*시도|중독자|외국인\s*근로자|전세\s*(?:사기|피해)|다문화|북한\s*이탈|탈북|제대\s*군인|경계선\s*지능")


def _names(text: str | None) -> set[str]:
    return {x.strip() for x in (text or "").split(",") if x.strip()} - {"제한없음", "기타"}


def my_situations(profile: dict) -> set[str]:
    mine = set(profile.get("situations") or [])
    if profile.get("sex") == "여":
        mine.add("여성")
    mine |= JOB_SITUATIONS.get(profile.get("job") or "", set())
    return mine


def eligible(row: dict, profile: dict, allow_special: bool = False) -> bool:
    """나이·거주지·마감은 조회 단계(DB 또는 rows.matches_basic)에서 거른다. 여기서는 특정 대상·취업·학력·상황.

    allow_special: 사용자가 직접 찾은 경우(대화 검색)에는 특정 대상 사업도 보여준다. 자동 추천에서는 False.
    """
    payload = row["payload"]
    if not allow_special and SPECIAL_TARGET.search(row["title"]):
        return False
    if row["kind"] == "policy":
        jobs = _names(payload.get("jobCd_nm"))
        if jobs and profile.get("job") and not (jobs & JOB.get(profile["job"], set())):
            return False
        schools = _names(payload.get("schoolCd_nm"))
        if schools and profile.get("school") and not (schools & SCHOOL.get(profile["school"], set())):
            return False
    mine = my_situations(profile)
    tags = set(row["situations"])
    if (tags & GATE) - mine:
        return False
    if tags & STAGE and not (tags & STAGE & mine):
        return False
    return True


def interest_match(row: dict, key: str) -> bool:
    if row["kind"] == "program":
        return key in (row["payload"].get("topics") or [])
    rule = INTERESTS[key]
    name = row["title"]
    mcl = {m.strip() for m in (row["payload"].get("mclsfNm") or "").split(",")}
    if "name_not" in rule and rule["name_not"].search(name):
        return False
    if "or_domains" in rule and rule["name"].search(name) and set(row["domains"]) & rule["or_domains"]:
        return True
    if not (mcl & rule["mclsf"]):
        return False
    if "name" in rule and not rule["name"].search(name):
        return False
    if "domains" in rule and not (set(row["domains"]) & rule["domains"]):
        return False
    return True


def score(row: dict, profile: dict, summary: dict) -> tuple[float, list[str]]:
    s, why = 0.0, []
    levels = summary.get("levels", {})
    domains = row["domains"]

    best, reason = 0.0, ""
    for i, d in enumerate(domains):          # 주 영역(첫 번째)은 만점, 두 번째는 절반
        level = levels.get(d)
        if level in LEVEL_POINTS:
            points = LEVEL_POINTS[level] * (1.0 if i == 0 else 0.5)
            if points > best:
                best, reason = points, DOMAIN_REASON[d][level]
    if best:
        s += best
        why.append(reason)

    hits = [k for k in summary.get("interests", []) if interest_match(row, k)]
    if hits:
        s += 10
        why.append("관심 분야: " + ", ".join(hits))

    matched = set(row["situations"]) & my_situations(profile)
    if matched:
        s += 10
        why.append("내 상황에 맞는 지원: " + ", ".join(sorted(matched)))

    scope = scope_of(row, profile["sigungu_cd"])
    if row["kind"] == "program":
        if scope == "시군구":
            s += 10
            why.append("우리 동네 청년센터")
        if row["payload"].get("evergreen"):
            s -= 4
    else:
        s += {"시군구": 4, "광역": 2}.get(scope, 0)

    face = summary.get("face_to_face")
    if face in ("high", "mid") and domains:
        in_person = domains[0] in ("P", "C") or row["access_type"] == "visit"
        if in_person:
            s -= 8 if face == "high" else 3

    s += min(math.log10((row["payload"].get("inqCnt") or 0) + 1), 4) * 0.5   # 동점 정리용
    return s, why


def rank(rows: list[dict], profile: dict, summary: dict, top: int) -> list[tuple[float, list[str], dict]]:
    focus = set(summary.get("priority_domains", []))
    cap = MAX_PER_DOMAIN if len(focus) != 1 else top   # 필요한 영역이 하나뿐이면 그 영역으로 채운다
    seen: set[str] = set()
    per_domain: dict[str, int] = {}
    out = []
    scored = sorted(((score(r, profile, summary), r) for r in rows if eligible(r, profile)),
                    key=lambda x: (-x[0][0], x[1]["id"]))
    for (points, why), row in scored:
        key = "".join(ch for ch in row["title"] if ch.isalnum())[:12]   # 같은 사업 중복 정리
        main = row["domains"][0] if row["domains"] else "-"
        if key in seen or per_domain.get(main, 0) >= cap:
            continue
        seen.add(key)
        per_domain[main] = per_domain.get(main, 0) + 1
        out.append((round(points, 1), why, row))
        if len(out) >= top:
            break
    return out
