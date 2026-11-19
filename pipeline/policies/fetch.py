"""정책 수집: 온통청년 청년정책 API 전체 → CSV/JSONL 저장. 파이프라인 첫 단계.

사용법 (저장소 루트에서):
  키는 저장소 루트 .env 의 YOUTH_POLICY_API_KEY (프로세스 환경변수가 우선, 옛 이름 YOUTH_API_KEY 도 허용).
  python pipeline/policies/fetch.py            # 전국 전체
  python pipeline/policies/fetch.py 11000      # 서울만 (법정시군구코드, 쉼표로 여러 개 가능)

출력 (data/runtime/policies/):
  policies_raw.jsonl    API 원본 그대로 (재처리용, 버리지 말 것)
  policies.csv          정책 1행 = 1정책. 코드값을 이름으로 풀고 특수값(99999 등)을 정리한 버전
                        situations 열: 특수 상황 태그(군인·임신·출산·육아 등, 쉼표 구분, 빈값 = 누구나)
  policy_regions.csv    정책-지역(시군구 코드) 연결표
  policy_codes.csv      정책-요건코드(취업/학력/전공/특화) 연결표
  fill_rate.csv         필드별 채움률
키는 파일에 저장하지 않습니다.
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"
PAGE_SIZE = 100
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402

OUT = paths.POLICY_DIR

# API코드정보.xlsx 기준
CODES = {
    "0054001": "중앙부처", "0054002": "지자체",
    "0042001": "인프라 구축", "0042002": "프로그램", "0042003": "직접대출", "0042004": "공공기관",
    "0042005": "계약(위탁운영)", "0042006": "보조금", "0042007": "대출보증", "0042008": "공적보험",
    "0042009": "조세지출", "0042010": "바우처", "0042011": "정보제공", "0042012": "경제적 규제", "0042013": "기타",
    "0044001": "신청", "0044002": "승인", "0044003": "반려", "0044004": "임시저장",
    "0057001": "특정기간", "0057002": "상시", "0057003": "마감",
    "0056001": "특정기간", "0056002": "기타",
    "0055001": "기혼", "0055002": "미혼", "0055003": "제한없음",
    "0043001": "무관", "0043002": "연소득", "0043003": "기타",
    "0011001": "인문계열", "0011002": "사회계열", "0011003": "상경계열", "0011004": "이학계열",
    "0011005": "공학계열", "0011006": "예체능계열", "0011007": "농산업계열", "0011008": "기타", "0011009": "제한없음",
    "0013001": "재직자", "0013002": "자영업자", "0013003": "미취업자", "0013004": "프리랜서",
    "0013005": "일용근로자", "0013006": "(예비)창업자", "0013007": "단기근로자", "0013008": "영농종사자",
    "0013009": "기타", "0013010": "제한없음",
    "0049001": "고졸 미만", "0049002": "고교 재학", "0049003": "고졸 예정", "0049004": "고교 졸업",
    "0049005": "대학 재학", "0049006": "대졸 예정", "0049007": "대학 졸업", "0049008": "석·박사",
    "0049009": "기타", "0049010": "제한없음",
    "0014001": "중소기업", "0014002": "여성", "0014003": "기초생활수급자", "0014004": "한부모가정",
    "0014005": "장애인", "0014006": "농업인", "0014007": "군인", "0014008": "지역인재",
    "0014009": "기타", "0014010": "제한없음",
}
SINGLE_CODE_FIELDS = ["pvsnInstGroupCd", "plcyPvsnMthdCd", "plcyAprvSttsCd", "aplyPrdSeCd",
                      "bizPrdSeCd", "mrgSttsCd", "earnCndSeCd"]
MULTI_CODE_FIELDS = {"jobCd": "취업", "schoolCd": "학력", "plcyMajorCd": "전공", "sbizCd": "특화"}
TEXT_FIELDS = ["plcySprtCn", "earnEtcCn", "addAplyQlfcCndCn", "ptcpPrpTrgtCn", "sbmsnDcmntCn",
               "srngMthdCn", "plcyAplyMthdCn", "aplyUrlAddr", "refUrlAddr1", "etcMttrCn", "aplyYmd"]


def get_key():
    return paths.require_env("YOUTH_POLICY_API_KEY", "YOUTH_API_KEY")


def get(params):
    q = urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{URL}?{q}", timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # 네트워크 일시 오류 재시도
            if attempt == 2:
                raise
            print("  재시도:", e)
            time.sleep(2)


def find_list(obj):
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = find_list(v)
            if found is not None:
                return found
    return None


def find_total(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.lower() in ("totcount", "totalcount", "tot_count", "total"):
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
            t = find_total(v)
            if t is not None:
                return t
    return None


# 특수 상황 태그: 해당 상황인 사용자에게만 보여줄 정책을 표시한다 (규칙 기반, LLM 없음)
SITUATION_SBIZ = {  # sbizCd 특화분야 → 상황 태그 (제한없음·기타 제외)
    "0014001": "중소기업재직", "0014002": "여성", "0014003": "기초생활수급자", "0014004": "한부모가정",
    "0014005": "장애인", "0014006": "농업인", "0014007": "군인", "0014008": "지역인재",
}
SITUATION_MRG = {"0055001": "기혼", "0055002": "미혼"}   # 0055003 = 제한없음
SITUATION_NAME_RULES = [  # 코드로 안 잡히는 상황은 정책명으로 보완
    (re.compile(r"임신|난임|산후|산모|출산|출생"), "임신·출산"),
    (re.compile(r"육아|양육|(?<!창업)(?<!창업 )보육|아이돌봄|자녀"), "육아"),   # 창업보육센터 제외
    (re.compile(r"군복무|군 복무|장병|입영|제대군인|군인"), "군인"),
    (re.compile(r"한부모"), "한부모가정"),
    (re.compile(r"장애인"), "장애인"),
    (re.compile(r"자립준비청년|보호종료"), "자립준비청년"),
    (re.compile(r"가족돌봄"), "가족돌봄청년"),
]
KEYWORD_SPAM_LIMIT = 6   # 키워드가 이보다 많이 붙은 정책은 키워드를 믿지 않는다 (17개 전부 붙은 사례 있음)


def situations_of(it):
    tags = []
    def add(t):
        if t not in tags:
            tags.append(t)
    for c in split_codes(it.get("sbizCd")):
        if c in SITUATION_SBIZ:
            add(SITUATION_SBIZ[c])
    mrg = str(it.get("mrgSttsCd", "")).strip()
    if mrg in SITUATION_MRG:
        add(SITUATION_MRG[mrg])
    kws = split_codes(it.get("plcyKywdNm"))
    if len(kws) <= KEYWORD_SPAM_LIMIT:
        if "출산" in kws:
            add("임신·출산")
        if "육아" in kws:
            add("육아")
    name = str(it.get("plcyNm", ""))
    for pat, tag in SITUATION_NAME_RULES:
        if pat.search(name):
            add(tag)
    return tags


def split_codes(v):
    return [c.strip() for c in str(v or "").split(",") if c.strip()]


def is_empty(v):
    return str(v if v is not None else "").strip() in ("", "-", "null", "None")


def to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def main():
    key = get_key()
    zip_cd = sys.argv[1] if len(sys.argv) > 1 else None
    OUT.mkdir(parents=True, exist_ok=True)

    items, page, total = [], 1, None
    while True:
        params = {"apiKeyNm": key, "pageNum": page, "pageSize": PAGE_SIZE, "rtnType": "json"}
        if zip_cd:
            params["zipCd"] = zip_cd
        data = get(params)
        if page == 1:
            total = find_total(data)
            print("전체 건수(응답 기준):", total)
        batch = find_list(data) or []
        if not batch:
            if page == 1:
                print("목록을 찾지 못했습니다. 응답 앞부분:\n", json.dumps(data, ensure_ascii=False)[:1500])
            break
        items.extend(batch)
        print(f"  {page}페이지 +{len(batch)} (누적 {len(items)})")
        if len(batch) < PAGE_SIZE or (total and len(items) >= total):
            break
        page += 1
        time.sleep(0.3)  # 서버 부담 줄이기

    # 중복 제거 (plcyNo 기준)
    seen, uniq = set(), []
    for it in items:
        k = it.get("plcyNo") or json.dumps(it, sort_keys=True)
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    items = uniq

    with open(OUT / "policies_raw.jsonl", "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    # 정리된 정책 표
    rows, regions, codes = [], [], []
    for it in items:
        no = it.get("plcyNo")
        row = dict(it)
        for fld in SINGLE_CODE_FIELDS:
            if fld in it:
                row[fld + "_nm"] = CODES.get(str(it[fld]).strip(), it[fld])
        lo, hi = to_int(it.get("sprtTrgtMinAge")), to_int(it.get("sprtTrgtMaxAge"))
        row["age_min_clean"] = None if lo in (None, 0) else lo
        row["age_max_clean"] = None if hi in (None, 0) or hi >= 99 else hi      # 0·99·99999 = 제한없음
        emax = to_int(it.get("earnMaxAmt"))
        row["earn_max_clean"] = None if emax is None or emax >= 99999 else emax
        sec = str(it.get("aplyPrdSeCd", "")).strip()   # 코드(0057003)나 이름(마감) 어느 쪽으로 와도 처리
        row["is_closed"] = CODES.get(sec, sec) == "마감"
        row["region_count"] = len(split_codes(it.get("zipCd")))
        row["situations"] = ",".join(situations_of(it))   # 비어 있으면 누구에게나 해당
        for fld, label in MULTI_CODE_FIELDS.items():
            names = [CODES.get(c, c) for c in split_codes(it.get(fld))]
            row[fld + "_nm"] = ",".join(names)
            for c in split_codes(it.get(fld)):
                codes.append({"plcyNo": no, "kind": label, "code": c, "name": CODES.get(c, c)})
        for z in split_codes(it.get("zipCd")):
            regions.append({"plcyNo": no, "zipCd": z})
        rows.append(row)

    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    write_csv(OUT / "policies.csv", rows, cols)
    write_csv(OUT / "policy_regions.csv", regions, ["plcyNo", "zipCd"])
    write_csv(OUT / "policy_codes.csv", codes, ["plcyNo", "kind", "code", "name"])

    # 채움률 (전체 / 마감 제외)
    live = [r for r in rows if not r["is_closed"]]
    fill = []
    for k in [c for c in cols if c in items[0] or c in TEXT_FIELDS]:
        fill.append({
            "field": k,
            "all_pct": round(100 * sum(not is_empty(r.get(k)) for r in rows) / max(len(rows), 1)),
            "open_pct": round(100 * sum(not is_empty(r.get(k)) for r in live) / max(len(live), 1)),
        })
    write_csv(OUT / "fill_rate.csv", fill, ["field", "all_pct", "open_pct"])

    print(f"\n완료: 정책 {len(rows)}건 (마감 제외 {len(live)}건), 지역연결 {len(regions)}행 → {OUT.resolve()}")
    for f_ in fill:
        if f_["field"] in TEXT_FIELDS:
            print(f"  {f_['field']:18} 전체 {f_['all_pct']:3}%  마감제외 {f_['open_pct']:3}%")


def write_csv(path, rows, cols):
    # utf-8-sig: 엑셀에서 한글 안 깨짐. 줄바꿈 들어간 텍스트도 따옴표로 안전하게 저장됨
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    main()
