"""LLM 을 부르는 요청(대화·초안) 사용량 제한. 공개 주소라 비용을 막는다.

- 접속자(IP)마다 1분·하루 횟수, 서버 전체 하루 횟수. 0이면 그 제한은 끈다.
- 위기 표현 안내는 LLM 을 쓰지 않으므로 제한하지 않는다(대화 라우터에서 먼저 확인).
- 메모리에만 둔다(컨테이너 1개, 재시작하면 초기화). IP 는 로그에 남기지 않는다.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import date


class RateLimited(Exception):
    def __init__(self, retry_after: int, scope: str):
        super().__init__(scope)
        self.retry_after, self.scope = retry_after, scope


class UsageLimiter:
    def __init__(self, per_minute: int, per_day: int, total_per_day: int, clock=time.time, today=date.today):
        self.per_minute, self.per_day, self.total_per_day = per_minute, per_day, total_per_day
        self.clock, self.today = clock, today
        self.lock = threading.Lock()
        self.recent: dict[str, deque[float]] = {}
        self.daily: dict[str, int] = {}
        self.total = 0
        self.day = today()

    def hit(self, key: str) -> None:
        """한 번 쓴다. 넘으면 RateLimited (그때는 세지 않는다)."""
        with self.lock:
            now, today = self.clock(), self.today()
            if today != self.day:
                self.day, self.daily, self.total = today, {}, 0
            if self.total_per_day and self.total >= self.total_per_day:
                raise RateLimited(_seconds_to_midnight(), "total")
            if self.per_day and self.daily.get(key, 0) >= self.per_day:
                raise RateLimited(_seconds_to_midnight(), "day")
            window = self.recent.setdefault(key, deque())
            while window and now - window[0] >= 60:
                window.popleft()
            if self.per_minute and len(window) >= self.per_minute:
                raise RateLimited(max(1, int(60 - (now - window[0])) + 1), "minute")
            window.append(now)
            self.daily[key] = self.daily.get(key, 0) + 1
            self.total += 1
            if len(self.recent) > 10000:   # 오래된 접속자 정리
                for k in [k for k, w in self.recent.items() if not w or now - w[-1] >= 60]:
                    del self.recent[k]


def _seconds_to_midnight() -> int:
    now = time.localtime()
    return max(60, 86400 - (now.tm_hour * 3600 + now.tm_min * 60 + now.tm_sec))


def client_key(request) -> str:
    return request.client.host if request.client else "unknown"
