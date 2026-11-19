"""청년센터 API(getSpace) → data/runtime/programs/centers.csv 동기화 + 변경 이력 기록.

  python pipeline/programs/crawl/sync_centers.py              # API를 받아 centers.csv와 비교·갱신
  python pipeline/programs/crawl/sync_centers.py --from-seed  # API 호출 없이 data/seed/programs/centers_seed.jsonl 로 초기화
  python pipeline/programs/crawl/sync_centers.py --dry-run    # 비교 결과만 출력, 파일은 그대로

centers.csv 는 지운 센터도 남겨 둔다(status=removed). 크롤 결과의 cntrSn 이 끊기지 않게 하기 위해서다.
변경 내역은 data/runtime/programs/centers_changes.csv 에 계속 추가된다.

API 주의(docs/CENTER_FIELDS.md): 여러 페이지로 나누면 정렬이 흔들려 누락이 생김 → pageSize=1000 한 번에.
"""
import json
import sys

import requests

from common import DATA, append_csv, normalize_url, now, paths, read_csv, require_key, write_csv

API = "https://www.youthcenter.go.kr/go/ythip/getSpace"
CENTERS = DATA / "centers.csv"
CHANGES = DATA / "centers_changes.csv"
SEED = paths.SEED_PROGRAM_DIR / "centers_seed.jsonl"

API_FIELDS = ["cntrSn", "cntrNm", "cntrAddr", "cntrDaddr", "cntrTelno", "cntrUrlAddr",
              "stdgCtpvCd", "stdgCtpvCdNm", "stdgSggCd", "stdgSggCdNm"]
COLS = API_FIELDS + ["region_cd", "homepage", "status", "first_seen", "last_seen", "last_changed"]
CHANGE_COLS = ["synced_at", "change", "cntrSn", "cntrNm", "field", "old", "new"]
MIN_RATIO = 0.8   # 활성 센터의 80% 미만만 오면 API 이상으로 보고 중단 (대량 '삭제' 오판 방지)


def fetch_api():
    key = require_key("YOUTH_CENTER_API_KEY")
    params = {"apiKeyNm": key, "pageNum": 1, "pageSize": 1000, "rtnType": "json"}
    for attempt in range(3):
        try:
            r = requests.get(API, params=params, timeout=60, headers={"User-Agent": "youth-crawler"})
            r.raise_for_status()
            data = r.json()
            break
        except (requests.RequestException, ValueError) as e:
            if attempt == 2:
                raise SystemExit(f"API 호출 실패: {e}")
    if data.get("resultCode") != 200:
        raise SystemExit(f"API 오류: {data.get('resultCode')} {data.get('resultMessage')}")
    items = data["result"]["youthPolicyList"]   # 센터 API도 키 이름이 이렇다
    total = data["result"]["pagging"]["totCount"]
    if len(items) >= 1000:
        print("⚠ 1000건이 꽉 찼다. pageSize를 늘리거나 페이지 처리를 다시 검토할 것")
    return items, total


def load_seed():
    return [json.loads(line) for line in open(SEED, encoding="utf-8")]


def to_row(it):
    row = {k: str(it.get(k) if it.get(k) is not None else "").strip() for k in API_FIELDS}
    row["region_cd"] = row["stdgCtpvCd"] + row["stdgSggCd"]   # 정책 zipCd 와 같은 5자리 시군구 코드
    row["homepage"] = normalize_url(row["cntrUrlAddr"])
    return row


def main():
    dry = "--dry-run" in sys.argv
    ts = now()
    if "--from-seed" in sys.argv:
        items, total = load_seed(), "?"
        print(f"seed 파일에서 {len(items)}건")
    else:
        items, total = fetch_api()
        print(f"API {len(items)}건 (totCount {total})")

    incoming = {}
    for it in items:
        r = to_row(it)
        incoming.setdefault(r["cntrSn"], r)   # 혹시 모를 중복은 첫 값 유지

    old = {r["cntrSn"]: r for r in read_csv(CENTERS)}
    active_before = [r for r in old.values() if r.get("status") == "active"]
    if active_before and len(incoming) < MIN_RATIO * len(active_before):
        raise SystemExit(f"받은 센터 {len(incoming)}건 < 기존 활성 {len(active_before)}건의 {MIN_RATIO:.0%}. "
                         "API 이상으로 보고 갱신하지 않음")

    changes, out = [], {}
    for sn, new in incoming.items():
        prev = old.get(sn)
        row = {**new, "status": "active", "last_seen": ts}
        if prev is None:
            row.update(first_seen=ts, last_changed=ts)
            changes.append({"change": "added", "cntrSn": sn, "cntrNm": new["cntrNm"]})
        else:
            row["first_seen"] = prev.get("first_seen") or ts
            row["last_changed"] = prev.get("last_changed") or ts
            if prev.get("status") == "removed":
                row["last_changed"] = ts
                changes.append({"change": "reappeared", "cntrSn": sn, "cntrNm": new["cntrNm"]})
            for f in API_FIELDS:
                if (prev.get(f) or "") != new[f]:
                    row["last_changed"] = ts
                    changes.append({"change": "modified", "cntrSn": sn, "cntrNm": new["cntrNm"],
                                    "field": f, "old": prev.get(f, ""), "new": new[f]})
        out[sn] = row
    for sn, prev in old.items():
        if sn in out:
            continue
        row = dict(prev)
        if prev.get("status") != "removed":
            row.update(status="removed", last_changed=ts)
            changes.append({"change": "removed", "cntrSn": sn, "cntrNm": prev.get("cntrNm", "")})
        out[sn] = row

    for c in changes:
        c["synced_at"] = ts
    summary = {k: sum(1 for c in changes if c["change"] == k) for k in ("added", "removed", "reappeared")}
    summary["modified(센터 수)"] = len({c["cntrSn"] for c in changes if c["change"] == "modified"})
    print(f"활성 {sum(1 for r in out.values() if r['status'] == 'active')} / 전체 {len(out)}  변경: {summary}")
    for c in changes[:30]:
        extra = f"  {c['field']}: {c['old']!r} → {c['new']!r}" if c["change"] == "modified" else ""
        print(f"  [{c['change']}] {c['cntrSn']} {c['cntrNm']}{extra}")
    if len(changes) > 30:
        print(f"  ... 외 {len(changes) - 30}건 → {CHANGES.name}")
    if dry:
        print("(dry-run: 파일은 그대로)")
        return

    rows = sorted(out.values(), key=lambda r: (r["status"] != "active", r["stdgCtpvCd"], r["stdgSggCd"], r["cntrNm"]))
    write_csv(CENTERS, rows, COLS)
    if changes:
        append_csv(CHANGES, changes, CHANGE_COLS)
    print(f"→ {CENTERS}")


if __name__ == "__main__":
    main()
