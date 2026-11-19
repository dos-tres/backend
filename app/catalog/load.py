"""catalog_items 적재: 한 트랜잭션에서 오늘 받은 항목을 upsert 하고, 오늘 목록에 없는 기존 항목은 status='closed'.

행 변환은 rows.py (DB 없이 테스트 가능한 순수 함수).
"""
from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.catalog.models import CatalogItem
from app.catalog.rows import build_rows, policy_row, program_row  # noqa: F401  (pipeline 에서 함께 import)

MIN_RATIO = 0.5   # 오늘 받은 항목이 기존 활성 항목의 절반도 안 되면 수집 이상으로 보고 적재 중단
CHUNK = 500


def upsert_catalog(session: Session, kind: str, rows: list[dict], force: bool = False) -> dict:
    """한 kind 를 통째로 반영한다. 호출한 쪽에서 commit 한다."""
    active = session.scalar(select(func.count()).select_from(CatalogItem)
                            .where(CatalogItem.kind == kind, CatalogItem.status == "ok")) or 0
    if not force and active and len(rows) < active * MIN_RATIO:
        raise RuntimeError(f"{kind}: 오늘 {len(rows)}건 < 기존 활성 {active}건의 {MIN_RATIO:.0%} → 수집 이상으로 보고 중단")
    for start in range(0, len(rows), CHUNK):   # 한 문장의 파라미터 수 제한(65,535)을 넘지 않게 나눠서
        stmt = insert(CatalogItem).values(rows[start:start + CHUNK])
        changed = {c: stmt.excluded[c] for c in rows[0] if c != "id"}
        changed["updated_at"] = func.now()
        session.execute(stmt.on_conflict_do_update(index_elements=[CatalogItem.id], set_=changed))
    ids = [r["id"] for r in rows]
    closed = session.execute(
        update(CatalogItem)
        .where(CatalogItem.kind == kind, CatalogItem.status != "closed", CatalogItem.id.not_in(ids))
        .values(status="closed", updated_at=func.now())
    ).rowcount
    return {"kind": kind, "upserted": len(rows), "closed": closed, "previously_active": active}
