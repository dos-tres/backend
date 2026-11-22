"""앱 안 스케줄러: 시작 후 1번 + 매일 정해진 시각에 데이터 파이프라인(pipeline.run_daily)을 돌린다.

팀 결정(노션 「배포 및 운영 결정」 3번): 외부 cron 없이 앱 내부 스케줄러. Lightsail 컨테이너는 잠들지 않는다.

- SCHEDULER_ENABLED=true 일 때만 켠다 (로컬 개발·테스트에서는 꺼 둔다).
- 파이프라인은 별도 프로세스로 돌려 서버(요청 처리)와 메모리·오류를 나눈다. 실패해도 서버는 계속 마지막 정상 데이터로 동작한다.
- DB 주소가 없으면 --no-load (파일만 갱신), LLM 키가 없으면 --no-llm (새 글은 분류하지 않고 캐시로만).
- 끝나면 서비스 JSON 캐시를 비워 DB 없이 운영할 때도 새 파일을 읽게 한다.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import threading
from datetime import datetime, timedelta

from app.catalog import repository

logger = logging.getLogger(__name__)
FIRST_RUN_DELAY = 60   # 초. 서버가 먼저 뜨고 헬스체크를 통과한 뒤에 시작


def pipeline_args(has_db: bool, has_llm: bool) -> list[str]:
    args = [sys.executable, "-m", "pipeline.run_daily"]
    if not has_db:
        args.append("--no-load")
    if not has_llm:
        args.append("--no-llm")
    return args


PREPARE_COMMANDS = [
    ["-m", "alembic", "upgrade", "head"],                              # 테이블 만들기·바꾸기 (여러 번 해도 같음)
    ["-m", "pipeline.load_catalog", "--seed", "--if-empty"],           # 비어 있으면 이미지의 기본 데이터 적재
]


def prepare_database(runner=None) -> bool:
    """배포 첫 시작: 운영 DB 에 테이블을 만들고, 비어 있으면 기본 데이터를 넣는다 (DB_AUTO_MIGRATE).
    실패해도 서버는 서비스 JSON 으로 계속 동작한다(조회 실패 시 파일로 대체)."""
    run = runner or (lambda args: subprocess.run([sys.executable, *args], check=False).returncode)
    for args in PREPARE_COMMANDS:
        try:
            code = run(args)
        except Exception as exc:
            logger.error("database prepare failed to run: %s", type(exc).__name__)
            code = -1
        if code != 0:
            logger.error("database prepare step failed: %s (exit %s)", args[1], code)
            return False
    repository._fallback_rows.cache_clear()
    logger.info("database prepared")
    return True


def seconds_until(hour: int, now: datetime | None = None) -> float:
    now = now or datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


class DailyPipeline:
    def __init__(self, args: list[str], hour: int, runner=None, first_delay: float = FIRST_RUN_DELAY,
                 prepare=None):
        self.args, self.hour, self.first_delay = args, hour, first_delay
        self.prepare = prepare   # 첫 실행 전에 한 번 (DB 준비). 같은 스레드라 적재와 겹치지 않는다
        self.runner = runner or self._run_subprocess
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.last: dict | None = None   # 마지막 실행 결과 (시작·끝·종료코드)
        self.thread = threading.Thread(target=self._loop, name="daily-pipeline", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def shutdown(self) -> None:
        self.stop.set()

    def _run_subprocess(self) -> int:
        return subprocess.run(self.args, check=False).returncode

    def run_once(self) -> int | None:
        if not self.lock.acquire(blocking=False):
            logger.warning("daily pipeline already running, skipped")
            return None
        started = datetime.now()
        try:
            logger.info("daily pipeline start")
            try:
                code = self.runner()
            except Exception as exc:   # 서버는 멈추지 않는다
                logger.error("daily pipeline failed to run: %s", type(exc).__name__)
                code = -1
            repository._fallback_rows.cache_clear()     # 새 서비스 JSON 을 다시 읽게
            repository.data_region_codes.cache_clear()
            self.last = {"started_at": started.isoformat(timespec="seconds"),
                         "finished_at": datetime.now().isoformat(timespec="seconds"), "exit_code": code}
            logger.info("daily pipeline done: exit %s", code)
            return code
        finally:
            self.lock.release()

    def _loop(self) -> None:
        if self.prepare is not None and not self.stop.is_set():
            self.prepare()
        if self.stop.wait(self.first_delay):
            return
        self.run_once()
        while not self.stop.wait(seconds_until(self.hour)):
            self.run_once()
