"""대화용 LLM 클라이언트 (OpenAI 호환 chat/completions, 예: SSAFY GMS).

파이프라인용(pipeline/llm.py)과 따로 둔다. 웹 요청 안에서 쓰므로 전체 시간 제한(재시도 포함)을 두고, 재시도는 1번만 하고,
실패하면 예외로 알린다(예시 답변으로 대신하지 않는다 — docs/DEPLOYMENT.md 5장).
키·대화 내용은 로그에 남기지 않는다.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Protocol

import requests

logger = logging.getLogger(__name__)
MIN_ATTEMPT_SECONDS = 2.0   # 남은 시간이 이보다 적으면 다시 시도하지 않는다


class LLMUnavailable(Exception):
    """설정 없음·시간 초과·HTTP 오류·응답 형식 오류."""


class ChatModel(Protocol):
    def complete_json(self, system: str, messages: list[dict]) -> dict: ...


class OpenAICompatible:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 20.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete_json(self, system: str, messages: list[dict]) -> dict:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, *messages],
            "temperature": 0,   # 같은 말에서 같은 답을 뽑게 (0.3 에서는 '학교도 일도 안 해요' 추출이 회차마다 달랐다)
            "response_format": {"type": "json_object"},
        }
        # timeout 은 재시도까지 합친 전체 시간이다 (점검: 시도마다 20초를 주면 최악 40초가 걸렸다)
        deadline = time.monotonic() + self.timeout
        last_error = "unknown"
        for attempt in range(2):   # 첫 시도는 항상, 일시 오류면 남은 시간이 있을 때만 한 번 더
            remaining = deadline - time.monotonic()
            if attempt and remaining < MIN_ATTEMPT_SECONDS:
                last_error = "time budget exhausted"
                break
            remaining = max(remaining, 0.1)
            try:
                response = requests.post(f"{self.base_url}/chat/completions", json=body, timeout=remaining,
                                         headers={"Authorization": f"Bearer {self.api_key}"})
            except requests.Timeout:
                last_error = "Timeout"
                break   # 시간을 다 썼으므로 다시 시도하지 않는다
            except requests.RequestException as exc:
                last_error = type(exc).__name__
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {response.status_code}"
                continue
            if response.status_code != 200:
                logger.warning("chat LLM HTTP %s", response.status_code)
                raise LLMUnavailable(f"HTTP {response.status_code}")
            try:
                content = response.json()["choices"][0]["message"]["content"]
                data = json.loads(content)
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                raise LLMUnavailable("invalid response") from exc
            if not isinstance(data, dict):
                raise LLMUnavailable("invalid response")
            return data
        logger.warning("chat LLM unavailable: %s", last_error)
        raise LLMUnavailable(last_error)
