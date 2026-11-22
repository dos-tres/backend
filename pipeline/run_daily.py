"""매일 실행하는 데이터 파이프라인을 순서대로 돌린다.

  python -m pipeline.run_daily              # 전체
  python -m pipeline.run_daily --skip-crawl # 센터 크롤링 제외 (정책만 갱신)
  python -m pipeline.run_daily --no-llm     # LLM 호출 없이 캐시로만 분류 (키가 없을 때·비용 없이 확인할 때)
  python -m pipeline.run_daily --no-load    # DB 적재 제외 (파일만 만들기)

순서: 정책 수집 → 정책 분류 → 센터 목록 → 서울청년센터 → 그누보드 → 프로그램 통합 → 프로그램 분류 → DB 적재
한 단계가 실패하면 그 단계에 의존하는 뒤 단계는 건너뛰고, 서비스는 마지막으로 성공한 데이터로 계속 동작한다.
서버 안 스케줄러 연결(앱 시작 시 1회 + 하루 1회)은 다음 작업이다 (docs/RECOMMENDATION.md).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

from pipeline.paths import PROGRAM_DIR, ROOT

STEPS = [
    # (이름, 명령, 묶음) — 같은 묶음에서 앞 단계가 실패하면 뒤 단계를 건너뛴다
    ("정책 수집", ["pipeline/policies/fetch.py"], "policy"),
    ("정책 분류", ["pipeline/policies/classify.py"], "policy"),
    ("센터 목록", ["pipeline/programs/crawl/sync_centers.py"], "program"),
    ("센터 공간소개·공지", ["-m", "pipeline.programs.crawl.seoul_centers"], "center-content"),
    ("서울청년센터", ["pipeline/programs/crawl/seoul_orang.py"], "program"),
    ("그누보드", ["pipeline/programs/crawl/gnuboard.py"], "program"),
    ("프로그램 통합", ["pipeline/programs/crawl/merge.py"], "program"),
    ("프로그램 정보 추출", ["-m", "pipeline.programs.extract_facts"], "program"),
    ("프로그램 분류", ["pipeline/programs/classify.py"], "program"),
]


def run(name: str, args: list[str]) -> bool:
    start = time.time()
    print(f"\n▶ {name}: {' '.join(args)}", flush=True)
    code = subprocess.run([sys.executable, *args], cwd=ROOT).returncode
    print(f"{'✓' if code == 0 else '✗'} {name} ({time.time() - start:.0f}초, 종료코드 {code})", flush=True)
    return code == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-crawl", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--no-load", action="store_true")
    args = ap.parse_args(argv)

    broken: set[str] = set()
    for name, cmd, group in STEPS:
        if group in {"program", "center-content"} and args.skip_crawl and "classify" not in cmd[0] and "pipeline.programs.extract_facts" not in cmd:
            continue
        if group in broken:
            print(f"- {name}: 앞 단계 실패로 건너뜀")
            continue
        if args.no_llm and (cmd[0].endswith("classify.py") or "pipeline.programs.extract_facts" in cmd):
            cmd = [*cmd, "--no-llm"]
        if cmd[0].endswith("seoul_orang.py") and not (PROGRAM_DIR / "seoul_orang" / "programs.csv").exists():
            cmd = [*cmd, "--full"]   # 첫 실행(새 컨테이너)은 목록 전체를 받는다
        if not run(name, cmd):
            broken.add(group)

    if not args.no_load:
        load = ["-m", "pipeline.load_catalog"]
        if broken:
            # 실패한 묶음은 적재하지 않는다 (어제 데이터 유지)
            for kind in ("policy", "program"):
                if kind not in broken:
                    run(f"DB 적재 ({kind})", [*load, "--kind", kind])
        else:
            run("DB 적재", load)
    print(f"\n완료. 실패한 묶음: {sorted(broken) or '없음'}")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
