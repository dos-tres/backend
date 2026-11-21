"""① 대신 제출(구글폼) 흐름 (docs/APPLY.md 3·9장).

start  : 신청서 목록에 있는 항목이면 폼을 읽어 기본 정보로 채운 문항과 물을 문항을 돌려준다. 마감·지원 안 되는 폼은 안내.
draft  : 긴 답 초안 (LLM). 이름·연락처는 LLM 에 보내지 않는다.
submit : 사용자가 [제출하기]를 눌렀을 때만. 답을 검증하고 구글폼에 제출한다.
서버는 아무것도 저장하지 않는다.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.apply import fill, gform
from app.catalog.repository import get_item
from app.chat.llm import ChatModel, LLMUnavailable
from app.checkin.summary import summarize

KST = timezone(timedelta(hours=9))
DRAFT_LIMIT = 300   # 문항에 글자 수 안내가 없을 때 초안 길이
DRAFT_SYSTEM = """너는 청년 지원 서비스 '둘셋'의 AI 비서 조이다. 사용자가 청년센터 프로그램 신청서의 한 문항에 쓸 답 초안을 대신 써 준다.

규칙
- 사용자 본인이 쓰는 1인칭 존댓말(~습니다/~어요 섞지 말고 ~습니다체)로 쓴다.
- 아래 '사용자에 대해 아는 것'과 '대화'에 있는 사실만 쓴다. 경험·자격·학력·숫자·기관 이름을 지어내지 않는다. 모르는 부분은 일반적인 기대·바람으로 쓴다.
- 이름·연락처·주소를 쓰지 않는다. 대화에 [이름]·[생년월일]·[연락처]·[이메일] 같은 자리 표시가 있으면 꼭 필요할 때만 그 표시를 그대로 쓰고, 실제 값을 짐작해 넣지 않는다.
- 문항이 묻는 것에만 답한다. {limit}자 이내, 2~4문장.
- 진단·위험 같은 말이나 상태 체크 점수를 그대로 쓰지 않는다.
JSON 으로만 답한다: {{"draft": "..."}}"""


class NotAvailable(Exception):
    pass


# FE 가 이름·생일·연락처·이메일을 이 표시로 바꿔 보내고, 초안을 받으면 기기 값으로 되돌린다 (docs/APPLY.md 9-6).
PLACEHOLDERS = ("[이름]", "[생년월일]", "[연락처]", "[이메일]")
_PHONE = re.compile(r"(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def mask(text: str) -> str:
    """FE 치환이 빠졌을 때의 안전망: 휴대폰 번호·이메일은 LLM 에 보내기 전에 서버에서도 가린다.
    이름은 서버가 알아볼 수 없으므로 FE 치환이 맡는다."""
    return _EMAIL.sub("[이메일]", _PHONE.sub("[연락처]", text))


def _item_info(session: Session | None, item_id: str, form: gform.Form | None) -> dict:
    row = get_item(session, item_id)
    if row:
        p = row["payload"]
        summary = p.get("summary") or p.get("plcyExplnCn") or ""
        return {"id": item_id, "title": row["title"], "summary": " ".join(summary.split())[:400],
                "official_url": _official_url(row)}
    return {"id": item_id, "title": form.title if form else item_id,
            "summary": " ".join((form.description or "").split())[:400] if form else "", "official_url": None}


def _official_url(row: dict) -> str | None:
    p = row["payload"]
    urls = (p.get("apply_urls") or p.get("aplyUrlAddr") or p.get("url") or p.get("refUrlAddr1") or "").split()
    return urls[0] if urls else None


def _question_json(q: gform.Question, prefill: str | None, can_draft: bool, fill_key: str | None = None) -> dict:
    out = {"id": q.id, "label": q.label, "kind": q.kind, "required": q.required,
           "prompt": fill.prompt_for(q, prefill, can_draft)}
    if fill_key:
        out["fill_key"] = fill_key   # FE 가 기기에 둔 값으로 채우고 확인만 받는다. 값이 없으면 prompt 로 묻는다
    if q.options:
        out["options"] = q.options
    if q.other:
        out["other"] = True
    if q.kind == "agree" and q.description:
        out["description"] = q.description
    elif q.hint:
        out["hint"] = q.hint
    if prefill:
        out["prefill"] = prefill
    if can_draft:
        out["can_draft"] = True
    return out


def start(session: Session | None, forms: dict[str, dict], item_id: str, applicant: dict | None,
          profile: dict | None, fetch=gform.fetch) -> dict:
    entry = forms.get(item_id)
    if entry is None:
        info = _item_info(session, item_id, None)
        return {"channel": None, "available": False, "reason": "not_supported",
                "item": {"id": item_id, "title": info["title"]},
                "official_url": info["official_url"],
                "replies": ["이건 조이가 대신 제출할 수 없어서, 공식 페이지에서 신청해야 해요."],
                "choices": []}
    try:
        form = fetch(entry["form_url"])
    except gform.FormClosed as exc:
        info = _item_info(session, item_id, None)
        replies = ["아쉽게도 이 신청은 마감됐어요."]
        if exc.message:
            replies.append(f"기관 안내로는 \"{exc.message}\"라고 해요. 비슷한 지원을 찾아볼까요?")
        else:
            replies.append("비슷한 지원을 찾아볼까요?")
        return {"channel": "form", "available": False, "reason": "closed",
                "item": {"id": item_id, "title": info["title"]}, "closed_message": exc.message,
                "official_url": info["official_url"], "replies": replies,
                "choices": [{"type": "message", "label": "비슷한 지원 찾기", "text": "비슷한 지원 찾아 줘"},
                            {"type": "message", "label": "다른 추천 보기", "text": "나한테 맞는 지원 추천해 줘"}]}
    except gform.FormError as exc:
        info = _item_info(session, item_id, None)
        text = ("지금 신청서를 열 수 없어요. 공식 페이지에서 확인해 주세요." if exc.reason == "unreachable"
                else "이 신청서는 조이가 대신 쓸 수 없는 형식이라, 공식 페이지에서 신청해야 해요.")
        return {"channel": "form", "available": False, "reason": exc.reason,
                "item": {"id": item_id, "title": info["title"]}, "official_url": info["official_url"],
                "replies": [text], "choices": []}

    info = _item_info(session, item_id, form)
    filled, ask = fill.split(form.questions, applicant, profile)
    replies = [f"「{info['title']}」 신청서를 같이 써 볼게요."]
    if filled:
        summary = " · ".join(f"{f['label'] if len(f['label']) <= 8 else _short_label(f['label'])} {f['value']}"
                             for f in filled)
        replies.append(f"알고 있는 정보로 채웠어요. {summary}")
    return {"channel": "form", "available": True,
            "item": {"id": item_id, "title": info["title"]},
            "filled": filled,
            "questions": [_question_json(a["question"], a["prefill"], a["can_draft"], a["fill_key"]) for a in ask],
            "replies": replies,
            "choices": ([{"type": "apply_confirm", "label": "맞아요"}, {"type": "apply_edit", "label": "고칠래요"}]
                        if filled else [])}


def _short_label(label: str) -> str:
    return re.sub(r"\s*\(.*?\)\s*", " ", label).strip()[:8]


def submit(session: Session | None, forms: dict[str, dict], item_id: str, answers: dict,
           fetch=gform.fetch, post=None) -> dict:
    entry = forms.get(item_id)
    if entry is None:
        raise NotAvailable(item_id)
    form = fetch(entry["form_url"])          # 마감·형식 변경이면 FormError
    if post is None:
        gform.submit(form, answers)          # InvalidAnswers / SubmitFailed
    else:
        gform.submit(form, answers, http=post)
    info = _item_info(session, item_id, form)
    return {"status": "submitted", "confirmed_by": "server",
            "submitted_at": datetime.now(KST).isoformat(timespec="seconds"),
            "item": {"id": item_id, "title": info["title"]},
            "replies": ["신청 완료됐어요!", "결과는 센터에서 연락이 올 거예요. 신청 기록에 남기고 일정도 넣어 둘까요?"],
            "choices": [{"type": "record", "label": "기록하고 일정 넣기"}, {"type": "message", "label": "괜찮아요",
                                                                      "text": "괜찮아요"}]}


def _limit_from(q: gform.Question) -> int:
    m = re.search(r"(\d{2,4})\s*자", f"{q.label} {q.hint or ''}")
    return min(int(m.group(1)), 1000) if m else DRAFT_LIMIT


def draft(session: Session | None, model: ChatModel | None, forms: dict[str, dict], item_id: str,
          question_id: str, messages: list[dict], profile: dict | None, checkin: dict,
          previous: str | None, fetch=gform.fetch, preview: bool = False) -> dict:
    """preview=True 면 LLM 을 부르지 않고, AI 에 보낼 글을 그대로 돌려준다 ('AI에 전달되는 내용 보기')."""
    entry = forms.get(item_id)
    if entry is None:
        raise NotAvailable(item_id)
    form = fetch(entry["form_url"])
    q = next((q for q in form.questions if q.id == question_id), None)
    if q is None or q.kind != "long":
        raise NotAvailable(question_id)
    if model is None and not preview:
        raise LLMUnavailable("not configured")
    info = _item_info(session, item_id, form)
    limit = _limit_from(q)
    known = []
    if profile:
        known.append(f"만 {profile['age']}세")
        if profile.get("job"):
            known.append(f"지금 하는 일: {profile['job']}")
        if profile.get("school"):
            known.append(f"학교: {profile['school']}")
    if checkin:
        s = summarize(checkin)
        if s.get("interests"):
            known.append("관심 분야: " + ", ".join(s["interests"]))
        if s.get("notes"):
            known.append("상태 체크에서 한 말: " + " / ".join(s["notes"][:4]))
    said = [mask(m["content"]) for m in messages if m.get("role") == "user"][-8:]
    user = "\n".join([
        f"프로그램: {info['title']}",
        f"프로그램 소개: {info['summary'] or '(없음)'}",
        f"문항: {q.label}" + (f" ({q.hint})" if q.hint else ""),
        "사용자에 대해 아는 것: " + ("; ".join(known) if known else "(거의 없음)"),
        "대화에서 사용자가 한 말: " + (" / ".join(said) if said else "(없음)"),
        *([f"이전 초안(다르게 다시 써 줘): {mask(previous)}"] if previous else []),
    ])
    if preview:
        return {"question_id": q.id, "ai_input": user}
    data = model.complete_json(DRAFT_SYSTEM.format(limit=limit), [{"role": "user", "content": user}])
    text = " ".join(str(data.get("draft") or "").split())
    if not text:
        raise LLMUnavailable("empty draft")
    text = text[:limit]
    return {"question_id": q.id, "draft": text,
            "placeholders": [p for p in PLACEHOLDERS if p in text],   # FE 가 기기 값으로 되돌릴 자리 표시
            "replies": ["이렇게 써 봤어요. 고칠 데 있으면 고쳐 주세요."],
            "choices": [{"type": "draft_accept", "label": "이대로"}, {"type": "draft_retry", "label": "다시 써 줘"},
                        {"type": "draft_edit", "label": "직접 고칠게요"}]}
