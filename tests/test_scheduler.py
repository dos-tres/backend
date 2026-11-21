"""앱 안 스케줄러 (app/scheduler.py). 실제 파이프라인은 돌리지 않는다."""
import sys
import threading
import unittest
from datetime import datetime

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.scheduler import DailyPipeline, pipeline_args, seconds_until


class SchedulerTests(unittest.TestCase):
    def test_args_follow_settings(self):
        self.assertEqual(pipeline_args(True, True), [sys.executable, "-m", "pipeline.run_daily"])
        self.assertEqual(pipeline_args(False, False)[-2:], ["--no-load", "--no-llm"])

    def test_seconds_until_next_run(self):
        self.assertEqual(seconds_until(4, datetime(2026, 11, 22, 3, 0)), 3600)
        self.assertEqual(seconds_until(4, datetime(2026, 11, 22, 5, 0)), 23 * 3600)

    def test_runs_once_after_delay_and_survives_errors(self):
        calls = []
        done = threading.Event()

        def runner():
            calls.append(1)
            done.set()
            raise RuntimeError("boom")   # 파이프라인이 터져도 스케줄러·서버는 계속

        daily = DailyPipeline([], hour=4, runner=runner, first_delay=0)
        daily.start()
        self.assertTrue(done.wait(5))
        daily.shutdown()
        daily.thread.join(5)
        self.assertEqual(calls, [1])
        self.assertEqual(daily.last["exit_code"], -1)

    def test_no_overlap(self):
        gate = threading.Event()
        daily = DailyPipeline([], hour=4, runner=lambda: gate.wait(5) and 0)
        t = threading.Thread(target=daily.run_once)
        t.start()
        while not daily.lock.locked():
            pass
        self.assertIsNone(daily.run_once())   # 이미 도는 중이면 건너뜀
        gate.set()
        t.join(5)

    def test_prepare_runs_migration_then_seed_and_stops_on_failure(self):
        from app.scheduler import prepare_database
        calls = []
        self.assertTrue(prepare_database(lambda args: calls.append(args[1]) or 0))
        self.assertEqual(calls, ["alembic", "pipeline.load_catalog"])
        calls.clear()
        self.assertFalse(prepare_database(lambda args: calls.append(args[1]) or 1))
        self.assertEqual(calls, ["alembic"])   # 테이블 만들기가 실패하면 적재는 안 함

    def test_prepare_runs_before_first_pipeline(self):
        order, done = [], threading.Event()
        daily = DailyPipeline([], hour=4, runner=lambda: order.append("pipeline") or done.set() or 0,
                              first_delay=0, prepare=lambda: order.append("prepare"))
        daily.start()
        self.assertTrue(done.wait(5))
        daily.shutdown()
        self.assertEqual(order[:2], ["prepare", "pipeline"])

    def test_app_starts_scheduler_only_when_enabled(self):
        with TestClient(create_app(Settings(_env_file=None))) as client:
            self.assertIsNone(client.app.app.state.daily_pipeline)
        app = create_app(Settings(_env_file=None, scheduler_enabled=True))
        with TestClient(app) as client:
            daily = client.app.app.state.daily_pipeline
            self.assertIsNotNone(daily)
            self.assertIn("--no-load", daily.args)   # DB 주소 없음
            self.assertIn("--no-llm", daily.args)    # LLM 키 없음
        self.assertTrue(daily.stop.is_set())         # 종료 시 멈춤 (첫 실행 60초 전이라 파이프라인은 안 돎)


if __name__ == "__main__":
    unittest.main()
