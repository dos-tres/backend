"""청년공간/센터 API(getSpace) 실제 형식 + 각 홈페이지 크롤링 방식 진단.

  python tools/data_check/inspect_centers.py            # 전체
  python tools/data_check/inspect_centers.py --no-web   # 홈페이지 접속 진단 생략(API 형식만)

출력(data/runtime/data_check/center/):
  sample_response.json   첫 페이지 원본 응답
  raw.jsonl / fields.csv
  homepage_probe.csv     센터별 홈페이지: 최종URL, 상태, 플랫폼 추정, 렌더링 방식, 프로그램 게시판 후보 링크
  platform_summary.csv   플랫폼별 센터 수 → 크롤러 전략 결정용
"""
import csv
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from common import OUT, UA, dump_jsonl, fetch_all, field_profile, require_key

D = OUT / "center"
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.I)
BARE_DOMAIN_RE = re.compile(r"(?:[\w가-힣-]+\.)+[a-z가-힣]{2,}(?:[/?#][^\s\"'<>]*)?", re.I)
PROGRAM_WORDS = ("프로그램", "모집", "공지", "신청", "교육", "행사", "강좌", "이벤트", "참여", "program", "notice", "bbs", "board")

# 1단계: 최종 URL(도메인)로만 판단하는 외부 플랫폼.
#   HTML 본문으로 판단하면 푸터의 SNS 링크 때문에 자체 홈페이지가 instagram 등으로 오분류됨
#   (이전 실행: instagram 133곳 중 107곳이 실제로는 자체 홈페이지였음)
URL_PLATFORMS = [
    ("instagram", r"instagram\.com"),
    ("facebook", r"facebook\.com"),
    ("naver_blog", r"blog\.naver\.com|m\.blog\.naver"),
    ("naver_cafe", r"cafe\.naver\.com"),
    ("naver_modoo/booking", r"modoo\.at|booking\.naver"),
    ("kakao_channel", r"pf\.kakao\.com|kakao\.com/_"),
    ("linktree", r"linktr\.ee|litt\.ly|inpock"),
    ("youthcenter_portal", r"youthcenter\.go\.kr"),
]
# 본문에 링크로만 걸린 SNS — 자체 홈페이지 외 보조 수집 경로로 기록
SNS_LINKS = [
    ("instagram", r"instagram\.com/(?!p/|reel/|explore/)([\w.]+)"),
    ("naver_blog", r"blog\.naver\.com/([\w-]+)"),
    ("naver_cafe", r"cafe\.naver\.com/([\w-]+)"),
    ("kakao_channel", r"pf\.kakao\.com/([\w-]+)"),
    ("youtube", r"youtube\.com/(@[\w.-]+|channel/[\w-]+|c/[\w-]+)"),
]
# 2단계: 자체 홈페이지일 때 HTML 지문으로 사이트 빌더/CMS 판별 — 위에서부터 먼저 걸리는 것 채택
PLATFORMS = [
    ("imweb", r"imweb|cdn\.imweb\.me"),
    ("wix", r"wix\.com|wixstatic"),
    ("cafe24", r"cafe24"),
    ("wordpress", r"wp-content|wp-json"),
    ("gnuboard", r"gnuboard|/bbs/board\.php|g5_"),
    ("xe_rhymix", r"xpressengine|rhymix|/index\.php\?mid=|xe\.min\.js"),
]
# 지자체/공공 사이트: 본문의 '.do' 링크 하나로는 판단하지 않고(외부 링크가 흔함) 최종 URL 기준 + egov 흔적
GOV_URL_RE = re.compile(r"^https?://[^/]+\.go\.kr(?=[/:]|$)|\.do(\?|$)", re.I)
GOV_HTML_RE = re.compile(r"egovframework|/egov[A-Z]", re.I)


def guess_url(it):
    """URL 필드명을 모르므로 이름에 url/hmpg/site 들어간 필드 → 그 외 아무 필드 순으로 첫 URL."""
    prio = [k for k in it if re.search(r"url|hmpg|homepage|site|link", k, re.I)]
    for k in prio:   # URL 필드: scheme 없이 'www.hampyeong.go.kr'처럼 온 값도 살린다
        m = BARE_DOMAIN_RE.match(str(it.get(k) or "").strip(" /"))
        if m and not URL_RE.search(str(it.get(k))):
            return k, "http://" + m.group(0).rstrip(".,)")
    for k in prio + [k for k in it if k not in prio]:
        m = URL_RE.search(str(it.get(k) or ""))
        if m:
            return k, m.group(0).rstrip(".,)")
    return None, None


def name_of(it):
    for k in it:
        if re.search(r"(cntr|spc|space).*nm|^nm$|name", k, re.I):
            return str(it[k])
    return ""


def to_ascii_url(url):
    """한글 도메인은 punycode, 한글 경로/쿼리는 퍼센트 인코딩 (이미 인코딩된 %XX는 유지)."""
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    netloc = host + (f":{p.port}" if p.port else "")
    safe = "/:@!$&'()*+,;=%~-._"
    return urllib.parse.urlunsplit((p.scheme, netloc, urllib.parse.quote(p.path, safe=safe),
                                    urllib.parse.quote(p.query, safe=safe + "?"),
                                    urllib.parse.quote(p.fragment, safe=safe)))


def probe(url):
    res = {"input_url": url, "status": "", "final_url": "", "platform": "", "render": "",
           "text_len": 0, "script_cnt": 0, "program_links": "", "sns_links": "", "error": "", "ssl_relaxed": False}
    ctxs = [ssl.create_default_context()]
    relaxed = ssl.create_default_context()
    relaxed.check_hostname, relaxed.verify_mode = False, ssl.CERT_NONE   # 진단용: 인증서 불량 사이트 다수
    ctxs.append(relaxed)
    for i, ctx in enumerate(ctxs):
        try:
            req = urllib.request.Request(to_ascii_url(url), headers={"User-Agent": UA, "Accept-Language": "ko"})
            with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                raw = r.read(1_500_000)
                res["status"], res["final_url"] = r.status, r.geturl()
                cs = r.headers.get_content_charset() or "utf-8"
            res["ssl_relaxed"] = i == 1
            break
        except ssl.SSLError as e:
            res["error"] = f"SSL: {e}"
            continue
        except urllib.error.HTTPError as e:
            res["status"], res["error"] = e.code, str(e)
            return res
        except Exception as e:
            res["error"] = f"{type(e).__name__}: {e}"
            if "CERTIFICATE" in str(e).upper():
                continue
            return res
    else:
        return res
    try:
        html = raw.decode(cs, errors="replace")
    except LookupError:
        html = raw.decode("utf-8", errors="replace")
    if "euc-kr" in html[:3000].lower() and cs.lower() == "utf-8":
        html = raw.decode("cp949", errors="replace")
    res["error"] = ""

    hay = html[:300_000]
    res["platform"] = (next((n for n, p in URL_PLATFORMS if re.search(p, res["final_url"], re.I)), None)
                       or next((n for n, p in PLATFORMS if re.search(p, res["final_url"] + "\n" + hay, re.I)), None)
                       or ("gov_site" if GOV_URL_RE.search(res["final_url"]) or GOV_HTML_RE.search(hay) else None)
                       or "custom/unknown")
    sns = []
    for n, p in SNS_LINKS:
        for m in re.finditer(p, hay, re.I):
            item = f"{n}:{m.group(1)}"
            if item not in sns and n != res["platform"]:
                sns.append(item)
    res["sns_links"] = " ; ".join(sns[:6])

    body = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", body)).strip()
    res["text_len"] = len(text)
    res["script_cnt"] = len(re.findall(r"(?i)<script", html))
    spa = re.search(r'id=["\'](root|app|__next|__nuxt)["\']', html) and res["text_len"] < 500
    res["render"] = "JS(SPA)필요" if spa or res["text_len"] < 200 else "정적HTML"

    links = []
    for href, label in re.findall(r'(?is)<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', html):
        label = re.sub(r"(?s)<[^>]+>", "", label).strip()
        if any(w in (label + href).lower() for w in PROGRAM_WORDS) and not href.startswith("javascript"):
            full = urllib.parse.urljoin(res["final_url"], href)
            item = f"{label[:15]}→{full}"
            if item not in links:
                links.append(item)
    res["program_links"] = " ; ".join(links[:8])
    return res


def write_csv(path, rows, cols=None):
    cols = cols or (list(rows[0].keys()) if rows else [])
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    key = require_key("YOUTH_CENTER_API_KEY")
    # 서버 정렬이 페이지마다 불안정해서 여러 페이지로 나누면 중복·누락이 생김
    # (pageSize=100 → 251행 중 고유 221). 한 페이지로 받으면 251건 모두 고유.
    items, first = fetch_all("getSpace", key, page_size=1000)
    # 안전장치: 혹시 남은 중복은 cntrSn 기준으로 제거
    seen, uniq = set(), []
    for it in items:
        k = it.get("cntrSn") or json.dumps(it, sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            uniq.append(it)
    if len(uniq) != len(items):
        print(f"중복 {len(items) - len(uniq)}건 제거 → {len(uniq)}건")
    items = uniq
    D.mkdir(parents=True, exist_ok=True)
    (D / "sample_response.json").write_text(json.dumps(first, ensure_ascii=False, indent=2)[:20000], encoding="utf-8")
    dump_jsonl(D / "raw.jsonl", items)
    write_csv(D / "fields.csv", field_profile(items))
    print(f"센터 {len(items)}건 → {D}")

    targets = []
    for it in items:
        fld, url = guess_url(it)
        targets.append((name_of(it), fld, url))
    url_fields = Counter(f for _, f, _ in targets if f)
    print("URL이 들어있는 필드:", dict(url_fields), f"/ URL 없음 {sum(1 for t in targets if not t[2])}건")
    if "--no-web" in sys.argv:
        return

    with_url = [t for t in targets if t[2]]
    print(f"홈페이지 {len(with_url)}곳 접속 진단 중...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda t: probe(t[2]), with_url))
    rows = [{"center": n, "url_field": f, **r} for (n, f, _), r in zip(with_url, results)]
    write_csv(D / "homepage_probe.csv", rows)

    summ = Counter((r["platform"] or "접속실패", r["render"]) for r in rows)
    write_csv(D / "platform_summary.csv",
              [{"platform": p, "render": rd, "count": c} for (p, rd), c in summ.most_common()])
    print("\n[플랫폼 x 렌더링]")
    for (p, rd), c in summ.most_common():
        print(f"  {p:22} {rd or '-':10} {c}")
    fails = Counter((r["error"] or "").split(":")[0] for r in rows if r["error"])
    if fails:
        print("[접속 실패 유형]", dict(fails))


if __name__ == "__main__":
    main()
