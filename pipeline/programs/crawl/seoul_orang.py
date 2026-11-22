"""서울청년센터(오랑) 통합 프로그램 페이지 수집기 — youth.seoul.go.kr

  python pipeline/programs/crawl/seoul_orang.py                 # 증분: 지점별 최신 목록 → 새 글 + 아직 유효한 글의 상세
  python pipeline/programs/crawl/seoul_orang.py --full          # 목록 전체 페이지 (첫 실행 권장, 상세는 유효한 글만)
  python pipeline/programs/crawl/seoul_orang.py --branch joonggu --max-detail 20
  python pipeline/programs/crawl/seoul_orang.py --detail-days 30   # 신청 마감 후 30일 지난 글까지 상세 수집

동작 (조사 내용: README.md "서울청년센터 통합 프로그램 페이지 조사")
  목록  GET  list.do?key=2309210005&sc_cntrSe={지점}&recordCountPerPage=48&pageIndex={n}
        → 등록일 최신순. 목록에 이미 상태·분야·제목·신청기간·진행일정·장소가 있음
        → 증분: 한 페이지가 전부 이미 본 글이면 그 지점은 멈춤
  상세  POST view.do?key=2309210005  sprtInfoId={id}   (GET 은 오류 페이지)
        → 대상·담당기관·주소·본문·신청 링크
        → 상세는 '아직 신청 가능하거나 곧 열리는' 글만 받는다(지난 글 수천 건은 목록 정보로 충분)

결과: data/runtime/programs/seoul_orang/programs.csv  (지점 → 센터 API cntrSn·지역코드 연결)
이용 시 주의: 페이지에 공공누리 표시가 없음 → 서비스에는 사실 정보 + 요약 + 원문 출처 표시. README 참고.
"""
import argparse
import re
import urllib.parse
from datetime import date, timedelta

from bs4 import BeautifulSoup

from common import DATA, Fetcher, now, read_csv, write_csv

BASE = "https://youth.seoul.go.kr/orang/infoData/sprtInfo/"
KEY = "2309210005"
PER_PAGE = 48
D = DATA / "seoul_orang"
OUT = D / "programs.csv"
COLS = ["sprtInfoId", "branch", "branch_name", "centers", "region_cds", "status", "category", "title",
        "aply_text", "aply_start", "aply_end", "prog_text", "prog_start", "prog_end", "place",
        "target", "org", "address", "org_link", "content", "content_urls", "image_url",
        "source", "list_url", "detail_fetched_at", "first_seen", "last_seen"]

# 사이트의 지점 코드(sc_cntrSe) → 자치구. 철자는 사이트 원문 그대로(secho = 서초)
BRANCHES = {
    "joonggu": "중구", "seongdong": "성동구", "gwangjin": "광진구", "dongdaemun": "동대문구",
    "seongbuk": "성북구", "gangbuk": "강북구", "dobong": "도봉구", "nowon": "노원구",
    "eunpyeong": "은평구", "mapo": "마포구", "yangcheon": "양천구", "gangseo": "강서구",
    "geumcheon": "금천구", "yeongdeungpo": "영등포구", "gwanak": "관악구", "secho": "서초구",
    "gangdong": "강동구", "common": None,   # common = 서울시 전체 대상
}
# 사이트의 분야 필터(ctgry) 값. 제목 앞 [..] 이 이 목록에 없으면 분야가 아니다(예: [서울청년센터 강북])
CATEGORIES = {"일자리", "진로", "창업", "주거", "금융", "교육", "마음건강", "신체건강", "생활지원",
              "문화/예술", "대외활동", "공간", "사회참여", "커뮤니티"}
DATE_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})")
URL_RE = re.compile(r"https?://[^\s<>\"'()]+")


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


def branch_links():
    """지점 코드 → (센터 API cntrSn, 지역코드). centers.csv 에서 자치구 + '서울청년센터' 이름으로 찾는다."""
    centers = [c for c in read_csv(DATA / "centers.csv") if c["stdgCtpvCd"] == "11" and c["status"] == "active"]
    out = {}
    for code, gu in BRANCHES.items():
        if gu is None:
            out[code] = ("", "11", "공통(서울 전체)")
            continue
        same_gu = [c for c in centers if c["stdgSggCdNm"] == gu]
        orang = [c for c in same_gu if "서울청년센터" in c["cntrNm"]]
        sn = orang[0]["cntrSn"] if orang else ""
        region = same_gu[0]["region_cd"] if same_gu else ""
        out[code] = (sn, region, f"서울청년센터 {gu.removesuffix('구') if gu != '중구' else gu}")
    return out


def split_range(text):
    m = DATE_RANGE_RE.search(text or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def list_url(branch, page):
    q = {"key": KEY, "sc_cntrSe": branch, "recordCountPerPage": PER_PAGE, "pageIndex": page}
    return BASE + "list.do?" + urllib.parse.urlencode(q)


def parse_list(html):
    """목록 → [{sprtInfoId, status, category, title, aply_text, prog_text, place, image_url}]"""
    soup = BeautifulSoup(html, "html.parser")
    total = re.search(r"총 게시물\s*([\d,]+)\s*건", soup.get_text(" "))
    items = []
    for a in soup.find_all("a", onclick=re.compile(r"goView\('\d+'\)")):
        sid = re.search(r"goView\('(\d+)'\)", a["onclick"]).group(1)
        title_el = a.select_one(".ti")
        raw_title = clean(title_el.get_text(" ")) if title_el else ""
        m = re.match(r"\[([^\]]+)\]\s*(.*)", raw_title)
        if m and m.group(1).strip() not in CATEGORIES:
            m = None
        info = {clean(li.em.get_text()): clean(li.span.get_text()) for li in a.select(".list-info li") if li.em and li.span}
        img = a.select_one(".img img")
        items.append({
            "sprtInfoId": sid,
            "status": clean(a.select_one(".cate1").get_text()) if a.select_one(".cate1") else "",
            "category": m.group(1) if m else "",
            "title": m.group(2) if m else raw_title,
            "aply_text": info.get("신청기간", ""),
            "prog_text": info.get("진행일정", ""),
            "place": info.get("장소", ""),
            "image_url": urllib.parse.urljoin(BASE, img["src"]) if img and img.get("src") else "",
        })
    return items, int(total.group(1).replace(",", "")) if total else None


def parse_view(html):
    soup = BeautifulSoup(html, "html.parser")
    ov = soup.select_one(".board-overview")
    if not ov:
        return None
    info = {}
    for li in ov.select("ul.info li"):
        k = li.find("strong")
        if k:
            key = clean(k.get_text())
            k.extract()
            info[key] = clean(li.get_text(" "))
    cats = [clean(s.get_text()) for s in ov.select(".cate-box .cate1")]   # [상태, 분야]
    btn = ov.select_one("a.btn[href]")
    org_link = btn["href"] if btn and btn["href"].startswith("http") else ""   # "담당기관 바로가기": 프로그램 신청폼일 수도, 기관 공통 링크일 수도 있음
    ed = soup.select_one(".board-content .editor")
    content, urls = "", []
    if ed:
        for a in ed.find_all("a", href=True):
            if a["href"].startswith("http") and a["href"] not in urls:
                urls.append(a["href"])
        content = clean(ed.get_text(" "))
        for u in URL_RE.findall(content):
            if u not in urls:
                urls.append(u)
    return {"target": info.get("대상", ""), "org": info.get("담당기관", ""), "address": info.get("찾아가기", ""),
            "org_link": org_link, "category": next((c for c in cats if c in CATEGORIES), ""), "content": content, "content_urls": " ".join(urls[:5])}


def is_relevant(row, today, days):
    """상세를 받을 가치가 있는 글.
    - 상태 '마감' → 아님
    - 신청기간이 날짜면 → 마감일이 (오늘 - days) 이후
    - 신청기간 '상시' → 진행일정이 날짜면 그 종료일 기준, 진행도 상시면 유효로 본다
      ('상시' 글 752건 중 162건은 이미 '마감', 상태 표시 없는 223건은 수년 전 글도 섞여 있음)"""
    if row.get("status") == "마감":
        return False
    cutoff = (today - timedelta(days=days)).isoformat()
    if row.get("aply_end"):
        return row["aply_end"] >= cutoff
    return not row.get("prog_end") or row["prog_end"] >= cutoff


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="목록 전체 페이지 수집")
    ap.add_argument("--branch", default="", help="지점 코드 하나만 (예: joonggu)")
    ap.add_argument("--detail-days", type=int, default=0, help="신청 마감 후 며칠 지난 글까지 상세 수집 (기본 0)")
    ap.add_argument("--max-detail", type=int, default=400, help="이번 실행에서 받을 상세 최대 수 (기본 400)")
    args = ap.parse_args()

    links = branch_links()
    fetch = Fetcher(delay=1.0)
    old = {r["sprtInfoId"]: r for r in read_csv(OUT)}
    ts, today = now(), date.today()
    branches = [args.branch] if args.branch else list(BRANCHES)

    # 1) 목록
    n_new = 0
    for br in branches:
        sn, region, bname = links[br]
        page, seen_new = 1, 0
        while True:
            url = list_url(br, page)
            try:
                _, html = fetch.get(url)
            except Exception as e:
                print(f"  ⚠ {br} p{page}: {type(e).__name__}: {e}")
                break
            items, total = parse_list(html)
            if not items:
                break
            fresh = 0
            for it in items:
                prev = old.get(it["sprtInfoId"])
                a0, a1 = split_range(it["aply_text"])
                p0, p1 = split_range(it["prog_text"])
                row = {**(prev or {}), **it, "branch": br, "branch_name": bname, "centers": sn, "region_cds": region,
                       "aply_start": a0, "aply_end": a1, "prog_start": p0, "prog_end": p1,
                       "source": "서울청년센터(youth.seoul.go.kr)", "list_url": url, "last_seen": ts}
                if not prev:
                    row["first_seen"] = ts
                    fresh += 1
                old[it["sprtInfoId"]] = row
            seen_new += fresh
            if page == 1:
                print(f"  {br:13} {bname:14} 전체 {total}건", end="")
            if (not args.full and fresh == 0) or len(items) < PER_PAGE:
                break
            page += 1
        n_new += seen_new
        print(f" → 목록 {page}페이지, 새 글 {seen_new}")

    # 2) 상세: 아직 상세가 없고 유효한 글 (최신 등록 순)
    todo = [r for r in old.values() if not r.get("detail_fetched_at") and is_relevant(r, today, args.detail_days)
            and (not args.branch or r["branch"] == args.branch)]
    todo.sort(key=lambda r: -int(r["sprtInfoId"]))
    todo = todo[:args.max_detail]
    print(f"[detail] 상세 수집 {len(todo)}건 (신청 마감 {args.detail_days}일 이내·상시 글)")
    fails = 0
    for i, r in enumerate(todo, 1):
        try:
            _, html = fetch.post(BASE + f"view.do?key={KEY}", {"key": KEY, "sprtInfoId": r["sprtInfoId"]})
            got = parse_view(html)
        except Exception as e:
            got, fails = None, fails + 1
            print(f"  ⚠ view {r['sprtInfoId']}: {type(e).__name__}: {e}")
        if got:
            if r.get("category"):          # 목록에서 얻은 분야가 있으면 그대로 둔다
                got.pop("category")
            r.update(got)
            r["detail_fetched_at"] = ts
        if i % 50 == 0:
            print(f"  ... {i}/{len(todo)}")
            write_csv(OUT, sorted(old.values(), key=lambda r: -int(r["sprtInfoId"])), COLS)   # 중간 저장

    write_csv(OUT, sorted(old.values(), key=lambda r: -int(r["sprtInfoId"])), COLS)
    with_detail = sum(1 for r in old.values() if r.get("detail_fetched_at"))
    print(f"[done] 새 글 {n_new}건 / 전체 {len(old)}건 (상세 있음 {with_detail}, 실패 {fails}) → {OUT}")


if __name__ == "__main__":
    main()
