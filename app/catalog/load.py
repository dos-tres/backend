"""catalog_items 적재: 한 트랜잭션에서 오늘 받은 항목을 반영하고 변경 이력(catalog_item_changes)을 남긴다.

source_hash 로 기존 행과 비교해 네 가지로 나눈다.
- created  : 처음 보는 항목 → INSERT
- updated  : 해시가 달라짐 → 필터 컬럼·payload 갱신, 바뀌기 전 payload 를 이력에 보관
- reopened : 닫혔던 항목이 다시 나타남 → status='ok' (내용도 바뀌었으면 이전 payload 보관)
- unchanged: 해시 같음 → 이력·updated_at 그대로. 조회수(inqCnt)처럼 해시에서 뺀 값만 payload 에 반영
오늘 목록에 없는 기존 항목은 status='closed' 로 바꾸고 closed 이력을 남긴다.
updated_at 은 '내용·상태가 마지막으로 바뀐 시각'이다.

행 변환은 rows.py (DB 없이 테스트 가능한 순수 함수).
"""
from __future__ import annotations

from sqlalchemy import case, func, insert as sa_insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.catalog.models import CatalogItem, CatalogItemChange
from app.catalog.rows import build_rows, changed_fields, policy_row, program_row  # noqa: F401  (pipeline 에서 함께 import)

MIN_RATIO = 0.5   # 오늘 받은 항목이 기존 활성 항목의 절반도 안 되면 수집 이상으로 보고 적재 중단
CHUNK = 500       # 한 문장의 파라미터 수 제한(65,535)을 넘지 않게 나눠서


def plan_changes(existing: dict[str, tuple[str, str]], rows: list[dict]) -> dict[str, list[str]]:
    """existing: {id: (source_hash, status)} (같은 kind 의 기존 행 전부) → 변경 종류별 id 목록."""
    plan: dict[str, list[str]] = {"created": [], "updated": [], "reopened": [], "unchanged": [], "closed": []}
    seen = set()
    for row in rows:
        seen.add(row["id"])
        old = existing.get(row["id"])
        if old is None:
            plan["created"].append(row["id"])
        elif old[1] != "ok":
            plan["reopened"].append(row["id"])
        elif old[0] != row["source_hash"]:
            plan["updated"].append(row["id"])
        else:
            plan["unchanged"].append(row["id"])
    plan["closed"] = sorted(i for i, (_, status) in existing.items() if status != "closed" and i not in seen)
    return plan


def _chunks(items: list, size: int = CHUNK):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def upsert_catalog(session: Session, kind: str, rows: list[dict], force: bool = False) -> dict:
    """한 kind 를 통째로 반영한다. 호출한 쪽에서 commit 한다."""
    item = CatalogItem
    existing = {i: (h, s) for i, h, s in session.execute(
        select(item.id, item.source_hash, item.status).where(item.kind == kind))}
    active = sum(1 for _, status in existing.values() if status == "ok")
    if not force and active and len(rows) < active * MIN_RATIO:
        raise RuntimeError(f"{kind}: 오늘 {len(rows)}건 < 기존 활성 {active}건의 {MIN_RATIO:.0%} → 수집 이상으로 보고 중단")

    plan = plan_changes(existing, rows)
    by_id = {r["id"]: r for r in rows}

    # 내용이 바뀐 항목은 덮어쓰기 전에 이전 payload 를 읽어 둔다
    content_changed = plan["updated"] + [i for i in plan["reopened"] if existing[i][0] != by_id[i]["source_hash"]]
    old_payloads: dict[str, dict] = {}
    for ids in _chunks(content_changed):
        # Result 객체에는 keys() 가 있어 dict.update 가 매핑으로 착각하므로 직접 푼다
        for item_id, payload in session.execute(select(item.id, item.payload).where(item.id.in_(ids))):
            old_payloads[item_id] = payload

    for chunk in _chunks(rows):
        stmt = insert(item).values(chunk)
        excluded = stmt.excluded
        changed = {c: excluded[c] for c in chunk[0] if c != "id"}
        # 해시나 상태가 달라졌을 때만 updated_at 을 옮긴다 (inqCnt 만 바뀐 날은 그대로)
        changed["updated_at"] = case(
            (or_(item.source_hash != excluded.source_hash, item.status != excluded.status), func.now()),
            else_=item.updated_at)
        session.execute(stmt.on_conflict_do_update(
            index_elements=[item.id], set_=changed,
            # 완전히 같은 행은 쓰지 않는다. 원본이 같아도 변환 규칙이 바뀌면(예: 마감일 계산) 파생 컬럼이 달라지므로
            # source_hash 만이 아니라 저장하는 컬럼 전부를 비교한다. 이 경우 이력·updated_at 은 그대로다.
            where=or_(*(getattr(item, c).is_distinct_from(excluded[c]) for c in chunk[0] if c != "id")),
        ))

    closed_ids: list[str] = []
    for ids in _chunks(plan["closed"]):
        closed_ids += session.scalars(
            update(item).where(item.kind == kind, item.status != "closed", item.id.in_(ids))
            .values(status="closed", updated_at=func.now()).returning(item.id)).all()

    history = []
    for i in plan["created"]:
        history.append({"item_id": i, "kind": kind, "change_type": "created", "old_hash": None,
                        "new_hash": by_id[i]["source_hash"], "changed_fields": [], "old_payload": None})
    for change_type in ("updated", "reopened"):
        for i in plan[change_type]:
            old_payload = old_payloads.get(i)
            history.append({"item_id": i, "kind": kind, "change_type": change_type, "old_hash": existing[i][0],
                            "new_hash": by_id[i]["source_hash"], "old_payload": old_payload,
                            "changed_fields": changed_fields(old_payload, by_id[i]["payload"]) if old_payload else []})
    for i in closed_ids:
        history.append({"item_id": i, "kind": kind, "change_type": "closed", "old_hash": existing[i][0],
                        "new_hash": None, "changed_fields": [], "old_payload": None})
    for chunk in _chunks(history):
        session.execute(sa_insert(CatalogItemChange), chunk)

    return {"kind": kind, "received": len(rows), "created": len(plan["created"]), "updated": len(plan["updated"]),
            "reopened": len(plan["reopened"]), "unchanged": len(plan["unchanged"]), "closed": len(closed_ids),
            "previously_active": active}
