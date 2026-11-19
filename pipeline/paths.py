"""파이프라인 공통 경로와 .env 로딩.

데이터 위치
  data/seed/      저장소에 포함. Docker 이미지에 들어가는 기본 데이터 (서비스 JSON, LLM 분류 캐시, 센터 목록 시드)
  data/runtime/   매일 생성. Git 제외. 컨테이너 재시작 시 사라져도 seed 와 DB 로 복구된다
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed"
RUNTIME = ROOT / "data" / "runtime"

POLICY_DIR = RUNTIME / "policies"            # 정책 API 수집 결과 (policies.csv 등)
PROGRAM_DIR = RUNTIME / "programs"           # 센터 크롤링 결과 (centers.csv, programs.csv 등)
SERVING_DIR = RUNTIME / "serving"            # 서비스용 JSON (DB 적재 전 단계, DB 장애 시 대체 데이터)
CACHE_DIR = RUNTIME / "cache"                # LLM 분류 캐시

SEED_SERVING_DIR = SEED / "serving"
SEED_CACHE_DIR = SEED / "cache"
SEED_PROGRAM_DIR = SEED / "programs"


def load_env() -> None:
    """저장소 루트 .env 를 읽는다. 이미 설정된 프로세스 환경변수가 우선 (app.config 와 같은 우선순위)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(*names: str) -> str:
    """names 중 처음 값이 있는 환경변수. 비었거나 .env.example 의 한글 안내문 그대로면 종료."""
    load_env()
    for name in names:
        value = os.environ.get(name, "")
        if value and value.isascii():
            return value
    raise SystemExit(f"{' 또는 '.join(names)} 가 없습니다. 저장소 루트 .env 에 넣으세요 (.env.example 참고).")


def cache_file(name: str) -> Path:
    """runtime 캐시 경로. 처음 실행이면 seed 캐시를 복사해 시작한다 (이미 분류한 결과 재사용 → LLM 비용 절약)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    seed = SEED_CACHE_DIR / name
    if not path.exists() and seed.exists():
        shutil.copyfile(seed, path)
    return path


def write_atomic(path: Path, text: str) -> None:
    """다 쓴 뒤 교체한다. 중간에 실패해도 이전 파일이 남는다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
