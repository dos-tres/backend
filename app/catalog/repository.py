"""추천 후보 조회: DB(catalog_items) 우선, DB가 없거나 실패하면 서비스 JSON으로 대신한다.

조건은 둘 다 같다 (rows.matches_basic): 사용 중(ok), 마감 전, 나이, 거주지.
- 정책: 사용자 시군구가 정책 거주지 요건(zipCd)에 포함
- 프로그램: 같은 시군구 센터 또는 같은 시도 센터
"""
from __future__ import annotations

import json
import logging
from datetime import date
from functools import lru_cache

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.catalog.models import CatalogItem
from app.catalog.rows import build_rows, matches_basic
from pipeline import paths

logger = logging.getLogger(__name__)
COLUMNS = ("id", "kind", "status", "title", "age_min", "age_max", "region_cds", "sido_cds", "domains",
           "situations", "access_type", "deadline", "source_hash", "payload")


def from_db(session: Session, sigungu_cd: str, age: int | None, today: date) -> list[dict]:
    item = CatalogItem
    stmt = select(item).where(
        item.status == "ok",
        or_(item.deadline.is_(None), item.deadline >= today),
        or_(
            and_(item.kind == "policy", item.region_cds.contains([sigungu_cd])),
            and_(item.kind == "program", or_(item.region_cds.contains([sigungu_cd]),
                                             item.sido_cds.contains([sigungu_cd[:2]]))),
        ),
    )
    if age is not None:
        stmt = stmt.where(or_(item.age_min.is_(None), item.age_min <= age),
                          or_(item.age_max.is_(None), item.age_max >= age))
    return [{c: getattr(row, c) for c in COLUMNS} for row in session.scalars(stmt)]


def _serving_file(name: str):
    runtime = paths.SERVING_DIR / name
    return runtime if runtime.exists() else paths.SEED_SERVING_DIR / name


@lru_cache(maxsize=1)
def _fallback_rows() -> tuple[dict, ...]:
    rows = build_rows("policy", json.loads(_serving_file("policies_serving.json").read_text(encoding="utf-8")))
    rows += build_rows("program", json.loads(_serving_file("programs_serving.json").read_text(encoding="utf-8")))
    return tuple(rows)


@lru_cache(maxsize=1)
def known_sigungu_codes() -> frozenset[str]:
    """원본(온통청년)이 쓰는 시군구 코드 전체. 전국 정책의 zipCd 목록과 지역 정책·프로그램 코드를 합친다.

    원본은 행정구역 개편을 반영한 코드를 쓴다 (예: 광주·전남 통합 → 12xxx, 강원 51xxx, 전북 52xxx).
    옛 코드(예: 곡성 46720)를 받으면 후보가 0건이 되므로 추천 전에 걸러 낸다.
    """
    return frozenset(code for r in _fallback_rows() for code in r["region_cds"] if len(code) == 5)


def from_files(sigungu_cd: str, age: int | None, today: date) -> list[dict]:
    return [r for r in _fallback_rows() if matches_basic(r, sigungu_cd, age, today)]


def find_candidates(session: Session | None, sigungu_cd: str, age: int | None, today: date) -> tuple[list[dict], str]:
    """(후보 행 목록, 출처 'db' 또는 'file')."""
    if session is not None:
        try:
            rows = from_db(session, sigungu_cd, age, today)
            loaded = rows or session.scalar(select(CatalogItem.id).where(CatalogItem.status == "ok").limit(1))
            if loaded:
                return rows, "db"
            # 테이블이 비어 있으면(아직 적재 전) 파일로 대신한다
        except SQLAlchemyError as exc:
            logger.warning("catalog DB 조회 실패, 서비스 JSON으로 대신함: %s", type(exc).__name__)
            session.rollback()
    return from_files(sigungu_cd, age, today), "file"
