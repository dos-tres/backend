# 프론트엔드 연결 안내

FE가 백엔드 API를 붙일 때 이 문서 하나만 보면 되도록 정리했다. 2026-11-21 `main`(9e707e0) 기준, 응답 예시는 실행 중인 서버에서 실제로 받은 값이다(긴 글은 줄임).

자세한 설계가 필요하면: 추천 [RECOMMENDATION.md](RECOMMENDATION.md) · 지역 [REGIONS.md](REGIONS.md) · 대화 [CHAT.md](CHAT.md) · 신청 [APPLY.md](APPLY.md) · 서버를 띄우면 `http://127.0.0.1:8000/docs`(자동 API 문서)

## 0. 한눈에

| API | 지금 동작 | FE 화면 |
| --- | --- | --- |
| `GET /api/regions` | ✅ | 지역 선택 (선택: 백엔드가 받는 코드 목록) |
| `GET /api/checkin/questions` | ✅ | 생활 점검 문항 (이미 연결됨) |
| `POST /api/checkin/summary` | ✅ | 생활 점검 결과 (이미 연결됨) |
| `POST /api/recommendations` | ✅ DB | 추천 카드 (이미 연결됨) — **새 필드 `apply_channel`** |
| `POST /api/chat` | ⚠️ **지금 503** (LLM 키 없음). 위기 안내만 동작 | AI 비서 대화 (아직 예시 응답) |
| `POST /api/apply/start` | ✅ | 신청 시작 (새로 연결) |
| `POST /api/apply/draft` | ⚠️ 503 (LLM 키 없음) | 긴 답 초안 |
| `POST /api/apply/submit` | ✅ (테스트 폼 실제 제출 확인) | 신청 제출 |
| 저장(프로필·관심·일정·신청 기록·대화) | ❌ 없음 | **FE 로컬 저장** (로그인 없는 MVP) |
| 센터 목록·상세 | ❌ 없음 | 예시 데이터 유지 |

## 1. 로컬에서 같이 돌리기

백엔드 (`backend/`, Windows PowerShell 기준)

```
docker compose up -d --wait db                 # 개발 DB (Docker Desktop 켜 두기)
.venv\Scripts\python -m alembic upgrade head    # 처음 한 번
.venv\Scripts\python -m pipeline.load_catalog --seed   # 정책 2,335 · 프로그램 137 적재 (처음 한 번)
.venv\Scripts\python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- `.env`는 `.env.example`을 복사해서 `DATABASE_URL`만 채우면 추천까지 된다. DB 없이 띄워도 추천은 파일 데이터로 동작한다(응답 `source: "file"`).
- 챗봇 신청 테스트 폼을 쓰려면 `APPLY_FORMS_PATH=apply_forms.local.json`과 그 파일이 필요하다(**Git에 없음**, 백엔드 담당에게 따로 받기).

프론트 (`frontend/`): `npm run dev` → `http://127.0.0.1:5173`. `vite.config.ts`가 `/api`를 `127.0.0.1:8000`으로 넘겨 주므로 따로 설정할 것 없다. 프록시 없이 직접 부르면(`VITE_API_BASE_URL`) 백엔드가 `http://localhost:5173`, `http://127.0.0.1:5173`만 허용한다(CORS, `.env`의 `ALLOWED_ORIGINS`로 추가).

## 2. 공통 규칙

- 모든 경로는 `/api/...`, 요청·응답 JSON(UTF-8).
- **서버는 아무것도 저장하지 않는다.** 대화·답·신청 정보는 매 요청에 FE가 보낸다. 서버는 로그에도 남기지 않는다.
- 오류 형식은 하나: `{"error": {"code": "...", "message": "..."}}`

| 상태 | code | 언제 | FE 처리 |
| --- | --- | --- | --- |
| 422 | `VALIDATION_ERROR` | 필드 형식이 틀림(나이 범위, 코드 자리수, 빈 메시지 등) | 개발 중 버그. 사용자에게는 "다시 시도" |
| 422 | `HTTP_422` + `Unknown sigungu_cd` | 백엔드가 모르는 지역 코드 (5장) | 시·군·구를 다시 고르게 하기 |
| 422 | `HTTP_422` + `Invalid check-in answers` | 없는 문항 id·선택지 code | 개발 중 버그 |
| 503 | `AI_UNAVAILABLE` | LLM 없음·실패 (대화·초안) | "AI 연결이 안 돼요. 잠시 뒤 다시 시도해 주세요" — **예시 답으로 대신하지 않기** |
| 404/409/422/502 | `APPLY_*` | 신청 (4-5) | 4-5 표 |
| 500 | `INTERNAL_SERVER_ERROR` | 서버 오류 | "다시 시도" |

## 3. 화면별 흐름

```text
첫 시작/내 정보 ── (FE 로컬 저장) ─────────────────────────────┐
생활 점검 ── GET /api/checkin/questions → POST /api/checkin/summary   │ profile + checkin
추천 화면 ── POST /api/recommendations ◀──────────────────────────────┘
   └ 카드 apply_channel == "form" → [신청하기] → 신청 흐름
AI 비서 ── POST /api/chat (매번 전체 대화 + profile + checkin)
   └ choices.type == "apply" → 신청 흐름 (아직 대화에서 안 나옴)
신청 흐름 ── POST /api/apply/start → (긴 답) /api/apply/draft → POST /api/apply/submit
   └ 성공 → FE 신청 기록·일정 저장 (confirmed_by: "server")
```

## 4. API

### 4-1. `GET /api/regions`

```json
{"regions": [{"code": "11110", "sido": "서울특별시", "sigungu": "종로구", "label": "서울특별시 종로구"}, "... 256개"]}
```

### 4-2. `GET /api/checkin/questions` (이미 연결됨)

```json
{
  "notice": "서비스 자체 상태 체크예요. 진단이 아니고, 답하지 않아도 돼요. 언제든 다시 바꿀 수 있어요.",
  "common_options": [{"code": "unknown", "label": "모르겠어요"}, {"code": "skip", "label": "답하지 않을래요"}, {"code": "later", "label": "나중에 할게요"}],
  "domain_questions": [{"id": "economy", "domain": "E", "text": "요즘 생활비나 취업 준비 비용이 얼마나 부담돼요?",
                        "options": [{"code": "high", "label": "많이 부담돼요"}, {"code": "mid", "label": "조금 부담돼요"}, {"code": "low", "label": "괜찮아요"}]}, "..."],
  "extra_questions": ["satisfaction", "change_wishes", "face_to_face", "interests(최대 3)"]
}
```

문항 id와 받는 code

| id | code |
| --- | --- |
| `economy`, `participation`, `outing`, `conversation`, `support`, `face_to_face` | `high`(도움 더 필요) / `mid` / `low`(괜찮음) + 공통 `unknown`·`skip`·`later` |
| `satisfaction` | `good` / `normal` / `bad` |
| `change_wishes` (여러 개) | `E` `P` `O` `C` `U` 또는 `none` |
| `interests` (최대 3) | `일자리·취업` `창업` `집·주거` `생활비·금융` `교육·자격증` `마음건강·상담` `몸 건강·식사` `문화·여가` `사람 만나기·모임` `해외 경험` |

### 4-3. `POST /api/checkin/summary` (이미 연결됨)

요청 `{"answers": {"economy": "high", "outing": "mid", "conversation": "high", "interests": ["일자리·취업"]}}`

```json
{"levels": {"E": "high", "O": "mid", "C": "high"}, "priority_domains": ["E", "C", "O"], "unanswered_domains": ["P", "U"],
 "interests": ["일자리·취업"], "notes": ["경제: 도움이 더 필요해 보여요", "교류: 도움이 더 필요해 보여요", "외출: 조금 신경 쓰여요"],
 "disclaimer": "서비스 자체 상태 체크 결과예요. 진단이나 위험 등급이 아니에요.", "...": "lowered_domains, change_wishes, face_to_face, satisfaction"}
```

### 4-4. `POST /api/recommendations` (이미 연결됨)

요청

```json
{"profile": {"age": 24, "sex": "여", "sigungu_cd": "11620", "job": "구직 중", "school": null, "situations": []},
 "checkin": {"economy": "high", "outing": "mid", "conversation": "high", "interests": ["일자리·취업"]}}
```

| profile 필드 | 값 |
| --- | --- |
| `age` (필수) | 만 나이 0~120 |
| `sigungu_cd` (필수) | 5자리, 백엔드 목록 256개 중 하나 (5장) |
| `sex` | `남` / `여` / null |
| `job` | `구직 중` `회사원` `아르바이트·단기` `프리랜서` `창업·자영업` `농어업` `학생` `쉬는 중` / null |
| `school` | `고등학생` `대학생` `대학원생` / null |
| `situations` | `임신·출산` `육아` `군인` `기혼` `미혼` `한부모가정` `장애인` `기초생활수급자` `자립준비청년` `가족돌봄청년` `농업인` `중소기업재직` `지역인재` |

응답: `summary`(4-3과 같음), `policies`(최대 6), `programs`(최대 4), `programs_notice`, `candidates`, `source`(`db`/`file`), `notice`

```json
{"id": "policy:20261018005400213991", "kind": "policy", "title": "2026 서울형 청년인턴 직무캠프",
 "why": ["생활비·취업 준비 부담이 크다고 했어요", "관심 분야: 일자리·취업"], "score": 43.0, "domains": ["E"],
 "access_type": "apply", "deadline": "2026-12-31", "scope": "광역",
 "summary": "사전직무교육 ✚ 인턴십(4개월) …", "support": "…", "institution": "서울특별시 미래청년기획관 청년정책담당관",
 "apply_period": "20260301 ~ 20261231", "apply_url": "https://…", "reference_url": "https://…",
 "income_condition": null, "apply_channel": null}
```

```json
{"id": "program:orang:75113", "kind": "program", "title": "서울청년센터 관악 신림동쓰리룸 <2026년 11월 1차 청년성장프로젝트> …",
 "why": ["…", "관심 분야: 일자리·취업", "우리 동네 청년센터"], "scope": "시군구", "deadline": null,
 "summary": "…(최대 200자)", "center": "서울청년센터 관악", "place": "…", "apply_period": "상시",
 "url": "https://…", "apply_urls": "https://forms.gle/…", "evergreen": false, "apply_channel": null}
```

- `why`: 카드에 그대로 보여 줄 추천 이유.
- `income_condition`: 소득 조건이 있으면 `{"kind", "max_manwon", "text"}` → 카드에 표시.
- `evergreen: true`: 오래된 상시 글 → "이용 전 센터에 확인" 표시.
- `programs_notice`: 프로그램이 0개일 때 이유 `{"code": "no_program_data" | "no_program_match", "message"}` → 그대로 안내.
- **`apply_channel`** (새로): `"form"`이면 [신청하기] → 4-6. `null`이면 지금처럼 공식 링크(`apply_url` / `apply_urls` / `url`).

### 4-5. `POST /api/chat` — ⚠️ 지금 503

요청 `{"messages": [{"role": "user", "content": "월세 지원 있어요?"}], "profile": {...4-4와 같음, 없어도 됨}, "checkin": {...}}`

- `messages`: 지금까지 대화 전체(최대 40개, 각 1,000자, 마지막은 `user`). 조이 말풍선 여러 개는 하나의 `assistant` 메시지로 이어 붙여 보낸다.
- 응답: `mode`, `replies`(말풍선 목록, 순서대로), `choices`(버튼), `results`(4-4와 같은 카드), `checkin`(다음 요청에 그대로), `checkin_update`, `needs`(`["profile"]`이면 나이·지역 입력 칸), `safety`.
- `choices[].type`: `message` → `text`를 사용자 메시지로 보냄 / `answer` → `checkin[question_id] = code` 넣고 `label`을 사용자 메시지로 보냄.
- **지금은 LLM 키가 없어 `503 AI_UNAVAILABLE`**. 화면은 붙여 두고 오류 안내만 보여 주면, 키가 생기는 대로 동작한다.
- **위기 표현**("죽고 싶어요" 등)은 키 없이도 200: `mode: "crisis"`, `safety.resources`(109·1577-0199·1388·112/119) → 연락처를 눈에 띄게 보여 주기.

```json
{"mode": "crisis", "replies": ["많이 힘들었겠어요. 말해 줘서 고마워요.", "지금 마음이 많이 위태롭다면 … 109 …", "원하면 상담이나 마음건강 지원도 같이 찾아볼게요."],
 "safety": {"level": "crisis", "resources": [{"name": "자살예방상담전화", "contact": "109", "hours": "24시간", "note": "전화·문자 상담"}, "…"]},
 "choices": [{"type": "message", "label": "상담·마음건강 지원 찾아보기", "text": "심리상담이나 마음건강 지원을 찾아줘"}, "…"],
 "results": null, "needs": [], "checkin": {}, "checkin_update": {}}
```

자세히: [CHAT.md](CHAT.md) 4~5장

### 4-6. 신청 `POST /api/apply/start` · `draft` · `submit`

실제 응답 예시·필드 설명은 [APPLY.md](APPLY.md) **9-5장**. 흐름만 요약:

1. `start` `{"item_id", "applicant": {"name", "birth_date": "YYYY-MM-DD", "phone", "email"}, "profile"}`
   - `available: true` → `replies` 보여 주고, `filled`(채운 값) 확인 [맞아요]/[고칠래요] → `questions`를 **하나씩** 말풍선(`prompt`)으로 묻기
     - `kind`: `short`·`long`(입력 칸, `prefill` 있으면 미리 채우기, `hint` 아래에) / `choice`·`multi`(버튼, `other: true`면 '기타' 입력) / `agree`(`description` 원문을 보여 주고 사용자가 직접 고름) / `date`
     - `required: false`면 건너뛰기 가능, `can_draft: true`면 [초안 써 줘요] → `draft`
   - `available: false` → `reason`: `closed`(마감, `closed_message`) / `not_supported`·`unreachable`(공식 링크 `official_url`) — `replies`·`choices` 그대로 보여 주기
2. `draft` `{"item_id", "question_id", "messages", "profile", "checkin", "previous"}` → `draft` 를 입력 칸에. 지금 503.
3. 마지막에 답 요약 → **사용자가 [제출하기]를 눌렀을 때만** `submit` `{"item_id", "applicant", "answers": {"q1": "...", ...}}`
   - `answers` = `filled` 값(고친 값) + `questions` 답. `multi`는 배열.
   - 성공 `{"status": "submitted", "confirmed_by": "server", "submitted_at", "replies", "choices"}` → 신청 기록·일정 저장(로컬)

| 오류 | FE |
| --- | --- |
| 422 `APPLY_INVALID` (`missing`, `invalid` 문항 id) | 그 문항으로 돌아가 다시 묻기 (제출 안 됨) |
| 409 `APPLY_FORM_CLOSED` | 마감 안내 |
| 404 `APPLY_NOT_AVAILABLE` | 공식 링크 안내 |
| 502 `APPLY_SUBMIT_FAILED` | "제출이 안 됐어요" + [다시 제출] |

시연용 `item_id`: `demo:open`(신청 가능 테스트 폼), `demo:closed`(마감 테스트 폼). 추천 카드에는 아직 `apply_channel: "form"`이 붙은 실제 항목이 없다(연결할 프로그램을 정하면 생김) → 시연 화면에서는 `demo:open`으로 시작 버튼을 하나 두면 된다.

## 5. FE와 백엔드가 맞춰야 하는 값 (FE main b65dd42 코드 확인)

✅ FE가 이미 맞게 바꿔 보냄 · ⚠️ 동작은 하지만 알아 둘 것 · ❌ 맞춰야 함

| # | 항목 | FE 화면 | 백엔드가 받는 값 | 상태 |
| --- | --- | --- | --- | --- |
| 1 | 생활 점검 5단계 (`economy`·`outing`·`conversation`·`face_to_face`) | 5개 보기 | `high` / `mid` / `low` (1·2번째 → 한쪽 끝, 3번째 → `mid`, 4·5번째 → 반대쪽 끝) | ✅ `checkin-scale.ts`. 단 "드물게"와 "거의 안"이 같은 `high`가 되므로 추천 이유 문구는 둘 다에 맞게 "잘 안 나간다"로 씀 |
| 2 | 만족도 `satisfaction` 5단계 | 5개 보기 | `bad` / `normal` / `good` | ✅ |
| 3 | 예/아니오 (`participation`·`support`) | 예 / 아니오 | 예 → `low`, 아니오 → `high` (백엔드의 `mid` "가끔 있어요"·"잘 모르겠어요"는 FE에서 안 씀) | ✅ |
| 4 | 관심 분야 (맞춤 설정) | 8개: 취업·진로, 주거, 생활·금융, 교육·자격증, 창업, 건강·마음, 문화·여가, 지역 활동 | 10개 (4-2 표) | ✅ `profile-context.ts`에서 변환 (건강·마음 → 마음건강·상담, 지역 활동 → 사람 만나기·모임). ⚠️ FE 맞춤 설정에는 '몸 건강·식사'·'해외 경험'이 없음 (생활 점검 9번 문항에서는 10개 그대로 고를 수 있음) |
| 5 | 관심 분야를 어디서 가져오나 | 맞춤 설정 / 생활 점검 중 최근 것 | `checkin.interests` 하나만 봄 | ✅ FE가 골라서 넣음 (백엔드는 출처를 모름) |
| 6 | 현재 상태 → `job` | 구직 중 · 재직 중 · 재학 중 · 아르바이트·단기 · 프리랜서 · 창업·자영업 · 쉬고 있어요 | 구직 중 · 회사원 · 학생 · 아르바이트·단기 · 프리랜서 · 창업·자영업 · 쉬는 중 · 농어업 | ✅ `policy-api.ts`에서 변환. FE에는 농어업 없음 |
| 7 | 학교 `school` | 고등학생 · 대학생 · 대학원생 | 같음 | ✅ |
| 8 | 나이 | 생년월일 | 만 나이 `age` | ✅ FE가 계산 |
| 9 | **지역 `sigungu_cd`** | 공식 법정동 사전 시군구 269개 | 256개 | ❌ 13개 '시 전체' 코드 → 422 (아래) |
| 10 | 성별 `sex` | **입력 칸 없음** | `남`/`여`/null | ⚠️ 없으면 여성 대상 정책은 추천에서 빠지고, 신청서의 성별 문항은 조이가 따로 물음. 넣으려면 FE 내 정보에 선택 칸 추가 |
| 11 | 상황 `situations` (한부모·장애인·기초생활수급자·자립준비청년 등) | 입력 칸 없음 | 13개 값 (4-4) | ⚠️ 없으면 그 상황 전용 정책은 빠짐(안전한 쪽). 시연에는 없어도 됨 |
| 12 | 신청자 정보 `applicant` | 이름(최대 50자) · 생년월일 · 휴대전화 · 이메일 | 이름 최대 30자 · `birth_date` YYYY-MM-DD · 휴대전화 · 이메일 | ⚠️ 이름 30자 넘으면 422. 휴대전화는 `010-0000-0000` 형식으로 보내기 (신청서 검증과 맞춤) |
| 13 | 대화 기록 `messages` | 화면의 전체 대화 | 최대 40개, 각 1,000자, 마지막은 user | ⚠️ 길어지면 최근 40개만 보내기 |
| 14 | 대화 `checkin` | — | 응답의 `checkin`을 다음 요청에 그대로 | ⚠️ 대화에서 알아들은 답(`checkin_update`)을 생활 점검 기록에 합칠지 FE가 정함 |

**지역 코드 13개**: 구가 있는 시의 '시 전체' 코드 — 수원시 41110, 성남시 41130, 안양시 41170, 부천시 41190, 안산시 41270, 고양시 41280, 용인시 41460, 화성시 41590, 청주시 43110, 천안시 44130, 포항시 47110, 창원시 48120, 전주시 52110. 지금은 FE가 이 코드를 그대로 보내고(`policy-api.ts`: 5자리면 추천 API 호출) 백엔드가 422를 돌려준다. 나머지 256개는 그대로 일치한다.

## 6. 아직 없는 것 (FE가 기다릴 필요 없음)

- 사용자 저장 API(프로필·관심·일정·신청 기록·대화) — MVP는 FE 로컬. 회원 테이블은 확장용 설계만 있음.
- 센터 목록·상세 API — 예시 화면 유지.
- 대화의 신청 버튼(`choices.type: "apply"`), 신청 ②③④(온라인 사이트·전화·방문) — 백엔드 작업 중. 지금은 `apply_channel: null`이면 공식 링크.
- 대화·초안 LLM — 키 문제 해결 전까지 503.
