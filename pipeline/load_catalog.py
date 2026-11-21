"""서비스 JSON → catalog_items 적재. 파이프라인 마지막 단계.

  python -m pipeline.load_catalog                 # data/runtime/serving/ 의 결과를 적재
  python -m pipeline.load_catalog --seed          # data/seed/serving/ 의 기본 데이터를 적재 (첫 배포·로컬 개발)
  python -m pipeline.load_catalog --kind program  # 하나만
  python -m pipeline.load_catalog --force         # 건수가 크게 줄어도 적재 (평소에는 쓰지 않는다)
  python -m pipeline.load_catalog --seed --if-empty  # 그 kind 가 비어 있을 때만 (배포 첫 시작, app/scheduler.py)

DATABASE_URL 은 앱과 같은 설정(프로세스 환경변수 → 저장소 루트 .env)을 쓴다.
정책과 프로그램은 각각 한 트랜잭션: 실패하면 그 kind 는 어제 데이터가 그대로 남는다.
"""
from __future__ import annotations

import argparse
import json
import sys

from sqlalchemy import select

from app.catalog.load import build_rows, upsert_catalog
from app.catalog.models import CatalogItem
from app.config import Settings
from app.database import Database
from pipeline import paths

FILES = {"policy": "policies_serving.json", "program": "programs_serving.json"}


def serving_path(kind: str, seed: bool):
    name = FILES[kind]
    runtime = paths.SERVING_DIR / name
    if not seed and runtime.exists():
        return runtime
    return paths.SEED_SERVING_DIR / name


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--kind", choices=sorted(FILES))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--if-empty", action="store_true", help="이미 행이 있는 kind 는 건너뛴다")
    args = ap.parse_args(argv)

    url = Settings().database_url.get_secret_value()
    if not url:
        print("DATABASE_URL 이 없습니다. 저장소 루트 .env 를 확인하세요.", file=sys.stderr)
        return 2
    database = Database(url)
    failed = False
    try:
        for kind in [args.kind] if args.kind else ["policy", "program"]:
            if args.if_empty:
                with database.sessions() as session:
                    if session.scalar(select(CatalogItem.id).where(CatalogItem.kind == kind).limit(1)):
                        print(f"{kind}: 이미 적재돼 있어 건너뜀 (--if-empty)")
                        continue
            path = serving_path(kind, args.seed)
            rows = build_rows(kind, json.loads(path.read_text(encoding="utf-8")))
            try:
                with database.sessions() as session:
                    result = upsert_catalog(session, kind, rows, force=args.force)
                    session.commit()
                print(f"{kind}: {path.relative_to(paths.ROOT)} → {result}")
            except Exception as exc:   # 한 kind 가 실패해도 다른 kind 는 진행
                failed = True
                print(f"{kind}: 적재 실패, 기존 데이터 유지 ({type(exc).__name__}: {exc})", file=sys.stderr)
    finally:
        database.dispose()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
