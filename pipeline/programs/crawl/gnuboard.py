"""그누보드(GNUBOARD) 기반 센터 홈페이지 공통 크롤러.

  python pipeline/programs/crawl/gnuboard.py                    # 감지(캐시 사용) → 프로그램/공지 게시판 수집(증분)
  python pipeline/programs/crawl/gnuboard.py --redetect         # 센터 홈페이지를 다시 훑어 그누보드 사이트·게시판 재감지
  python pipeline/programs/crawl/gnuboard.py --pages 3 --max-new 50   # 게시판당 목록 3페이지, 새 글 상세는 50개까지
  python pipeline/programs/crawl/gnuboard.py --all-boards       # 분류와 상관없이(skip 제외) 모든 게시판 수집
  python pipeline/programs/crawl/gnuboard.py --site ch2030youth.kr    # 특정 사이트만 (부분 일치)

흐름
  1) detect : data/runtime/programs/centers.csv 의 활성 센터 홈페이지에서 그누보드 게시판 링크(bo_table)를 찾음
              → data/runtime/programs/gnuboard/sites.csv, boards.csv
     · 플랫폼 라벨을 믿지 않고 링크로 직접 판별 (custom 으로 분류된 그누보드 사이트도 잡힘)
     · 한 사이트를 여러 센터가 쓰면(천안 3곳) 사이트는 한 번만 수집하고 센터를 모두 연결
  2) crawl  : 게시판 목록에서 글 번호(wr_id)만 모으고, 처음 보는 글만 상세 페이지를 받아
              제목·작성일·본문·이미지를 추출 → data/runtime/programs/gnuboard/posts.csv
     · 스킨마다 목록 HTML이 달라 목록에서는 번호만 신뢰. 제목/날짜/본문은 상세에서
     · 목록 한 페이지가 전부 이미 본 글이면 그 게시판은 거기서 멈춤(증분)

예의: robots.txt 준수, 호스트당 요청 간격 1초, 식별 가능한 User-Agent.
"""
import argparse
import re
import urllib.parse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from bs4 import BeautifulSoup

from common import DATA, Fetcher, now, read_csv, write_csv

D = DATA / "gnuboard"
SITES, BOARDS, POSTS = D / "sites.csv", D / "boards.csv", D / "posts.csv"
DETECT_LOG = D / "detect_log.csv"
DETECT_COLS = ["cntrSn", "cntrNm", "homepage", "result", "site", "error"]
SITE_COLS = ["site", "root", "centers", "center_names", "region_cds", "homepage", "n_boards", "detected_at", "error"]
BOARD_COLS = ["site", "bo_table", "label", "kind", "list_url", "last_crawled", "n_posts", "error"]
POST_COLS = ["site", "bo_table", "board_label", "board_kind", "wr_id", "url", "title", "posted_at",
             "list_text", "content", "image_urls", "attachments", "note", "centers", "center_names", "region_cds",
             "first_seen", "last_seen"]

# 게시판 분류: label(메뉴 글자) 우선, 없으면 bo_table 이름으로
# 이용자가 직접 쓰는 게시판(상담·문의·자유)은 개인정보·스팸이 섞이므로 수집하지 않는다
SKIP_RE = re.compile(r"갤러리|포토|사진|자료|FAQ|Q\s*&\s*A|qna|문의|질문|상담|대관|예약|후기|자유|채용|입찰|회원|"
                     r"정보공개|파트너|협력|링크|영상|홍보물|뉴스레터|보도|언론|"
                     r"gallery|photo|pds|faq|inquiry|consul|review|free|rent|reserv|video|newsletter|press", re.I)
SECRET_RE = re.compile(r"비밀글 기능으로 보호된 글|비밀글입니다")
LOGIN_RE = re.compile(r"접근할 권한이 없습니다|읽기 권한이 없습니다|로그인 후 이용|회원만 (?:열람|이용)")
NOT_TITLE_RE = re.compile(r"^(?:모집|접수|신청|진행|교육)\s*(?:기간|일정)\s*[:：]")
LABELED_DATE_RE = re.compile(r"(?:작성일|등록일|게시일|작성일시|등록일시)\s*[:：]?\s*")
PROGRAM_RE = re.compile(r"프로그램|모집|신청|접수|교육|강좌|강의|클래스|행사|이벤트|참여|사업|활동|일정|"
                        r"역량강화|여가|창업지원|동아리|체험|공모|"
                        r"program|apply|edu|class|event|recruit|biz", re.I)
NOTICE_RE = re.compile(r"공지|알림|소식|뉴스|notice|news", re.I)
STATUS_WORDS = re.compile(r"^(모집\s*중|모집\s*마감|마감|접수\s*중|진행\s*중|종료|공지|new|더보기|자세히\s*보기|more)$", re.I)

DATE_RE = re.compile(r"(?<!\d)((?:20)?\d{2})[-./](\d{1,2})[-./](\d{1,2})(?:\.?\s+(\d{1,2}):(\d{2}))?(?!\d)")
NOISE_RE = re.compile(r"gnb|lnb|snb|menu|nav|footer|header|quick|banner|aside|side|cmt|comment|"
                      r"sns|share|btn|pagination|pg_wrap|location|breadcrumb|skip", re.I)
VIEW_TITLE_SEL = ["#bo_v_title .bo_v_tit", ".bo_v_tit", "#bo_v_title", ".view_title", ".bo_v_title",
                  ".board_view .title", ".view_head h3", ".subject"]
VIEW_DATE_SEL = [".if_date", "#bo_v_info", ".bo_v_info", ".view_info", ".board_view .info", ".date", ".datetime"]
VIEW_BODY_SEL = ["#bo_v_con", ".bo_v_con", "#bo_v_atc", ".view_content", "#view_content", ".board_view .content",
                 "#bo_v", "article#bo_v"]


# ---------------- 링크 해석 ----------------
def board_link(href, page_url):
    """href 가 그누보드 게시판/글 링크면 (root, bo_table, wr_id|None, 절대URL)."""
    if not href or href.startswith(("javascript", "mailto", "tel", "#")):
        return None
    absu = urllib.parse.urljoin(page_url, href.replace("&amp;", "&"))
    p = urllib.parse.urlsplit(absu)
    m = re.search(r"^(.*?/)bbs/board\.php$", p.path)
    if not m:
        return None
    q = urllib.parse.parse_qs(p.query)
    bt = (q.get("bo_table") or [""])[0]
    if not re.fullmatch(r"[\w-]{1,40}", bt):
        return None
    wr = (q.get("wr_id") or [None])[0]
    root = f"{p.scheme}://{p.netloc}{m.group(1)}"
    return root, bt, (wr if wr and wr.isdigit() else None), absu


def site_key(root):
    p = urllib.parse.urlsplit(root)
    host = p.netloc.lower().removeprefix("www.")
    return host + p.path.rstrip("/")


def classify(label, bo_table):
    if label and SKIP_RE.search(label):
        return "skip"
    if not label and SKIP_RE.search(bo_table):
        return "skip"
    if PROGRAM_RE.search(label or "") or PROGRAM_RE.search(bo_table):
        return "program"
    if NOTICE_RE.search(label or "") or NOTICE_RE.search(bo_table):
        return "notice"
    return "other"


def clean(s):
    return re.sub(r"\s+", " ", s or "").strip()


# ---------------- 1) 감지 ----------------
def detect_one(fetch, center):
    try:
        final, html = fetch.get(center["homepage"])
    except Exception as e:
        return center, None, {}, f"{type(e).__name__}: {e}"[:200]
    soup = BeautifulSoup(html, "html.parser")
    roots, boards = defaultdict(int), {}
    for a in soup.find_all("a", href=True):
        hit = board_link(a["href"], final)
        if not hit:
            continue
        root, bt, wr, _ = hit
        roots[root] += 1
        label = clean(a.get_text(" "))
        b = boards.setdefault((root, bt), {"labels": defaultdict(int)})
        if label and not wr and not STATUS_WORDS.match(label) and len(label) <= 30:
            b["labels"][label] += 1           # 메뉴 링크(글 번호 없는 링크)의 글자를 게시판 이름으로
    # 최종 URL 자체가 게시판인 경우(전남청년센터)
    hit = board_link(final, final)
    if hit:
        roots[hit[0]] += 1
        boards.setdefault((hit[0], hit[1]), {"labels": defaultdict(int)})
    # 홈페이지와 같은 호스트의 게시판만 인정 (사하구청 사이트가 외부 업체 게시판을 링크한 경우 등 제외)
    home_host = urllib.parse.urlsplit(final).netloc.lower().removeprefix("www.")
    roots = {r: n for r, n in roots.items()
             if urllib.parse.urlsplit(r).netloc.lower().removeprefix("www.") == home_host}
    if not roots:
        return center, None, {}, ""
    root = max(roots, key=roots.get)
    own = {bt: b for (r, bt), b in boards.items() if r == root}
    return center, root, own, ""


def board_name_from_list(fetch, list_url, center_names):
    """그누보드 목록 페이지 제목 예: '공지사항 1 페이지 | 사이트', '사이트 > 공지사항'."""
    try:
        _, html = fetch.get(list_url)
    except Exception:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for sel in ["#bo_list_title", ".bo_list_title", "#container_title", ".sub_title h2", ".sub_tit", "h2.tit"]:
        el = soup.select_one(sel)
        if el and 1 < len(clean(el.get_text(" "))) <= 20:
            return clean(el.get_text(" "))
    title = clean(soup.title.get_text()) if soup.title else ""
    title = re.sub(r"\s*\d+\s*페이지", "", title)
    parts = [p.strip() for p in re.split(r"\s*[>|:·-]\s*", title) if p.strip()]
    # 사이트(센터) 이름과 겹치는 조각은 빼고, 남은 것 중 가장 짧은 것(보통 게시판 이름)
    cand = [p for p in parts if not any(p in n or n in p for n in center_names.split(";"))] or parts
    return min(cand, key=len)[:20] if cand else ""


def detect(fetch, centers):
    print(f"[detect] 센터 홈페이지 {len(centers)}곳 확인 중...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda c: detect_one(fetch, c), centers))
    sites, boards, log = {}, {}, []
    for center, root, own, err in results:
        result = ("robots_blocked" if err.startswith("PermissionError") else "error") if err \
            else ("gnuboard" if root else "not_gnuboard")
        log.append({"cntrSn": center["cntrSn"], "cntrNm": center["cntrNm"], "homepage": center["homepage"],
                    "result": result, "site": site_key(root) if root else "", "error": err})
        if not root:
            continue
        key = site_key(root)
        s = sites.setdefault(key, {"site": key, "root": root, "centers": [], "center_names": [],
                                   "region_cds": [], "homepage": center["homepage"], "error": ""})
        s["centers"].append(center["cntrSn"])
        s["center_names"].append(center["cntrNm"])
        if center["region_cd"] not in s["region_cds"]:
            s["region_cds"].append(center["region_cd"])
        for bt, b in own.items():
            cur = boards.setdefault((key, bt), {"site": key, "bo_table": bt, "labels": defaultdict(int)})
            for lb, n in b["labels"].items():
                cur["labels"][lb] += n
    ts = now()
    board_rows = []
    for (key, bt), b in boards.items():
        label = max(b["labels"], key=lambda k: (b["labels"][k], -len(k))) if b["labels"] else ""
        board_rows.append({"site": key, "bo_table": bt, "label": label,
                           "list_url": f"{sites[key]['root']}bbs/board.php?bo_table={bt}"})
    # 홈페이지에 메뉴 링크가 없어 이름을 못 얻은 게시판 → 목록 페이지 <title>에서 이름 추출
    unnamed = [b for b in board_rows if not b["label"]]
    if unnamed:
        print(f"[detect] 이름 없는 게시판 {len(unnamed)}개 → 목록 페이지 제목 확인")
        site_names = {k: ";".join(s["center_names"]) for k, s in sites.items()}
        with ThreadPoolExecutor(max_workers=6) as ex:
            names = list(ex.map(lambda b: board_name_from_list(fetch, b["list_url"], site_names[b["site"]]), unnamed))
        for b, n in zip(unnamed, names):
            b["label"] = n
    for b in board_rows:
        b["kind"] = classify(b["label"], b["bo_table"])
    for s in sites.values():
        s["n_boards"] = sum(1 for b in board_rows if b["site"] == s["site"])
        s["detected_at"] = ts
        for k in ("centers", "center_names", "region_cds"):
            s[k] = ";".join(s[k])
    # 이전 crawl 상태(last_crawled 등)는 유지
    prev = {(b["site"], b["bo_table"]): b for b in read_csv(BOARDS)}
    for b in board_rows:
        p = prev.get((b["site"], b["bo_table"]))
        if p:
            b.update({k: p.get(k, "") for k in ("last_crawled", "n_posts", "error")})
    board_rows.sort(key=lambda b: (b["site"], {"program": 0, "notice": 1, "other": 2, "skip": 3}[b["kind"]], b["bo_table"]))
    write_csv(SITES, sorted(sites.values(), key=lambda s: s["site"]), SITE_COLS)
    write_csv(BOARDS, board_rows, BOARD_COLS)
    write_csv(DETECT_LOG, sorted(log, key=lambda r: (r["result"], r["cntrNm"])), DETECT_COLS)
    kinds, results_n = defaultdict(int), defaultdict(int)
    for b in board_rows:
        kinds[b["kind"]] += 1
    for r in log:
        results_n[r["result"]] += 1
    print(f"[detect] 그누보드 사이트 {len(sites)}곳 (센터 {sum(len(s['centers'].split(';')) for s in sites.values())}곳), "
          f"게시판 {len(board_rows)}개 {dict(kinds)}")
    print(f"[detect] 센터별 결과 {dict(results_n)} → {DETECT_LOG.name}")
    return list(sites.values()), board_rows


# ---------------- 2) 수집 ----------------
def norm_date(m, today=None):
    today = today or date.today()
    y, mo, d, hh, mm = m.groups()
    y = int(y) + (2000 if len(y) == 2 else 0)
    try:
        dt = date(y, int(mo), int(d))
    except ValueError:
        return ""
    # 작성일 전용: 수집일보다 뒤인 날짜는 진행일·모집일을 잘못 잡은 것이므로 버린다
    if not (2000 <= dt.year and dt <= today):
        return ""
    return dt.isoformat() + (f" {int(hh):02d}:{mm}" if hh else "")


def short_date(text, today=None):
    """목록의 '11-05' 같은 연도 없는 날짜 → 가장 가까운 과거 날짜."""
    today = today or date.today()
    m = re.search(r"(?<![\d-])(\d{1,2})-(\d{2})(?![\d-])", text or "")
    if not m:
        return ""
    mo, d = int(m.group(1)), int(m.group(2))
    try:
        dt = date(today.year, mo, d)
    except ValueError:
        return ""
    if dt > today:
        dt = dt.replace(year=today.year - 1)
    return dt.isoformat()


def strip_noise(node):
    for t in node.find_all(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button"]):
        t.decompose()
    for t in node.find_all(True):
        if t.decomposed:          # 부모와 함께 이미 지워진 태그
            continue
        attrs = " ".join([t.get("id") or ""] + (t.get("class") or []))
        if attrs and NOISE_RE.search(attrs) and not re.search(r"bo_v|view|content|article", attrs, re.I):
            t.decompose()


def text_score(node):
    txt = len(clean(node.get_text(" ")))
    links = sum(len(clean(a.get_text(" "))) for a in node.find_all("a"))
    return txt - links


def main_block(soup):
    """본문 영역 추정: 텍스트가 60% 이상 몰린 자식으로 계속 내려간다."""
    node = soup.body or soup
    while True:
        kids = [c for c in node.find_all(["div", "article", "section", "main", "td", "table", "tbody", "tr"],
                                         recursive=False)]
        if not kids:
            return node
        best = max(kids, key=text_score)
        if text_score(best) < 0.6 * max(text_score(node), 1):
            return node
        node = best


def extract_view(html, url, list_title):
    soup = BeautifulSoup(html, "html.parser")
    page_title = clean(soup.title.get_text()) if soup.title else ""

    title = ""
    for sel in VIEW_TITLE_SEL:
        el = soup.select_one(sel)
        if el and 2 <= len(clean(el.get_text(" "))) <= 200:
            title = clean(el.get_text(" "))
            break
    if not title and list_title and len(list_title) >= 6 and not STATUS_WORDS.match(list_title):
        title = list_title
    if not title and page_title:                     # "글제목 > 게시판 | 사이트" 형태
        parts = [p.strip() for p in re.split(r"\s+[>|]\s+", page_title) if p.strip()]
        title = max(parts, key=len) if parts else page_title

    page_text = clean(soup.get_text(" "))
    if SECRET_RE.search(page_text[:20000]):
        return None                      # 비밀글: 저장하지 않음
    if len(page_text) < 1500 and LOGIN_RE.search(page_text):
        return "login_required"          # 회원 전용 글: 목록 정보만 저장 (로그인 수집은 하지 않음)

    # 작성일: ① '작성일/등록일' 표시가 붙은 날짜 ② 날짜 전용 영역 ③ 제목 바로 뒤에 나오는 날짜
    #   (본문 아무 날짜나 잡으면 '모집기간' 같은 미래 날짜가 들어간다)
    posted = ""
    for lm in LABELED_DATE_RE.finditer(page_text):
        m = DATE_RE.match(page_text, lm.end())
        if m and norm_date(m):
            posted = norm_date(m)
            break
    for sel in ([] if posted else VIEW_DATE_SEL):
        el = soup.select_one(sel)
        m = el and DATE_RE.search(el.get_text(" "))
        if m and norm_date(m):
            posted = norm_date(m)
            break
    if not posted and title:
        i = page_text.rfind(title[:20])
        m = DATE_RE.search(page_text[i:i + len(title) + 300]) if i >= 0 else None
        if m and norm_date(m):
            posted = norm_date(m)

    body = None
    for sel in VIEW_BODY_SEL:
        el = soup.select_one(sel)
        if el and text_score(el) > 0 or (el and el.find("img")):
            body = el
            break
    if body is None:
        strip_noise(soup)
        body = main_block(soup)
    imgs, files = [], []
    for img in body.find_all("img", src=True):
        src = urllib.parse.urljoin(url, img["src"])
        if not re.search(r"icon|btn|blank|spacer|\.gif$", src, re.I) and src not in imgs:
            imgs.append(src)
    for a in soup.find_all("a", href=True):
        if "download.php" in a["href"]:
            name = clean(a.get_text(" "))
            if name and name not in files:
                files.append(name[:80])
    content = clean(body.get_text(" "))
    if title and content.startswith(title):
        content = content[len(title):].strip()
    return title, posted, content[:4000], imgs[:5], files[:5]


def list_page_posts(html, page_url, root, bt):
    """목록 페이지에서 {wr_id: (최적 제목 후보, 행 텍스트)}"""
    soup = BeautifulSoup(html, "html.parser")
    out = {}
    short_re = re.compile(rf"/{re.escape(bt)}/(\d+)/?$")      # 짧은 주소: /main_program/123
    root_host = urllib.parse.urlsplit(root).netloc
    for a in soup.find_all("a", href=True):
        hit = board_link(a["href"], page_url)
        wr = None
        if hit and hit[1] == bt and hit[2]:
            wr = hit[2]
        elif not hit:
            p = urllib.parse.urlsplit(urllib.parse.urljoin(page_url, a["href"]))
            m = short_re.search(p.path)
            if m and p.netloc == root_host:
                wr = m.group(1)
        if not wr:
            continue
        label = clean(a.get_text(" "))
        row = a.find_parent(["tr", "li"]) or a.parent
        row_text = clean(row.get_text(" "))[:300] if row else ""
        cur = out.get(wr, ("", ""))
        ok = not STATUS_WORDS.match(label) and not NOT_TITLE_RE.match(label)
        better = label if (ok and len(label) > len(cur[0])) else cur[0]
        out[wr] = (better, cur[1] if len(cur[1]) >= len(row_text) else row_text)
    return out


def crawl_board(fetch, site, board, known, pages, max_new):
    root, bt = site["root"], board["bo_table"]
    found, new_ids, err = {}, [], ""
    for page in range(1, pages + 1):
        url = f"{root}bbs/board.php?bo_table={bt}" + (f"&page={page}" if page > 1 else "")
        try:
            final, html = fetch.get(url)
        except Exception as e:
            err = f"list p{page}: {type(e).__name__}: {e}"[:200]
            break
        posts = list_page_posts(html, final, root, bt)
        if not posts:
            break
        fresh = [w for w in posts if (site["site"], bt, w) not in known and w not in found]
        found.update(posts)
        new_ids += fresh
        if not fresh:          # 이 페이지가 전부 이미 본 글 → 증분 수집 종료
            break
    rows = []
    for wr in sorted(set(new_ids), key=int, reverse=True)[:max_new]:
        list_title, row_text = found[wr]
        url = f"{root}bbs/board.php?bo_table={bt}&wr_id={wr}"
        try:
            final, html = fetch.get(url)
            got = extract_view(html, final, list_title)
            if got is None:          # 비밀글
                continue
            note = ""
            if got == "login_required":
                got, note = (list_title, "", "", [], []), "login_required"
            title, posted, content, imgs, files = got
        except Exception as e:
            title, posted, content, imgs, files = list_title, "", "", [], []
            note = "view_error"
            err = err or f"view {wr}: {type(e).__name__}: {e}"[:200]
        if not posted:   # 목록 행의 날짜로 보충. 단 '모집기간 : 날짜 ~ 날짜' 부분은 작성일이 아니므로 제거
            rt = re.sub(r"(?:모집|접수|신청|진행|교육|운영|행사)\s*(?:기간|일정|일시)\s*[:：]?\s*[\d.\-/~ ():월화수목금토일]+",
                        " ", row_text)
            m = DATE_RE.search(rt)
            posted = (norm_date(m) if m else "") or short_date(rt)
        rows.append({"site": site["site"], "bo_table": bt, "board_label": board["label"], "board_kind": board["kind"],
                     "wr_id": wr, "url": url, "title": title, "posted_at": posted, "list_text": row_text,
                     "content": content, "image_urls": " ".join(imgs), "attachments": " | ".join(files), "note": note,
                     "centers": site["centers"], "center_names": site["center_names"], "region_cds": site["region_cds"]})
    seen_again = [w for w in found if (site["site"], bt, w) in known]
    return rows, seen_again, err


def crawl(fetch, sites, boards, args):
    old = {(p["site"], p["bo_table"], p["wr_id"]): p for p in read_csv(POSTS)}
    known = set(old)
    kinds = {"program", "notice"} | ({"other"} if args.all_boards else set())
    by_site = {s["site"]: s for s in sites}
    targets = [b for b in boards if b["kind"] in kinds and b["site"] in by_site
               and (not args.site or args.site in b["site"])]
    print(f"[crawl] 게시판 {len(targets)}개 수집 (사이트 {len({b['site'] for b in targets})}곳, 기존 글 {len(old)}건)")

    def work(b):
        return b, crawl_board(fetch, by_site[b["site"]], b, known, args.pages, args.max_new)

    ts = now()
    with ThreadPoolExecutor(max_workers=6) as ex:   # 호스트별 간격은 Fetcher 가 보장
        results = list(ex.map(work, targets))

    n_new = 0
    for b, (rows, seen_again, err) in results:
        for r in rows:
            r["first_seen"] = r["last_seen"] = ts
            old[(r["site"], r["bo_table"], r["wr_id"])] = r
        for w in seen_again:
            old[(b["site"], b["bo_table"], w)]["last_seen"] = ts
        n_new += len(rows)
        b["last_crawled"], b["error"] = ts, err
        b["n_posts"] = sum(1 for k in old if k[0] == b["site"] and k[1] == b["bo_table"])
        flag = f"  ⚠ {err}" if err else ""
        print(f"  {b['site'][:32]:32} {b['bo_table'][:18]:18} {b['label'][:12]:12} 새 글 {len(rows):3}{flag}")

    write_csv(POSTS, sorted(old.values(), key=lambda p: (p["site"], p["bo_table"], -int(p["wr_id"]))), POST_COLS)
    write_csv(BOARDS, boards, BOARD_COLS)
    print(f"[crawl] 새 글 {n_new}건 / 전체 {len(old)}건 → {POSTS}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--redetect", action="store_true")
    ap.add_argument("--pages", type=int, default=2, help="게시판당 목록 최대 페이지 (기본 2)")
    ap.add_argument("--max-new", type=int, default=30, help="게시판당 상세를 받을 새 글 최대 수 (기본 30)")
    ap.add_argument("--all-boards", action="store_true")
    ap.add_argument("--site", default="")
    ap.add_argument("--detect-only", action="store_true")
    args = ap.parse_args()

    fetch = Fetcher(delay=1.0)
    if args.redetect or not SITES.exists():
        centers = [c for c in read_csv(DATA / "centers.csv") if c["status"] == "active" and c["homepage"]]
        if not centers:
            raise SystemExit("data/runtime/programs/centers.csv 가 없습니다. 먼저 python pipeline/programs/crawl/sync_centers.py")
        sites, boards = detect(fetch, centers)
    else:
        sites, boards = read_csv(SITES), read_csv(BOARDS)
        print(f"[detect] 캐시 사용: 사이트 {len(sites)}곳, 게시판 {len(boards)}개 (다시 하려면 --redetect)")
    if not args.detect_only:
        crawl(fetch, sites, boards, args)


if __name__ == "__main__":
    main()
