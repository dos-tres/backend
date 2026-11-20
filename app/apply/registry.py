"""신청서 목록: 챗봇이 대신 제출할 수 있는 항목 → 테스트 구글폼 주소 (docs/APPLY.md 11장).

파일은 Git 에 올리지 않는다(`*.local.json`). 경로는 .env 의 APPLY_FORMS_PATH. 없으면 신청 가능한 항목이 없다.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load(path: str | None) -> dict[str, dict]:
    if not path:
        return {}
    file = Path(path)
    if not file.exists():
        logger.warning("apply forms file not found")
        return {}
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except ValueError:
        logger.warning("apply forms file is not valid JSON")
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict) and v.get("form_url")}


def mark(results: dict | None, forms: dict[str, dict]) -> dict | None:
    """추천·검색 결과 항목에 apply_channel 표시. 지금은 신청서 목록에 있으면 'form', 아니면 None
    (②③④ 갈래 판단은 아직 — docs/APPLY.md 2-1). FE 는 'form' 이면 카드에 [신청하기]를 띄운다."""
    if not results:
        return results
    for key in ("policies", "programs"):
        for item in results.get(key) or []:
            item["apply_channel"] = "form" if item.get("id") in forms else None
    return results
