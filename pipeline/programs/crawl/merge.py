"""수집 결과를 하나의 '센터 프로그램' 표로 합친다 → data/runtime/programs/programs.csv

  python pipeline/programs/crawl/merge.py

입력
  data/runtime/programs/seoul_orang/programs.csv   서울청년센터 (이미 구조화: 상태·분야·신청기간·진행일정·장소)
  data/runtime/programs/gnuboard/posts.csv         그누보드 게시판 글 (기간·상태는 글에서 추출)

공통 칸 (COLS 참고)
  - region_cds 로 사용자 지역과 매칭 (5자리 시군구, 여러 개면 ';'. 서울 공통은 '11')
  - is_active: Y(지금 신청 가능/상시) / N(마감) / unknown(기간 정보를 못 찾음)
  - 그누보드 '공지' 게시판 글은 프로그램이 아닌 것(휴관 안내 등)도 섞여 있어 kind=notice 로 구분
"""
import json
import re
from datetime import date

import requests

from common import DATA, UA, now, read_csv, write_csv
from pipeline import paths

OUT = DATA / "programs.csv"
COLS = ["program_id", "source", "kind", "center_sns", "center_names", "region_cds", "sido_cd",
        "title", "category", "status", "is_active",
        "aply_start", "aply_end", "aply_text", "prog_start", "prog_end", "prog_text",
        "place", "target", "posted_at", "summary", "url", "apply_urls", "image_url",
        "source_name", "first_seen", "last_seen", "merged_at"]

TODAY = date.today().isoformat()
FORM_RE = re.compile(r"https?://(?:forms\.gle|docs\.google\.com/forms|form\.naver\.com|"
                     r"[\w.-]*typeform\.com|tally\.so)[^\s<>\"']*")

# ---------- 단축 링크 풀기 ----------
# 본문의 신청 링크가 bit.ly·naver.me 같은 단축 링크면 실제 주소(구글폼·네이버폼·예약 페이지 등)를 알 수 없다.
# 2026-11-21 점검: bit.ly 4개가 실제로는 구글폼이었다. merge 때 한 번 열어 최종 주소로 바꾸고, 결과는 캐시에 둔다
# (같은 링크를 매일 다시 열지 않음). 열지 못하면 단축 링크를 그대로 두고 신청폼 후보로 본다(이전 동작).
SHORT_RE = re.compile(r"https?://(?:www\.)?(?:bit\.ly|naver\.me|tinyurl\.com|zrr\.kr|iii\.im|m\.site\.naver\.com|"
                      r"han\.gl|me2\.do|url\.kr|buly\.kr|vo\.la|t\.ly|lrl\.kr|abit\.ly|goo\.gl)/", re.I)
# 서버 이동(301/302)이 아니라 페이지 안의 스크립트·meta 로 이동하는 단축 서비스용 (zrr.kr, iii.im 등)
JS_REDIRECT_RE = re.compile(r"""(?:location(?:\.href)?\s*=\s*|location\.replace\(\s*|"""
                            r"""http-equiv=["']?refresh["']?[^>]*?url=)["']?(https?://[^"'\s<>)]+)""", re.I)
SHORT_CACHE = "short_links.json"


def fetch_final_url(url, timeout=10):
    """단축 링크를 열어 최종 주소. 실패하거나 끝까지 단축 링크면 None."""
    try:
        res = requests.get(url, headers={"User-Agent": UA}, timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        return None
    final = res.url
    if SHORT_RE.match(final):
        m = JS_REDIRECT_RE.search(res.text[:50000])
        final = m.group(1) if m else None
    return final if final and not SHORT_RE.match(final) else None


class ShortLinks:
    """단축 링크 → 최종 주소. 성공한 것만 캐시한다(실패는 다음 실행에서 다시 시도)."""

    def __init__(self, path=None, fetch=fetch_final_url, enabled=True):
        self.path, self.fetch, self.enabled = path, fetch, enabled
        self.cache = {}
        if path and path.exists():
            self.cache = json.loads(path.read_text(encoding="utf-8"))
        self.resolved = self.failed = 0

    def resolve(self, url):
        if not SHORT_RE.match(url):
            return url
        if url in self.cache:
            return self.cache[url]
        final = self.fetch(url) if self.enabled else None
        if final:
            self.cache[url] = final
            self.resolved += 1
            return final
        self.failed += 1
        return url

    def save(self):
        if self.path and self.resolved:
            paths.write_atomic(self.path, json.dumps(self.cache, ensure_ascii=False, indent=1, sort_keys=True))


def is_form(url):
    """신청폼 링크. 풀지 못한 단축 링크도 후보로 둔다."""
    return bool(FORM_RE.match(url) or SHORT_RE.match(url))


NO_RESOLVE = ShortLinks(enabled=False)

# ---------- 그누보드 글에서 신청기간·상태 추출 ----------
PERIOD_LABEL_RE = re.compile(r"(?:모집|접수|신청|참여\s*신청)\s*(?:기간|일정|일시)?\s*[:：]?\s*")
PROG_LABEL_RE = re.compile(r"(?:진행|교육|운영|행사|활동)\s*(?:기간|일정|일시)\s*[:：]?\s*")
# 목록 링크 글자가 제목으로 들어온 경우의 군더더기 (안산 상상대로: '모집중 외부기관 제목 신청기간 : … 진행기간 : …')
TITLE_PREFIX_RE = re.compile(r"^(?:모집\s*중|모집\s*마감|마감|모집\s*예정|접수\s*중|접수\s*마감)\s+(?:외부기관|프로그램|공간이용)?\s*")
TITLE_SUFFIX_RE = re.compile(r"\s+(?:신청|모집|접수|진행)\s*기간\s*[:：]?\s*\d.*$")
DATE_TOKEN_RE = re.compile(r"(?:(20\d{2})\s*[.\-/년]\s*)?(\d{1,2})\s*[.\-/월]\s*(\d{1,2})(?!\d)\s*\.?\s*(?:일)?")
STATUS_RULES = [("모집예정", re.compile(r"모집\s*예정|접수\s*예정|오픈\s*예정")),
                ("모집중", re.compile(r"모집\s*중|접수\s*중|신청\s*중|진행\s*중")),
                ("마감", re.compile(r"모집\s*마감|접수\s*마감|신청\s*마감|마감|종료"))]


def mkdate(y, m, d):
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except (ValueError, TypeError):
        return ""


def clean_title(t):
    t = TITLE_PREFIX_RE.sub("", t.strip())
    return TITLE_SUFFIX_RE.sub("", t).strip()


def extract_period(text, base_year, label_re=PERIOD_LABEL_RE, allow_end_only=True):
    """'신청기간 : 2026. 9. 1.(화) ~ 9. 11.(금)' → ('2026-09-01', '2026-09-11', 원문)"""
    for lm in label_re.finditer(text):
        seg = text[lm.end():lm.end() + 70]
        if "~" not in seg:
            continue
        left, right = seg.split("~", 1)
        a = DATE_TOKEN_RE.search(left)
        b = DATE_TOKEN_RE.search(right)
        if not a or not b or a.start() > 3:         # 라벨 바로 뒤에 날짜가 와야 한다
            continue
        y1 = a.group(1) or base_year
        start = mkdate(y1, a.group(2), a.group(3))
        y2 = b.group(1) or y1
        end = mkdate(y2, b.group(2), b.group(3))
        if start and end and end < start and not b.group(1):
            end = mkdate(int(y2) + 1, b.group(2), b.group(3))   # 12.20 ~ 1.10 처럼 해를 넘김
        if start and end:
            return start, end, (text[lm.start():lm.end()] + left + "~" + right[:b.end()]).strip()
    # 제목의 '(~11.18.)' 처럼 마감일만 있는 경우
    m = allow_end_only and re.search(r"\(\s*~\s*(\d{1,2})\s*[./]\s*(\d{1,2})", text)
    if m:
        end = mkdate(base_year, m.group(1), m.group(2))
        if end:
            return "", end, m.group(0) + ")"
    return "", "", ""


def gnu_status(list_text, title):
    head = f"{list_text} {title}"[:200]
    for name, rx in STATUS_RULES:
        if rx.search(head):
            return name
    return ""


def active_flag(status, aply_start, aply_end, prog_end):
    if status == "마감":
        return "N"
    if aply_end:
        return "Y" if aply_end >= TODAY else "N"
    if status in ("모집중", "상시", "모집예정"):
        return "Y" if not prog_end or prog_end >= TODAY else "N"
    return "unknown"


def summarize(text, n=300):
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:n] + ("…" if len(text) > n else "")


# ---------- 원본별 변환 ----------
def from_orang(r, links=NO_RESOLVE):
    urls = list(dict.fromkeys(links.resolve(u) for u in (r.get("content_urls") or "").split() if u))
    forms = [u for u in urls if is_form(u)]
    status = r["status"] or ("상시" if r["aply_text"] == "상시" else "")
    return {
        "program_id": f"orang:{r['sprtInfoId']}", "source": "seoul_orang", "kind": "program",
        "center_sns": r["centers"], "center_names": r["branch_name"], "region_cds": r["region_cds"],
        "sido_cd": r["region_cds"][:2],
        "title": r["title"], "category": r["category"], "status": status,
        "is_active": active_flag(status if r["status"] else ("상시" if r["aply_text"] == "상시" else ""),
                                 r["aply_start"], r["aply_end"], r["prog_end"]),
        "aply_start": r["aply_start"], "aply_end": r["aply_end"], "aply_text": r["aply_text"],
        "prog_start": r["prog_start"], "prog_end": r["prog_end"], "prog_text": r["prog_text"],
        "place": r["place"], "target": r.get("target", ""), "posted_at": "",
        "summary": summarize(r.get("content")), "url": r["list_url"],
        "apply_urls": " ".join(forms or urls[:2]), "image_url": r["image_url"],
        "source_name": "서울청년센터(youth.seoul.go.kr)", "first_seen": r["first_seen"], "last_seen": r["last_seen"],
    }


def from_gnuboard(p, links=NO_RESOLVE):
    base_year = (p["posted_at"] or p["first_seen"])[:4]
    blob = f"{p['list_text']} || {p['title']} || {p['content'][:2500]}"
    a0, a1, atext = extract_period(blob, base_year)
    p0, p1, ptext = extract_period(blob, base_year, PROG_LABEL_RE, allow_end_only=False)
    status = gnu_status(p["list_text"], p["title"])
    urls = list(dict.fromkeys(links.resolve(u) for u in re.findall(r"https?://[^\s<>\"'()]+", p["content"])))
    forms = [u for u in urls if is_form(u)]
    regions = p["region_cds"].split(";")
    return {
        "program_id": f"gnu:{p['site']}:{p['bo_table']}:{p['wr_id']}", "source": "gnuboard",
        "kind": "program" if p["board_kind"] == "program" else "notice",
        "center_sns": p["centers"], "center_names": p["center_names"], "region_cds": p["region_cds"],
        "sido_cd": ";".join(sorted({r[:2] for r in regions if r})),
        "title": clean_title(p["title"]), "category": p["board_label"], "status": status,
        "is_active": active_flag(status, a0, a1, p1),
        "aply_start": a0, "aply_end": a1, "aply_text": atext,
        "prog_start": p0, "prog_end": p1, "prog_text": ptext,
        "place": "", "target": "", "posted_at": p["posted_at"],
        "summary": summarize(p["content"]) or ("(회원 전용 글 — 본문 없음)" if p["note"] == "login_required" else ""),
        "url": p["url"], "apply_urls": " ".join(forms[:3]),
        "image_url": (p["image_urls"].split() or [""])[0],
        "source_name": f"{p['center_names'].split(';')[0]} 홈페이지 ({p['board_label']})",
        "first_seen": p["first_seen"], "last_seen": p["last_seen"],
    }


def dedupe_gnuboard(rows):
    """같은 사이트에서 같은 제목이 여러 게시판(공지·프로그램)에 올라온 경우 하나만 남긴다(프로그램 게시판 우선)."""
    best = {}
    for r in rows:
        site = r["program_id"].split(":")[1]
        key = (site, re.sub(r"\W+", "", r["title"]))
        cur = best.get(key)
        if cur is None or (cur["kind"] != "program" and r["kind"] == "program"):
            best[key] = r
    return list(best.values())


def main():
    links = ShortLinks(paths.cache_file(SHORT_CACHE))
    orang = [from_orang(r, links) for r in read_csv(DATA / "seoul_orang" / "programs.csv")]
    gnu_all = [from_gnuboard(p, links) for p in read_csv(DATA / "gnuboard" / "posts.csv")]
    links.save()
    gnu = dedupe_gnuboard(gnu_all)
    ts = now()
    rows = orang + gnu
    for r in rows:
        r["merged_at"] = ts
    rows.sort(key=lambda r: ({"Y": 0, "unknown": 1, "N": 2}[r["is_active"]], r["sido_cd"], r["region_cds"],
                             -(int(re.sub(r"\D", "", r["aply_start"] or "0") or 0))))
    write_csv(OUT, rows, COLS)

    def stat(rs):
        c = {"Y": 0, "N": 0, "unknown": 0}
        for r in rs:
            c[r["is_active"]] += 1
        return c
    print(f"서울청년센터 {len(orang)}건 {stat(orang)}")
    print(f"그누보드     {len(gnu)}건 (중복 제거 {len(gnu_all) - len(gnu)}건) {stat(gnu)}, "
          f"신청기간 추출 {sum(1 for r in gnu if r['aply_end'])}건")
    print(f"단축 링크   새로 풀림 {links.resolved}건, 못 풂 {links.failed}건 (캐시 {len(links.cache)}건)")
    print(f"→ {OUT}  전체 {len(rows)}건, 지금 신청 가능(is_active=Y) {sum(1 for r in rows if r['is_active'] == 'Y')}건")


if __name__ == "__main__":
    main()
