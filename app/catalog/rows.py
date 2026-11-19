"""서비스 JSON 항목 → catalog_items 행 변환과 자격 조건 거르기 (DB 없이 쓰는 순수 함수).

DB 적재(load.py)와 DB가 없을 때의 대체 조회(repository.py)가 같은 변환을 쓴다.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date

YMD = re.compile(r"(\d{8})")


def _date(text: str | None) -> date | None:
    if not text:
        return None
    digits = text.replace("-", "")[:8]
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def policy_deadline(item: dict) -> date | None:
    """신청 마감일: aplyYmd 'YYYYMMDD ~ YYYYMMDD' 의 마지막 날짜.

    신청기간이 비어 있으면 사업 종료일(bizPrdEndYmd)을 쓴다. 신청기간 없이 끝난 행사·사업
    (예: 9월에 끝난 축제)이 마감 필터를 통과하지 않게 한다. 둘 다 없으면 상시·미기재로 보고 None.
    """
    found = YMD.findall(item.get("aplyYmd") or "")
    if found:
        return _date(found[-1])
    biz_end = YMD.findall(item.get("bizPrdEndYmd") or "")
    return _date(biz_end[-1]) if biz_end else None


# 내용 변경이 아닌데 매일 바뀌는 필드. payload 에는 남기되 source_hash·변경 이력 비교에서는 뺀다.
VOLATILE_FIELDS = frozenset({"inqCnt"})   # 정책 조회수


def content_hash(item: dict) -> str:
    """원본 항목의 내용 해시 (VOLATILE_FIELDS 제외). 같으면 바뀐 것이 없다고 본다."""
    stable = {k: v for k, v in item.items() if k not in VOLATILE_FIELDS}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def changed_fields(old: dict, new: dict) -> list[str]:
    """두 payload 사이에 값이 달라진 최상위 필드 (VOLATILE_FIELDS 제외, 이름순)."""
    keys = (set(old) | set(new)) - VOLATILE_FIELDS
    return sorted(k for k in keys if old.get(k) != new.get(k))


def policy_row(item: dict) -> dict:
    zips = list(dict.fromkeys(item.get("zipCd") or []))
    return {
        "id": f"policy:{item['plcyNo']}",
        "kind": "policy",
        "status": "ok",
        "title": (item.get("plcyNm") or "").strip(),
        "age_min": item.get("age_min_clean"),
        "age_max": item.get("age_max_clean"),
        "region_cds": zips,
        "sido_cds": sorted({z[:2] for z in zips}),
        "domains": list(item.get("i5_domains") or []),
        "situations": list(item.get("situations") or []),
        "access_type": item.get("access_type"),
        "deadline": policy_deadline(item),
        "source_hash": content_hash(item),
        "payload": item,
    }


def program_row(item: dict) -> dict:
    regions = list(dict.fromkeys(item.get("region_cds") or []))
    return {
        "id": f"program:{item['program_id']}",
        "kind": "program",
        "status": "ok",
        "title": (item.get("title") or "").strip(),
        "age_min": None,
        "age_max": None,
        "region_cds": regions,
        "sido_cds": sorted({c[:2] for c in regions}),
        "domains": list(item.get("i5_domains") or []),
        "situations": list(item.get("situations") or []),
        "access_type": item.get("access_type"),
        "deadline": _date(item.get("aply_end")),
        "source_hash": content_hash(item),
        "payload": item,
    }


def build_rows(kind: str, serving: dict) -> list[dict]:
    """서비스 JSON 한 개(policies_serving.json / programs_serving.json) → 행 목록."""
    if kind == "policy":
        return [policy_row(p) for p in serving["policies"]]
    if kind == "program":
        return [program_row(p) for p in serving["programs"]]
    raise ValueError(f"unknown kind: {kind}")


def scope_of(row: dict, sigungu_cd: str) -> str:
    """사용자 위치 기준 범위: 시군구(우리 동네) / 광역 / 전국."""
    regions = row["region_cds"]
    if row["kind"] == "policy":
        return (row["payload"].get("region_scope") or ("전국" if len(regions) >= 240 else "광역"))
    return "시군구" if sigungu_cd in regions else "광역"


def matches_basic(row: dict, sigungu_cd: str, age: int | None, today: date) -> bool:
    """DB 쿼리와 같은 조건: 사용 중(ok), 마감 전, 나이, 거주지(정책은 시군구 일치, 프로그램은 같은 시도까지)."""
    if row["status"] != "ok" or (row["deadline"] and row["deadline"] < today):
        return False
    if age is not None and ((row["age_min"] and age < row["age_min"]) or (row["age_max"] and age > row["age_max"])):
        return False
    if row["kind"] == "policy":
        return sigungu_cd in row["region_cds"]
    return sigungu_cd in row["region_cds"] or sigungu_cd[:2] in row["sido_cds"]
