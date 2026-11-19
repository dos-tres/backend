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
    """aplyYmd 'YYYYMMDD ~ YYYYMMDD' 의 마지막 날짜. 상시·미기재면 None."""
    found = YMD.findall(item.get("aplyYmd") or "")
    return _date(found[-1]) if found else None


def _hash(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:64]


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
        "source_hash": _hash(item.get("lastMdfcnDt") or "", json.dumps(item, ensure_ascii=False, sort_keys=True)),
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
        "source_hash": _hash(json.dumps(item, ensure_ascii=False, sort_keys=True)),
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
