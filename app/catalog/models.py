"""정책·청년센터 프로그램 통합 테이블 (Postgres 중간 방법).

거르는 데 쓰는 칸만 컬럼으로 두고, 화면에 보여줄 나머지는 payload(JSONB)에 통째로 넣는다.
필드가 늘어도 payload 에만 추가하면 되므로 마이그레이션이 필요 없다. 결정 배경: docs/RECOMMENDATION.md
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Identity, Index, Integer, String,
                        Text, func)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CatalogItem(Base):
    __tablename__ = "catalog_items"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)           # policy:{plcyNo} / program:{program_id}
    kind: Mapped[str] = mapped_column(String(10), nullable=False)          # policy / program
    status: Mapped[str] = mapped_column(String(10), nullable=False)        # ok / closed
    title: Mapped[str] = mapped_column(Text, nullable=False)
    age_min: Mapped[int | None] = mapped_column(Integer)                   # 빈값 = 제한 없음
    age_max: Mapped[int | None] = mapped_column(Integer)
    region_cds: Mapped[list[str]] = mapped_column(ARRAY(String(10)), nullable=False)   # 시군구(5자리) 또는 시도(2자리)
    sido_cds: Mapped[list[str]] = mapped_column(ARRAY(String(2)), nullable=False)      # region_cds 의 시도 (프로그램 같은 시도 매칭용)
    domains: Mapped[list[str]] = mapped_column(ARRAY(String(1)), nullable=False)       # E/P/O/C/U, 주 영역이 앞
    situations: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False)
    access_type: Mapped[str | None] = mapped_column(String(10))           # apply / visit
    deadline: Mapped[date | None] = mapped_column(Date)                    # 신청 마감일 (없으면 상시·미기재)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)   # 원본이 바뀌었는지 비교
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)           # 서비스 JSON 항목 전체
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_catalog_items_kind_status", "kind", "status"),
        Index("ix_catalog_items_region_cds", "region_cds", postgresql_using="gin"),
        Index("ix_catalog_items_sido_cds", "sido_cds", postgresql_using="gin"),
    )


CHANGE_TYPES = ("created", "updated", "reopened", "closed")


class CatalogItemChange(Base):
    """catalog_items 변경 이력. 적재할 때 새로 생김·내용 바뀜·다시 열림·닫힘을 한 줄씩 쌓는다.

    updated·reopened(내용도 바뀐 경우)는 바뀌기 전 payload 를 old_payload 에 남긴다.
    찜·신청한 항목의 변경 알림, 수집 이상 추적에 쓴다.
    """
    __tablename__ = "catalog_item_changes"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(80), ForeignKey("catalog_items.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    change_type: Mapped[str] = mapped_column(String(10), nullable=False)
    old_hash: Mapped[str | None] = mapped_column(String(64))
    new_hash: Mapped[str | None] = mapped_column(String(64))
    changed_fields: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)   # payload 최상위 필드 이름
    old_payload: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))   # None → SQL NULL (JSON null 아님)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        CheckConstraint("change_type IN ('created', 'updated', 'reopened', 'closed')", name="change_type"),
        Index("ix_catalog_item_changes_item_id_changed_at", "item_id", "changed_at"),
        Index("ix_catalog_item_changes_changed_at", "changed_at"),
    )
