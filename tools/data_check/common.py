"""API 조사용 공통: .env 로딩 + 온통청년 API 페이지 수집 (표준 라이브러리만 사용).

서비스 파이프라인이 아니라 필드·코드 조사용 도구다. 조사 결과 정리: docs/POLICY_FIELDS.md, docs/CENTER_FIELDS.md
  python tools/data_check/inspect_policies.py
  python tools/data_check/inspect_centers.py
결과는 data/runtime/data_check/ 에 저장된다.
"""
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "data" / "runtime" / "data_check"
BASE = "https://www.youthcenter.go.kr/go/ythip"
UA = "Mozilla/5.0 (data-check script)"


def load_env(path=ROOT / ".env"):
    """python-dotenv 없이 KEY=VALUE 형식만 읽는다. 이미 설정된 환경변수가 우선."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def require_key(name):
    load_env()
    key = os.environ.get(name, "")
    if not key or not key.isascii():   # .env.example 의 한글 placeholder 그대로면 거부
        raise SystemExit(f"{name} 가 비어 있습니다. 저장소 루트 .env 에 키를 넣으세요.")
    return key


def get_json(endpoint, params):
    url = f"{BASE}/{endpoint}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
            if isinstance(data, dict) and data.get("errorCode"):
                raise SystemExit(f"API 오류 {data['errorCode']}: {data.get('errorMsg')}")
            return data
        except SystemExit:
            raise
        except Exception as e:
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


def fetch_all(endpoint, key, page_size=100, extra=None, max_pages=None):
    """전체 페이지 수집. 첫 페이지 원본 응답도 함께 반환(구조 확인용)."""
    items, page, total, first = [], 1, None, None
    while True:
        params = {"apiKeyNm": key, "pageNum": page, "pageSize": page_size, "rtnType": "json"}
        params.update(extra or {})
        data = get_json(endpoint, params)
        if page == 1:
            first, total = data, find_total(data)
            print(f"[{endpoint}] 전체 건수(응답 기준): {total}")
        batch = find_list(data) or []
        if not batch:
            break
        items.extend(batch)
        print(f"  {page}페이지 +{len(batch)} (누적 {len(items)})")
        if len(batch) < page_size or (total and len(items) >= total):
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(0.3)
    return items, first


def dump_jsonl(path, items):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


def field_profile(items, max_examples=3):
    """필드별 채움률·고유값 수·예시값 — 원본 형식 파악용."""
    keys = []
    for it in items:
        for k in it:
            if k not in keys:
                keys.append(k)
    rows = []
    for k in keys:
        vals = [str(it.get(k) if it.get(k) is not None else "").strip() for it in items]
        filled = [v for v in vals if v not in ("", "-", "null", "None")]
        uniq = list(dict.fromkeys(filled))
        rows.append({
            "field": k,
            "fill_pct": round(100 * len(filled) / max(len(items), 1)),
            "n_unique": len(uniq),
            "examples": " | ".join(v.replace("\n", " ")[:60] for v in uniq[:max_examples]),
        })
    return rows
