"""정책 분류 (LLM, 캐시) — pipeline/policies/fetch.py 다음에 실행.

입력:  data/runtime/policies/policies.csv          (fetch.py 결과, situations 규칙 태그 포함)
캐시:  data/runtime/cache/policy_tags_cache.jsonl   plcyNo + lastMdfcnDt + 프롬프트 버전 기준. 새로 등록·수정된 정책만 LLM 호출
       (처음이면 data/seed/cache/ 의 캐시로 시작)
출력:  data/runtime/policies/policy_tags.csv        plcyNo, i5_domains, access_type, situations, confidence, status, model
       data/runtime/serving/policies_serving.json   status=ok 인 정책만, 화면·추천에 필요한 필드만 → load_catalog.py 가 DB에 적재

필드 정의와 프롬프트 변경 기록: docs/RECOMMENDATION.md

사용법 (저장소 루트에서):
  python pipeline/policies/classify.py --limit 40     # 먼저 40건만 분류해서 결과 확인
  python pipeline/policies/classify.py                # 마감 제외 전체 (캐시된 건 건너뜀)
  python pipeline/policies/classify.py --dry-run      # LLM 호출 없이 첫 배치 프롬프트만 출력
  python pipeline/policies/classify.py --no-llm       # LLM 없이 캐시로 결과 파일만 다시 생성
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
from pipeline.llm import ACCESS_TYPES, BATCH, DOMAINS, SITUATIONS, chat, llm_config, status_of  # noqa: E402

POLICIES = paths.POLICY_DIR / "policies.csv"
CACHE_NAME = "policy_tags_cache.jsonl"
CACHE = paths.CACHE_DIR / CACHE_NAME
TAGS = paths.POLICY_DIR / "policy_tags.csv"
SERVING = paths.SERVING_DIR / "policies_serving.json"

PROMPT_VERSION = "v4"
# 이전 버전 결과 중 다시 분류하지 않고 그대로 쓰는 경우 (none·영역 없음은 v4에서도 제외·보류라 결과가 같다)
REUSABLE_VERSIONS = {"v3"}
ACCESS_TYPES = ("apply", "visit", "none")

SYSTEM = f"""너는 한국 청년정책 분류기다. 각 정책을 아래 기준으로 분류해 JSON으로만 답한다.

i5_domains: 이 정책이 청년의 어떤 어려움을 직접 덜어주는가. 해당하는 것만 0~2개.
  E 경제: 소득·일자리·창업·생활비·주거비·대출·자산형성·출산/육아 지원금 등 돈과 생계
  P 모임 참여: 동아리·소모임·커뮤니티·봉사 등 단체 활동에 참여할 기회
  O 외출·여가: 문화·체육·여행·여가 활동을 하러 밖에 나갈 계기 (문화패스, 공연·체험 등)
  C 사람과의 교류: 새로운 사람을 만나고 관계를 맺는 기회 (만남·교류 프로그램, 청년공간 네트워킹)
  U 도움·상담: 힘들 때 기댈 곳 — 심리상담, 마음건강, 고립·은둔 지원, 위기 지원, 생활 돌봄
  교육·자격증·역량강화처럼 위 다섯에 직접 해당하지 않으면 E(취업 준비) 또는 빈 배열.

access_type: 청년 개인이 이 정책을 어떻게 이용하나. 셋 중 하나.
  apply: 신청·선정을 거쳐 받는 혜택 (지원금, 대출·이자 지원, 바우처, 교육·프로그램 참가자 모집, 일자리 사업)
  visit: 신청 없이 또는 간단한 예약으로 가서 이용·참여하는 곳이나 행사
         (청년공간·청년센터·일자리센터 이용과 상담, 청년주간·축제·공연 관람, 상시 상담 창구)
  none: 개인이 이용할 수 없음 (시설 조성·건립·리모델링, 대회·행사 유치 자체, 위원회·협의체·정책네트워크 위원 운영,
        기업·기관 육성 지원, 공무원·종사자 대상, 정책 홍보)
  판단 기준은 '청년 개인이 이 사업으로 직접 무언가를 받거나, 가서 이용·참여할 수 있는가'다.
  - '~운영', '~개최'는 청년이 이용·참여하는 공간·행사면 visit, 기업·기관을 돕는 시설이면 none
  - '~조성', '~체계구축', '~개선사업', '~유치', '~육성'처럼 인프라를 만들거나 기업·산업을 키우는 사업은 none
  예) 청년공간 ○○ 운영 → visit / 청년주간 개최 → visit / 일자리센터 운영(상담) → visit
      대학가 문화거리 조성 → none / 산업단지 정주여건 개선 → none / 게임기업 지원센터 운영 → none
      스마트팜 사관학교 체계구축 → none / 영농정착지원금 → apply / 청년정책네트워크 위원 모집 → apply

situations: 특정 상황인 사람만 받을 수 있는 정책이면 그 상황. 누구나 받을 수 있으면 빈 배열.
  고를 수 있는 값: {", ".join(SITUATIONS)}
  rule_hint는 데이터 코드에서 뽑은 참고값이며 틀릴 수 있다 (예: 미혼 코드가 붙은 신혼부부 정책 → 기혼).

confidence: 위 판단에 확신이 있으면 "high", 아래 중 하나라도 해당하면 "low".
  - 혜택인지, 이용하는 공간·행사인지, 기관 사업인지 정보만으로 구분하기 어렵다
  - i5_domains가 애매하다 (예: 결혼식·이사처럼 다섯 영역 어디에도 딱 맞지 않음)
  - 정책명과 설명이 짧거나 서로 맞지 않는다
  low는 서비스에서 보류되므로, 확실하지 않으면 low로 답한다.

출력 형식: {{"results": [{{"id": "정책번호", "i5_domains": ["E"], "access_type": "apply", "situations": [], "confidence": "high"}}, ...]}}
입력의 모든 id에 대해 하나씩 답한다."""


def policy_input(r):
    return {
        "id": r["plcyNo"],
        "name": r["plcyNm"].strip(),
        "category": r["mclsfNm"].strip(),
        "summary": " ".join(r["plcyExplnCn"].split())[:300],
        "support": " ".join(r["plcySprtCn"].split())[:300],
        "rule_hint": r.get("situations", ""),
    }


def clean_result(res):
    doms = [d for d in res.get("i5_domains", []) if d in DOMAINS][:2]
    sits = [s for s in res.get("situations", []) if s in SITUATIONS]
    acc = res.get("access_type")
    conf = res.get("confidence")
    return {"i5_domains": doms, "access_type": acc if acc in ACCESS_TYPES else None, "situations": sits,
            "confidence": conf if conf in ("high", "low") else "low"}


def load_cache():
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                cache[e["plcyNo"]] = e
    return cache


def cache_key_ok(entry, r):
    if entry.get("lastMdfcnDt") != r["lastMdfcnDt"]:
        return False
    if entry.get("prompt_version") == PROMPT_VERSION:
        return True
    # v3의 none·영역 없음 결과는 v4에서도 제외·보류라 다시 분류하지 않는다
    return entry.get("prompt_version") in REUSABLE_VERSIONS and (
        entry.get("access_type") == "none" or not entry.get("i5_domains"))


def write_tags(rows, cache):
    with open(TAGS, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["plcyNo", "i5_domains", "access_type", "situations", "confidence", "status", "model"])
        for r in rows:
            e = cache.get(r["plcyNo"])
            if e and cache_key_ok(e, r):
                w.writerow([r["plcyNo"], ",".join(e["i5_domains"]), e.get("access_type") or "",
                            ",".join(e["situations"]), e.get("confidence", ""), status_of(e), e["model"]])


# 서비스용 JSON에 넣는 원본 필드 (담당자 개인 이름 *PicNm 은 넣지 않는다)
SERVING_FIELDS = [
    "plcyNm", "plcyExplnCn", "plcySprtCn", "lclsfNm", "mclsfNm", "plcyKywdNm",
    "aplyPrdSeCd_nm", "aplyYmd", "bizPrdBgngYmd", "bizPrdEndYmd", "bizPrdEtcCn",
    "age_min_clean", "age_max_clean", "mrgSttsCd_nm", "earnCndSeCd_nm", "earn_max_clean", "earnEtcCn",
    "jobCd_nm", "schoolCd_nm", "plcyMajorCd_nm", "sbizCd_nm", "addAplyQlfcCndCn", "ptcpPrpTrgtCn",
    "plcyAplyMthdCn", "srngMthdCn", "sbmsnDcmntCn", "etcMttrCn", "aplyUrlAddr", "refUrlAddr1", "refUrlAddr2",
    "sprtSclCnt", "sprtArvlSeqYn", "sprvsnInstCdNm", "operInstCdNm", "pvsnInstGroupCd_nm",
    "inqCnt", "frstRegDt", "lastMdfcnDt",
]
INT_FIELDS = {"age_min_clean", "age_max_clean", "earn_max_clean", "sprtSclCnt", "inqCnt"}


NATIONWIDE = 240   # zipCd 가 이 개수 이상이면 전국
CHANGUP_BOYUK = re.compile(r"창업\s*보육|인큐베이")
CHILDCARE = re.compile(r"육아|양육|어린이집|아이|자녀|영유아")


def inst_sido_map(rows):
    """등록 최상위기관 코드(앞 3자리) → zipCd 시도(앞 2자리). 지역이 제대로 들어간 지자체 정책에서 학습한다.
    (전남광주통합특별시처럼 기관코드와 지역코드 시도가 다른 곳이 있어 고정표 대신 데이터로 맞춘다)"""
    votes = collections.defaultdict(collections.Counter)
    for r in rows:
        zips = [z for z in r.get("zipCd", "").split(",") if z.strip()]
        inst = r.get("rgtrHghrkInstCd", "")[:3]
        if r.get("pvsnInstGroupCd_nm") == "지자체" and inst and 0 < len(zips) < NATIONWIDE:
            for z in zips:
                votes[inst][z.strip()[:2]] += 1
    return {inst: c.most_common(1)[0][0] for inst, c in votes.items()}


def fix_region(r, zips, sido_map):
    """지자체 정책인데 zipCd 가 전국으로 들어온 경우(원본 오류) → 등록기관 시도로 좁힌다."""
    if len(zips) < NATIONWIDE or r.get("pvsnInstGroupCd_nm") != "지자체":
        return zips, False
    sido = sido_map.get(r.get("rgtrHghrkInstCd", "")[:3])
    if not sido:
        return zips, False
    return [z for z in zips if z.startswith(sido)], True


def fix_situations(name, sits):
    """'창업보육센터'의 '보육'이 육아로 잘못 붙은 경우를 바로잡는다."""
    if "육아" in sits and CHANGUP_BOYUK.search(name) and not CHILDCARE.search(CHANGUP_BOYUK.sub("", name)):
        return [s for s in sits if s != "육아"]
    return sits


def region_scope(zips):
    return "전국" if len(zips) >= NATIONWIDE else "시군구" if len(zips) <= 5 else "광역"


def write_serving(rows, cache):
    items, counts = [], {"ok": 0, "hold": 0, "excluded": 0, "unclassified": 0}
    sido_map = inst_sido_map(rows)
    fixed = {"region": 0, "situations": 0}
    for r in rows:
        e = cache.get(r["plcyNo"])
        if not (e and cache_key_ok(e, r)):
            counts["unclassified"] += 1
            continue
        st = status_of(e)
        counts[st] += 1
        if st != "ok":
            continue
        item = {"plcyNo": r["plcyNo"]}
        for k in SERVING_FIELDS:
            v = (r.get(k) or "").strip()
            if k in INT_FIELDS:
                v = int(float(v)) if v else None
            item[k] = v
        zips, region_fixed = fix_region(r, [z.strip() for z in r.get("zipCd", "").split(",") if z.strip()], sido_map)
        sits = fix_situations(r["plcyNm"], e["situations"])
        fixed["region"] += region_fixed
        fixed["situations"] += sits != e["situations"]
        item["zipCd"] = zips
        item["region_scope"] = region_scope(zips)
        item["region_fixed"] = region_fixed
        item["i5_domains"] = e["i5_domains"]
        item["access_type"] = e["access_type"]
        item["situations"] = sits
        items.append(item)
    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "온통청년 청년정책 API (pipeline/policies/fetch.py) + pipeline/policies/classify.py 분류",
        "counts": counts,
        "fixed": fixed,
        "policies": items,
    }
    paths.write_atomic(SERVING, json.dumps(data, ensure_ascii=False))   # 다 쓴 뒤 교체 (실패해도 이전 파일 유지)
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, help="이번 실행에서 새로 분류할 최대 건수")
    ap.add_argument("--include-closed", action="store_true", help="마감 정책도 분류")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="LLM 호출 없이 결과 파일만 다시 생성")
    args = ap.parse_args()

    if not POLICIES.exists():
        sys.exit(f"{POLICIES} 가 없습니다. pipeline/policies/fetch.py 를 먼저 실행하세요.")
    with open(POLICIES, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if args.include_closed or r["is_closed"] != "True"]
    paths.cache_file(CACHE_NAME)   # 처음이면 seed 캐시 복사
    cache = load_cache()
    todo = [r for r in rows if not (r["plcyNo"] in cache and cache_key_ok(cache[r["plcyNo"]], r))]
    cached = len(rows) - len(todo)
    if args.limit:
        todo = todo[: args.limit]
    print(f"대상 {len(rows)}건 중 이미 분류 {cached}건, 이번에 분류 {len(todo)}건")

    if args.dry_run:
        batch = [policy_input(r) for r in todo[:BATCH]]
        print(SYSTEM, "\n---\n", json.dumps({"policies": batch}, ensure_ascii=False, indent=1)[:3000])
        return
    if not todo or args.no_llm:
        write_tags(rows, cache)
        counts = write_serving(rows, cache)
        print(f"LLM 호출 없음 → {TAGS}, {SERVING}\n상태: {counts}")
        return

    key, base, model = llm_config()
    tokens_in = tokens_out = failed = 0
    with open(CACHE, "a", encoding="utf-8") as cf:
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            user = json.dumps({"policies": [policy_input(r) for r in batch]}, ensure_ascii=False)
            try:
                content, usage = chat(key, base, model, SYSTEM, user)
                results = {str(x.get("id")): x for x in json.loads(content).get("results", [])}
            except (RuntimeError, json.JSONDecodeError, AttributeError) as e:
                print(f"  배치 {i // BATCH + 1} 실패 (다음 실행 때 다시 시도): {e}")
                failed += len(batch)
                continue
            tokens_in += usage.get("prompt_tokens", 0)
            tokens_out += usage.get("completion_tokens", 0)
            for r in batch:
                res = results.get(r["plcyNo"])
                if res is None:
                    failed += 1
                    continue
                entry = {"plcyNo": r["plcyNo"], "lastMdfcnDt": r["lastMdfcnDt"], "prompt_version": PROMPT_VERSION,
                         "model": model, **clean_result(res)}
                cache[r["plcyNo"]] = entry
                cf.write(json.dumps(entry, ensure_ascii=False) + "\n")
            cf.flush()
            done = min(i + BATCH, len(todo))
            print(f"  {done}/{len(todo)}  (토큰 입력 {tokens_in:,} / 출력 {tokens_out:,})")

    write_tags(rows, cache)
    counts = write_serving(rows, cache)
    print(f"\n완료: 분류 {len(todo) - failed}건, 실패 {failed}건 → {TAGS}, {SERVING}")
    print(f"상태: {counts}  (ok만 서비스에 사용)")
    print(f"사용 토큰: 입력 {tokens_in:,} / 출력 {tokens_out:,}")


if __name__ == "__main__":
    main()
