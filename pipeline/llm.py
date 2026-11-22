"""LLM 호출 공통과 분류 태그 정의 (정책·프로그램 분류가 같이 쓴다).

LLM: OpenAI 호환 chat/completions. 표준 라이브러리만 사용.
  OPENAI_API_KEY (예전 이름 GMS_KEY)  저장소 루트 .env
  OPENAI_BASE_URL (또는 LLM_BASE_URL)  없으면 https://api.openai.com/v1
  LLM_MODEL                         기본 gpt-4.1-mini
"""
from __future__ import annotations

import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request

from pipeline.paths import require_env

# 분류 태그 (docs/RECOMMENDATION.md 2장)
DOMAINS = ("E", "P", "O", "C", "U")   # 경제·모임 참여·외출·교류·도움(지원망)
SITUATIONS = ("임신·출산", "육아", "군인", "기혼", "미혼", "한부모가정", "장애인", "기초생활수급자",
              "자립준비청년", "가족돌봄청년", "농업인", "중소기업재직", "여성", "지역인재")
ACCESS_TYPES = ("apply", "visit", "none")
BATCH = 20


def llm_config():
    key = require_env("OPENAI_API_KEY", "LLM_API_KEY", "GMS_KEY")
    base = (os.environ.get("OPENAI_BASE_URL") or os.environ.get("LLM_BASE_URL")
            or "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("LLM_MODEL") or "gpt-4.1-mini"
    return key, base, model


def chat(key, base, model, system, user):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    req = urllib.request.Request(f"{base}/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    tries = 6
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"], data.get("usage", {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code in (401, 403, 404):
                sys.exit(f"LLM 호출 실패 {e.code}: {detail}\n키·LLM_BASE_URL·LLM_MODEL 을 확인하세요.")
            if attempt == tries - 1:
                raise RuntimeError(f"LLM 호출 실패 {e.code}: {detail}")
            err = f"HTTP {e.code}"
        except (OSError, http.client.HTTPException) as e:
            # URLError, 타임아웃, ConnectionResetError(10054), RemoteDisconnected, IncompleteRead 등
            if attempt == tries - 1:
                raise RuntimeError(f"LLM 연결 실패: {e!r}")
            err = repr(e)
        wait = min(5 * 2 ** attempt, 60)
        print(f"    연결 오류 {err} → {wait}초 후 재시도 ({attempt + 1}/{tries - 1})")
        time.sleep(wait)


def status_of(e):
    if e.get("access_type") == "none":
        return "excluded"
    if not e.get("access_type") or not e.get("i5_domains") or e.get("confidence") != "high":
        return "hold"
    return "ok"
