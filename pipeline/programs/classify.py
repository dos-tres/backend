"""청년센터 프로그램 분류 (LLM, 캐시) — 정책 분류(pipeline/policies/classify.py)와 같은 기준.

입력:  data/runtime/programs/programs.csv   (pipeline/programs/crawl/merge.py 결과)
캐시:  data/runtime/cache/program_tags_cache.jsonl   program_id + 제목·요약 해시 기준. 새 글·바뀐 글만 LLM 호출
       (처음이면 data/seed/cache/ 의 캐시로 시작)
출력:  data/runtime/programs/program_tags.csv             program_id, i5_domains, access_type, topics, situations, confidence, status, model
       data/runtime/serving/programs_serving.json   status=ok 인 프로그램만 → load_catalog.py 가 DB에 적재

대상: is_active=Y 이고 kind=program 이며 신청 마감일이 오늘 이후(또는 없음)인 글
필드:
  i5_domains, situations, confidence, status   정책과 같은 의미
  access_type  apply = 참여자 모집·신청 / visit = 상시 이용·상담 창구·관람 / none = 프로그램이 아님(공지·결과·채용·휴관)
  topics       설문 '관심 분야' 선택지 중 해당하는 것 0~2개 (정책은 중분류로 대신함)

사용법 (저장소 루트에서, 키 설정은 정책 분류와 같다):
  python pipeline/programs/classify.py --limit 40
  python pipeline/programs/classify.py
  python pipeline/programs/classify.py --no-llm
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import paths  # noqa: E402
from pipeline.llm import ACCESS_TYPES, BATCH, DOMAINS, SITUATIONS, chat, llm_config, status_of  # noqa: E402

PROGRAMS = paths.PROGRAM_DIR / "programs.csv"
CACHE_NAME = "program_tags_cache.jsonl"
CACHE = paths.CACHE_DIR / CACHE_NAME
TAGS = paths.PROGRAM_DIR / "program_tags.csv"
SERVING = paths.SERVING_DIR / "programs_serving.json"
PROMPT_VERSION = "p1"

TOPICS = ("일자리·취업", "창업", "집·주거", "생활비·금융", "교육·자격증", "마음건강·상담",
          "몸 건강·식사", "문화·여가", "사람 만나기·모임", "해외 경험")

SYSTEM = f"""너는 청년센터 게시글 분류기다. 각 글을 아래 기준으로 분류해 JSON으로만 답한다.

i5_domains: 이 프로그램이 청년의 어떤 어려움을 직접 덜어주는가. 해당하는 것만 0~2개, 가장 중요한 것을 먼저.
  E 경제: 일자리·취업 준비·창업·주거·재무·생활비
  P 모임 참여: 동아리·소모임·커뮤니티·봉사 등 함께하는 활동에 참여할 기회
  O 외출·여가: 문화·예술·체육·만들기 클래스·전시·공연 등 밖에 나가 즐기는 활동
  C 사람과의 교류: 새로운 사람을 만나고 관계를 맺는 기회 (네트워킹, 함께 밥 먹기, 청년공간 교류)
  U 도움·상담: 심리상담, 마음건강, 고립·은둔 지원, 법률·노무·재무 상담 같은 기댈 곳
  단순 강의·교육은 주제에 따라 E(취업·재무) 또는 O(취미). 어디에도 맞지 않으면 빈 배열.

access_type: 셋 중 하나.
  apply: 참여자를 모집해 신청을 받는 프로그램
  visit: 신청 없이 이용하는 공간·상시 상담 창구·관람 행사
  none: 청년이 참여하는 프로그램이 아님 (합격자·결과 발표, 직원 채용, 휴관·운영 안내, 단순 홍보)

topics: 아래 관심 분야 중 해당하는 것 0~2개.
  {", ".join(TOPICS)}

situations: 특정 상황인 사람만 참여할 수 있으면 그 상황 (예: 1인가구 대상은 해당 없음 → 빈 배열).
  고를 수 있는 값: {", ".join(SITUATIONS)}

confidence: 확신이 있으면 "high". 제목·요약만으로 무슨 프로그램인지 알기 어렵거나 영역이 애매하면 "low".

출력 형식: {{"results": [{{"id": "글번호", "i5_domains": ["O"], "access_type": "apply", "topics": ["문화·여가"], "situations": [], "confidence": "high"}}, ...]}}
입력의 모든 id에 대해 하나씩 답한다."""


# 서울청년센터는 지난 글도 '상시'로 남아 있어 is_active=Y 로 들어온다 → 제목의 날짜로 지난 글을 거른다
YEAR = re.compile(r"(20\d\d)\s*년?")
MONTH_DAY = re.compile(r"(?<!\d)(\d{1,2})\s*[/.]\s*(\d{1,2})(?!\d)")
MONTH = re.compile(r"(?<!\d)(\d{1,2})\s*월")


def stale_reason(r, today):
    """지난 글이면 사유, 아니면 None. 신청 마감일이 있으면 그걸 믿는다(load_targets 에서 이미 비교)."""
    t = r["title"]
    years = [int(y) for y in YEAR.findall(t)]
    if years and max(years) < today.year:
        return "지난 연도"
    if r["aply_end"] or (years and max(years) > today.year):
        return None
    mds = [(int(m), int(d)) for m, d in MONTH_DAY.findall(t) if 1 <= int(m) <= 12 and 1 <= int(d) <= 31]
    if mds and max(mds) < (today.month, today.day):
        return "지난 날짜"
    months = [int(m) for m in MONTH.findall(t) if 1 <= int(m) <= 12]
    if months and max(months) < today.month:
        return "지난 달"
    # 마감일·진행 종료일이 없는 '상시' 글은 본문(요약)의 날짜도 본다 (점검: 9월 체육대회·8월 북캉스가 11월에 '상시'로 추천됨)
    # 상담·공간처럼 계속 운영하는 서비스는 본문에 지난 시작일이 있어도 지금 운영 중일 수 있어 보지 않는다
    if not r.get("prog_end") and not is_evergreen(r):
        dates = body_dates(r.get("summary", ""), today.year)
        if dates and max(dates) < today:
            return "본문 날짜 지남"
    return None


# 본문 날짜: 2026년 9월 12일 / 26. 8. 27. / 2026.08.27 / 9월 12일(올해로 본다)
FULL_DATE = re.compile(r"(?<!\d)(20\d\d|\d\d)\s*[.년/-]\s*(\d{1,2})\s*[.월/-]\s*(\d{1,2})(?!\d)")
KO_MONTH_DAY = re.compile(r"(?<![\d.])(\d{1,2})\s*월\s*(\d{1,2})\s*일")


def body_dates(text, year):
    found = []
    for y, m, d in FULL_DATE.findall(text):
        y = int(y) + (2000 if len(y) == 2 else 0)
        found.append((y, int(m), int(d)))
    rest = FULL_DATE.sub(" ", text)
    found += [(year, int(m), int(d)) for m, d in KO_MONTH_DAY.findall(rest)]
    out = []
    for y, m, d in found:
        try:
            out.append(dt.date(y, m, d))
        except ValueError:
            continue
    return out


RECENT_DAYS = 90   # 마감일·날짜가 없는 '상시' 글은 이 기간 안에 올라온 것만 쓴다


def orang_id(r):
    return int(r["program_id"].split(":")[1]) if r["program_id"].startswith("orang:") else None


def orang_cutoff(rows, today):
    """서울청년센터 글번호는 올라온 순서대로 커진다. 날짜가 있는 글로 'RECENT_DAYS 전 무렵'의 글번호를 추정한다.
    (서울 글은 작성일이 없어서 글번호로 나이를 가늠한다)"""
    month = (today - dt.timedelta(days=RECENT_DAYS)).strftime("%Y-%m")
    ids = [orang_id(r) for r in rows if orang_id(r) and (r["aply_end"] or r["prog_end"])[:7] == month]
    return int(statistics.median(ids)) if len(ids) >= 20 else None


def old_undated(r, today, cutoff):
    """마감일 없는 글이 RECENT_DAYS 보다 오래됐으면 True."""
    if r["aply_end"]:
        return False
    oid = orang_id(r)
    if oid is not None:
        return cutoff is not None and oid < cutoff
    posted = r.get("posted_at", "")[:10]
    return bool(posted) and posted < (today - dt.timedelta(days=RECENT_DAYS)).isoformat()


# 오래됐어도 지금 운영 중일 가능성이 큰 상시 서비스 (상담 창구·공간·동아리 등)
EVERGREEN = re.compile(r"상담|이용|대관|사물함|공간|라운지|편의점|동아리|상시|바로\s*전문가|무료\s*초청")
EVENT = re.compile(r"\d+\s*(회차|차|기)(?![가-힣])|회차|특강|축제|행사|콘서트|공연|전시|페스타|워크숍|캠프|이벤트|개막|오늘\s*저녁|설명회")


def is_evergreen(r):
    t = r["title"]
    return bool(EVERGREEN.search(t)) and not EVENT.search(t)


def norm_title(r):
    """반복 게시글 비교용: 숫자·회차·기호·공백을 지운 제목."""
    t = re.sub(r"\d+\s*(회차|차|기)?|회차", "", r["title"])
    return re.sub(r"[^가-힣a-zA-Z]", "", t)


def newest_per_title(rows):
    """같은 제목(숫자·회차 제외)으로 여러 번 올라온 글은 가장 최근 글 하나만 남긴다."""
    best = {}
    for r in rows:
        key = (r["source"], norm_title(r))
        rank = orang_id(r) or 0, r.get("posted_at", ""), r["aply_end"]
        if key not in best or rank > best[key][0]:
            best[key] = (rank, r)
    keep = {id(v[1]) for v in best.values()}
    return [r for r in rows if id(r) in keep]


def content_hash(r):
    return hashlib.sha1((r["title"] + "|" + r["summary"]).encode("utf-8")).hexdigest()[:12]


def program_input(r):
    return {
        "id": r["program_id"],
        "title": " ".join(r["title"].split()),
        "category": r["category"],
        "center": r["center_names"][:60],
        "target": " ".join(r["target"].split())[:100],
        "summary": " ".join(r["summary"].split())[:300],
    }


def clean_result(res):
    acc = res.get("access_type")
    conf = res.get("confidence")
    return {
        "i5_domains": [d for d in res.get("i5_domains", []) if d in DOMAINS][:2],
        "access_type": acc if acc in ACCESS_TYPES else None,
        "topics": [t for t in res.get("topics", []) if t in TOPICS][:2],
        "situations": [s for s in res.get("situations", []) if s in SITUATIONS],
        "confidence": conf if conf in ("high", "low") else "low",
    }


def load_cache():
    cache = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                cache[e["program_id"]] = e
    return cache


def cache_ok(e, r):
    return e.get("hash") == content_hash(r) and e.get("prompt_version") == PROMPT_VERSION


def load_targets(today):
    """신청 가능 + 지난 글 아님. 지난 글은 LLM 비용도 아끼려고 분류 전에 뺀다."""
    with open(PROGRAMS, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    day = dt.date.fromisoformat(today)
    active = [r for r in rows
              if r["is_active"] == "Y" and r["kind"] == "program" and not (r["aply_end"] and r["aply_end"][:10] < today)]
    cutoff = orang_cutoff(rows, day)
    fresh = [r for r in active if not stale_reason(r, day)]
    recent = [r for r in fresh if not old_undated(r, day, cutoff)]
    old = [r for r in fresh if old_undated(r, day, cutoff)]
    evergreen = [r for r in old if is_evergreen(r)]
    for r in evergreen:
        r["_evergreen"] = True
    picked = newest_per_title(recent + evergreen)
    print(f"신청 가능 {len(active)}건 → 날짜가 지난 글(제목·본문) {len(active) - len(fresh)}건 제외, "
          f"마감일 없이 {RECENT_DAYS}일보다 오래된 글 {len(old)}건 중 상시 서비스 {len(evergreen)}건만 유지, "
          f"반복 게시 {len(recent) + len(evergreen) - len(picked)}건 정리 → {len(picked)}건 (서울 글번호 기준 {cutoff})")
    return picked


def write_outputs(rows, cache):
    counts = {"ok": 0, "hold": 0, "excluded": 0, "unclassified": 0}
    items = []
    with open(TAGS, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["program_id", "i5_domains", "access_type", "topics", "situations", "confidence", "status", "model"])
        for r in rows:
            e = cache.get(r["program_id"])
            if not (e and cache_ok(e, r)):
                counts["unclassified"] += 1
                continue
            st = status_of(e)
            counts[st] += 1
            w.writerow([r["program_id"], ",".join(e["i5_domains"]), e["access_type"] or "", ",".join(e["topics"]),
                        ",".join(e["situations"]), e["confidence"], st, e["model"]])
            if st != "ok":
                continue
            items.append({
                "program_id": r["program_id"],
                "title": " ".join(r["title"].split()),
                "center_names": r["center_names"],
                "region_cds": [c.strip() for c in r["region_cds"].split(";") if c.strip()],
                "sido_cd": r["sido_cd"],
                "category": r["category"],
                "status": r["status"],
                "aply_start": r["aply_start"][:10], "aply_end": r["aply_end"][:10], "aply_text": r["aply_text"],
                "prog_start": r["prog_start"][:10], "prog_end": r["prog_end"][:10], "prog_text": r["prog_text"],
                "place": r["place"], "target": r["target"], "summary": r["summary"],
                "url": r["url"], "apply_urls": r["apply_urls"], "image_url": r["image_url"],
                "source_name": r["source_name"],
                "evergreen": bool(r.get("_evergreen")),   # 오래된 상시 글: '이용 전 센터에 확인' 표시
                "i5_domains": e["i5_domains"], "access_type": e["access_type"],
                "topics": e["topics"], "situations": e["situations"],
            })
    data = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "청년센터 프로그램 (pipeline/programs/crawl) + pipeline/programs/classify.py 분류",
        "counts": counts,
        "programs": items,
    }
    paths.write_atomic(SERVING, json.dumps(data, ensure_ascii=False))
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    if not PROGRAMS.exists():
        sys.exit(f"{PROGRAMS} 가 없습니다. pipeline/programs/crawl/merge.py 를 먼저 실행하세요.")
    paths.cache_file(CACHE_NAME)   # 처음이면 seed 캐시 복사
    rows = load_targets(dt.date.today().isoformat())
    cache = load_cache()
    todo = [r for r in rows if not (r["program_id"] in cache and cache_ok(cache[r["program_id"]], r))]
    cached = len(rows) - len(todo)
    if args.limit:
        todo = todo[: args.limit]
    print(f"대상 {len(rows)}건 중 이미 분류 {cached}건, 이번에 분류 {len(todo)}건")

    if args.dry_run:
        print(SYSTEM, "\n---\n", json.dumps({"programs": [program_input(r) for r in todo[:BATCH]]},
                                            ensure_ascii=False, indent=1)[:3000])
        return
    if not todo or args.no_llm:
        print(f"LLM 호출 없음 → {TAGS}, {SERVING}\n상태: {write_outputs(rows, cache)}")
        return

    key, base, model = llm_config()
    tokens_in = tokens_out = failed = 0
    with open(CACHE, "a", encoding="utf-8") as cf:
        for i in range(0, len(todo), BATCH):
            batch = todo[i:i + BATCH]
            user = json.dumps({"programs": [program_input(r) for r in batch]}, ensure_ascii=False)
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
                res = results.get(r["program_id"])
                if res is None:
                    failed += 1
                    continue
                entry = {"program_id": r["program_id"], "hash": content_hash(r), "prompt_version": PROMPT_VERSION,
                         "model": model, **clean_result(res)}
                cache[r["program_id"]] = entry
                cf.write(json.dumps(entry, ensure_ascii=False) + "\n")
            cf.flush()
            print(f"  {min(i + BATCH, len(todo))}/{len(todo)}  (토큰 입력 {tokens_in:,} / 출력 {tokens_out:,})")

    counts = write_outputs(rows, cache)
    print(f"\n완료: 분류 {len(todo) - failed}건, 실패 {failed}건 → {TAGS}, {SERVING}")
    print(f"상태: {counts}  (ok만 서비스에 사용)")
    print(f"사용 토큰: 입력 {tokens_in:,} / 출력 {tokens_out:,}")


if __name__ == "__main__":
    main()
