"""구글폼 읽기·제출 (docs/APPLY.md 3·11장).

읽기: 폼 페이지(viewform)에 들어 있는 FB_PUBLIC_LOAD_DATA_ 값에서 문항·문항 번호·필수 여부·선택지·작성 안내를 꺼낸다.
구글 공개 API 가 아니라 페이지 값이라 형식이 바뀌면 FormUnreachable 로 알린다(테스트로 형식 확인).
제출: 공개 제출 주소(formResponse)에 entry.{문항 번호}=답. 사용자가 [제출하기]를 눌렀을 때만 호출된다.
신청자 정보는 저장하거나 로그에 남기지 않는다.
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)
UA = "Mozilla/5.0 (compatible; dostres-apply/0.1)"
TIMEOUT = 10
FORM_URL_RE = re.compile(r"^https://docs\.google\.com/forms/d/e/([A-Za-z0-9_-]+)/(?:viewform|formResponse|closedform)")
DATA_RE = re.compile(r"FB_PUBLIC_LOAD_DATA_ = (.*?);</script>", re.S)
FBZX_RE = re.compile(r'name="fbzx" value="([^"]+)"')
FORM_AGAIN_RE = re.compile(r'<form[^>]*action="[^"]*/formResponse"')
HIDDEN_RE = re.compile(r'<input type="hidden" name="([^"]+)" value="([^"]*)"')
OTHER = "__other_option__"

# 구글폼 문항 종류 번호 → 우리 kind. 없는 번호는 지원하지 않는 문항
KINDS = {0: "short", 1: "long", 2: "choice", 3: "choice", 4: "multi", 9: "date"}
DISPLAY_ONLY = {6, 11, 12}          # 설명 글·이미지·동영상: 답할 것이 없다
PAGE_BREAK = 8                      # 여러 페이지 폼은 MVP 에서 다루지 않는다


class FormError(Exception):
    reason = "unreachable"


class FormClosed(FormError):
    reason = "closed"

    def __init__(self, message: str | None = None):
        super().__init__("closed")
        self.message = message


class FormNotSupported(FormError):
    reason = "not_supported"


class FormUnreachable(FormError):
    reason = "unreachable"


class SubmitFailed(Exception):
    pass


@dataclass
class Question:
    id: str                  # 우리 쪽 id (q1, q2 …). FE 는 이 값으로 답을 보낸다
    entry: int               # 구글폼 문항 번호 (entry.N)
    label: str
    description: str | None
    kind: str                # short / long / choice / multi / date / agree
    required: bool
    options: list[str] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)
    other: bool = False      # 선택지에 '기타(직접 입력)'가 있다
    hint: str | None = None  # 작성 안내 (폼의 설명·검증 안내)


@dataclass
class Form:
    title: str
    description: str | None
    questions: list[Question]
    submit_url: str
    fbzx: str | None
    hidden: list[tuple[str, str]] = field(default_factory=list)   # 브라우저가 같이 보내는 값 (partialResponse 등)


def _closed_message(page: str) -> str | None:
    """마감 화면의 기관 문구. 첫 번째 글은 폼 제목, 두 번째가 마감 문구다."""
    texts = [html_lib.unescape(t).strip() for t in re.findall(r"<div[^>]*>([^<]{5,500})</div>", page)]
    texts = [t for t in texts if t]
    return texts[1] if len(texts) > 1 else None


def parse(page: str, final_url: str, *, read_only: bool = False) -> Form:
    if "accounts.google.com" in final_url:
        raise FormNotSupported("login required")
    if "/closedform" in final_url:
        raise FormClosed(_closed_message(page))
    match = DATA_RE.search(page)
    m_url = FORM_URL_RE.match(final_url)
    if not match or not m_url:
        raise FormUnreachable("no form data")
    try:
        data = json.loads(match.group(1))
        info = data[1]
        items = info[1] or []
        title = info[8] or data[3] or ""
        description = info[0]
    except (ValueError, IndexError, TypeError) as exc:
        raise FormUnreachable("unexpected form data") from exc

    questions: list[Question] = []
    for item in items:
        try:
            typ, label, desc = item[3], (item[1] or "").strip(), item[2]
        except (IndexError, TypeError) as exc:
            raise FormUnreachable("unexpected item") from exc
        if typ in DISPLAY_ONLY:
            continue
        if typ == PAGE_BREAK and read_only:
            continue
        if typ == PAGE_BREAK:
            raise FormNotSupported("multiple pages")
        if typ not in KINDS and typ != 7:
            raise FormNotSupported(f"question type {typ}")
        entries = item[4] or []
        if typ == 7:
            if not entries or not all(len(e)>11 and e[11] == [1] for e in entries):
                raise FormNotSupported("radio grid")
            question_id = f"q{len(questions)+1}"
            try:
                options = [o[0] for o in entries[0][1] if o and o[0]]
                if any([o[0] for o in e[1] if o and o[0]] != options for e in entries):
                    raise FormNotSupported("different grid columns")
                rows = [{"id":f"{question_id}r{n+1}", "label":e[3][0],
                         "entry":int(e[0]), "required":bool(e[2])} for n,e in enumerate(entries)]
            except (IndexError, TypeError, ValueError) as exc:
                raise FormUnreachable("unexpected grid") from exc
            questions.append(Question(
                id=question_id, entry=int(entries[0][0]), label=label, description=desc,
                kind="multi_grid", required=any(row["required"] for row in rows),
                options=options, rows=rows,
            ))
            continue
        if len(entries) != 1:
            raise FormNotSupported("grid question")
        entry = entries[0]
        raw_options = entry[1] or []
        options = [o[0] for o in raw_options if o and o[0]]
        other = any(len(o) > 4 and o[4] == 1 for o in raw_options if o)
        hints = [desc] if desc else []
        validation = entry[4] if len(entry) > 4 and entry[4] else []
        hints += [v[3] for v in validation if len(v) > 3 and v[3]]
        kind = KINDS[typ]
        if kind == "choice" and "동의" in label:
            kind = "agree"   # 동의 문항은 대신 답하지 않는다 (fill.py)
        questions.append(Question(
            id=f"q{len(questions) + 1}", entry=int(entry[0]), label=label, description=desc, kind=kind,
            required=bool(entry[2]), options=options, other=other,
            hint=" / ".join(dict.fromkeys(h.strip() for h in hints if h.strip())) or None,
        ))
    fbzx = FBZX_RE.search(page)
    # 브라우저가 제출 때 함께 보내는 숨은 값. 브라우저와 같은 요청이 되도록 그대로 같이 보낸다
    hidden = [(n, html_lib.unescape(v)) for n, v in HIDDEN_RE.findall(page) if not n.startswith("entry.")]
    submit_url = f"https://docs.google.com/forms/d/e/{m_url.group(1)}/formResponse"
    return Form(title=title, description=description, questions=questions, submit_url=submit_url,
                fbzx=fbzx.group(1) if fbzx else None, hidden=hidden)


def fetch(url: str, http=requests, *, read_only: bool = False) -> Form:
    try:
        res = http.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as exc:
        logger.warning("form fetch failed: %s", type(exc).__name__)
        raise FormUnreachable(type(exc).__name__) from exc
    if res.status_code != 200:
        raise FormUnreachable(f"HTTP {res.status_code}")
    return parse(res.text, res.url, read_only=read_only)


class InvalidAnswers(ValueError):
    def __init__(self, missing: list[str], invalid: list[str]):
        super().__init__("invalid answers")
        self.missing, self.invalid = missing, invalid


def build_payload(form: Form, answers: dict[str, str | list[str]]) -> list[tuple[str, str]]:
    """문항 id → 답 을 구글폼 제출 형식으로. 필수 답 없음·선택지 밖 값이면 InvalidAnswers."""
    payload: list[tuple[str, str]] = []
    missing, invalid = [], []
    for q in form.questions:
        if q.kind == "multi_grid":
            for row in q.rows:
                value = answers.get(row["id"], [])
                values = value if isinstance(value, list) else [value]
                values = [v.strip() for v in values if isinstance(v,str) and v.strip()]
                if not values and row["required"]: missing.append(row["id"])
                if any(v not in q.options for v in values): invalid.append(row["id"])
                payload.extend((f"entry.{row['entry']}",v) for v in values if v in q.options)
            continue
        value = answers.get(q.id)
        values = [v.strip() for v in (value if isinstance(value, list) else [value]) if isinstance(v, str) and v.strip()]
        if not values:
            if q.required:
                missing.append(q.id)
            continue
        key = f"entry.{q.entry}"
        if q.kind in ("choice", "agree", "multi"):
            if q.kind != "multi" and len(values) > 1:
                invalid.append(q.id)
                continue
            for v in values:
                if v in q.options:
                    payload.append((key, v))
                elif q.other:
                    payload.append((key, OTHER))
                    payload.append((f"{key}.other_option_response", v))
                else:
                    invalid.append(q.id)
        elif q.kind == "date":
            m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", values[0])
            if not m:
                invalid.append(q.id)
                continue
            payload += [(f"{key}_year", m.group(1)), (f"{key}_month", m.group(2)), (f"{key}_day", m.group(3))]
        else:
            if len(values) > 1:
                invalid.append(q.id)
                continue
            payload.append((key, values[0]))
    if missing or invalid:
        raise InvalidAnswers(missing, sorted(set(invalid)))
    return payload


def submit(form: Form, answers: dict[str, str | list[str]], http=requests) -> None:
    """제출. 실패하면 SubmitFailed. 답 검증 실패는 InvalidAnswers (제출하지 않음)."""
    payload = build_payload(form, answers)
    sent = {k for k, _ in form.hidden}
    payload += form.hidden
    payload += [(k, v) for k, v in (("fvv", "1"), ("pageHistory", "0")) if k not in sent]
    if form.fbzx and "fbzx" not in sent:
        payload.append(("fbzx", form.fbzx))
    for q in form.questions:   # 선택 문항 표시값 (브라우저와 같게)
        if q.kind == "multi_grid":
            payload.extend((f"entry.{row['entry']}_sentinel", "") for row in q.rows)
        elif q.kind in ("choice", "agree", "multi"):
            payload.append((f"entry.{q.entry}_sentinel", ""))
    try:
        res = http.post(form.submit_url, data=payload, headers={"User-Agent": UA}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        logger.warning("form submit failed: %s", type(exc).__name__)
        raise SubmitFailed(type(exc).__name__) from exc
    if res.status_code != 200:
        logger.warning("form submit HTTP %s", res.status_code)
        raise SubmitFailed(f"HTTP {res.status_code}")
    if FORM_AGAIN_RE.search(res.text or ""):
        # 접수 완료 화면('다른 응답 제출', usp=form_confirm)이 아니라 입력 폼이 다시 나왔다 = 기록되지 않음
        logger.warning("form submit returned the form again")
        raise SubmitFailed("form returned again")


def fetch_source(url: str) -> Form:
    """공개 원본을 읽기만 한다. 여러 페이지를 제출 대상으로 사용하지 않는다."""
    return fetch(url, read_only=True)
