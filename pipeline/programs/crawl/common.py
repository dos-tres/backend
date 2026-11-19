"""크롤러 공통: 경로, .env, CSV 입출력, URL 정리, 예의 바른 HTTP 클라이언트.

센터 프로그램 수집 순서 (저장소 루트에서, pipeline/run_daily.py 가 이 순서로 실행):
  python pipeline/programs/crawl/sync_centers.py   # 청년센터 API → centers.csv
  python pipeline/programs/crawl/seoul_orang.py    # 서울청년센터 통합 페이지
  python pipeline/programs/crawl/gnuboard.py       # 그누보드 센터 홈페이지 게시판
  python pipeline/programs/crawl/merge.py          # 두 결과 → programs.csv
결과는 data/runtime/programs/ 에 쌓인다. 자세한 설명: docs/CRAWLER.md
"""
import csv
import os
import re
import threading
import time
import urllib.parse
import urllib.robotparser
from datetime import datetime
from pathlib import Path

import requests
import urllib3

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from pipeline import paths  # noqa: E402

DATA = paths.PROGRAM_DIR
DATA.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (compatible; youth-program-crawler/0.1)"

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- .env ----------
def require_key(name):
    """저장소 루트 .env 에서 읽는다 (pipeline/paths.py)."""
    return paths.require_env(name)


# ---------- CSV ----------
def read_csv(path):
    path = Path(path)
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, cols):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)   # 중간에 죽어도 기존 파일이 깨지지 않게


def append_csv(path, rows, cols):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerows(rows)


# ---------- URL ----------
BARE_DOMAIN_RE = re.compile(r"(?:[\w가-힣-]+\.)+[a-z가-힣]{2,}(?:[/?#][^\s\"'<>]*)?", re.I)


def normalize_url(raw):
    """API의 cntrUrlAddr 정리: 공백·앞쪽 잡문자 제거, scheme 보충. 실패하면 ''."""
    s = (raw or "").strip()
    if not s:
        return ""
    i = s.lower().find("http")
    if i > 0:
        s = s[i:]
    if not s.lower().startswith("http"):
        m = BARE_DOMAIN_RE.match(s.strip(" /"))
        if not m:
            return ""
        s = "http://" + m.group(0)
    return s.rstrip(".,)")


def to_ascii_url(url):
    """한글 도메인은 punycode, 한글 경로/쿼리는 퍼센트 인코딩."""
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


# ---------- HTTP ----------
class Fetcher:
    """호스트별 최소 간격 + robots.txt 준수 + 재시도 + 인증서 불량 사이트 허용 + 인코딩 보정."""

    def __init__(self, delay=1.0, timeout=20, retries=2):
        self.delay, self.timeout, self.retries = delay, timeout, retries
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA, "Accept-Language": "ko,en;q=0.5"})
        self._last, self._robots, self._lock = {}, {}, threading.Lock()
        self.host_locks = {}

    def _host_lock(self, host):
        with self._lock:
            return self.host_locks.setdefault(host, threading.Lock())

    def allowed(self, url):
        p = urllib.parse.urlsplit(url)
        root = f"{p.scheme}://{p.netloc}"
        if root not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = self.s.get(root + "/robots.txt", timeout=10, verify=False)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self._robots[root] = rp
        return self._robots[root].can_fetch(UA, url)

    def get(self, url):
        """(최종URL, html) 반환. 실패 시 예외."""
        return self._request("GET", url)

    def post(self, url, data):
        """폼 POST (상세 페이지가 POST로만 열리는 사이트용). get 과 같은 간격·robots·재시도 규칙."""
        return self._request("POST", url, data)

    def _request(self, method, url, data=None):
        url = to_ascii_url(url)
        if not self.allowed(url):
            raise PermissionError(f"robots.txt 차단: {url}")
        host = urllib.parse.urlsplit(url).netloc
        with self._host_lock(host):
            wait = self._last.get(host, 0) + self.delay - time.time()
            if wait > 0:
                time.sleep(wait)
            err = None
            for attempt in range(self.retries + 1):
                try:
                    r = self.s.request(method, url, data=data, timeout=self.timeout, verify=False)
                    self._last[host] = time.time()
                    if r.encoding is None or r.encoding.lower() == "iso-8859-1":
                        r.encoding = r.apparent_encoding
                    # 일부 사이트(jb2030)는 정상 페이지를 500 상태로 보낸다 → 본문이 충분하면 수용
                    if r.status_code >= 500 and len(r.text) > 20000 and "<body" in r.text.lower():
                        return r.url, r.text
                    r.raise_for_status()
                    return r.url, r.text
                except requests.HTTPError as e:
                    err = e
                    if e.response is not None and e.response.status_code < 500:
                        break
                except requests.RequestException as e:
                    err = e
                self._last[host] = time.time()
                time.sleep(1.5 * (attempt + 1))
            raise err
