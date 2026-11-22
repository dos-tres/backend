# 개발 로그

## 2026-11-21 — 신청 ① 개인정보 줄이기: FE 채우기 · 치환 · AI 전달 내용 보기

- 브랜치: `feat/apply-fill-keys` (`main` 0d20a4f에서)
- 결정: 구글폼 제출은 지금처럼 BE가 대신 한다(성공 확인·테스트 폼 주소 보호). 개인정보가 BE를 지나는 때는 [제출하기] 한 번뿐, 저장·로그 없음.
- `start`: 이름·생년월일·연락처·이메일 칸에 `fill_key` → FE가 기기 값으로 채운다. `applicant`는 안 보내도 됨(보내면 예전처럼 채움).
- `draft`: `[이름]`·`[생년월일]`·`[연락처]`·`[이메일]` 자리 표시를 그대로 쓰게 프롬프트 수정, 응답에 `placeholders`. `preview: true`면 LLM 없이 `ai_input`(AI에 보낼 글) 반환. 안전망으로 LLM에 보내기 전 휴대폰 번호·이메일을 BE에서도 가림.
- 문서: APPLY.md 9-6장·12장, FRONTEND.md 4-6.
- 검증: 테스트 4개 추가(fill_key, start 에 applicant 없이, 자리 표시 유지·번호/이메일 가림, preview 가 LLM 안 부름) 포함 전체 110개 통과. 실제 LLM으로는 아직 확인 전(키 갱신 필요).
- 아직: FE 치환·복원·미리 보기 화면.

## 2026-11-21 — 배포 준비 (Dockerfile·화면 제공·스케줄러·사용량 제한)

- 브랜치: `feat/deploy`. 팀 결정(Lightsail 컨테이너, 이미지 1개, 앱 안 스케줄러) 그대로.
- `Dockerfile`(FE 빌드 + 백엔드, 작업 폴더에서 빌드) · `Dockerfile.dockerignore`(.env·*.local.json 제외).
- `app/web.py`: `WEB_DIR`의 FE 빌드 제공, 새로고침 시 index.html, 없는 /api 는 JSON 404 (Windows 경로 구분자 처리).
- `app/scheduler.py`: `SCHEDULER_ENABLED`면 시작 60초 뒤 + 매일 4시 `pipeline.run_daily`(별도 프로세스, DB 없으면 --no-load, LLM 없으면 --no-llm, 겹침 방지, 끝나면 서비스 JSON 캐시 비움).
- `APPLY_FORMS_JSON`: 테스트 폼 목록을 환경변수로(파일과 합침).
- `app/limits.py`: LLM 요청(대화·초안) 접속자당 1분 10·하루 100, 전체 하루 2,000 → 429 `RATE_LIMITED`. 위기 안내는 제한 없음.
- 배포 방법: `docs/DEPLOYMENT.md` 9장, `deploy/containers.example.json`·`public-endpoint.json` (`containers.json`은 Git 제외).
- 검증: 신규 테스트(web 4, scheduler 5, limits 4, 폼 목록 1) 포함 전체 통과. 로컬 이미지(299MB) 실행: 화면·새로고침·API·추천(file)·위기 안내·11번째 대화 429·환경변수 폼으로 신청 시작, 컨테이너 안 정책 파이프라인 41초(정책 2,314), 이미지 안 비밀 파일 없음.
- 운영 DB: Lightsail 관리형 PostgreSQL(서울)로 결정. `DB_AUTO_MIGRATE`로 시작 시 `alembic upgrade head` + 비어 있으면 기본 데이터 적재(`load_catalog --if-empty`, 스케줄러와 같은 스레드). 로컬 빈 DB로 컨테이너 확인: 테이블 생성·2,335/137 적재·`/readyz` 200·추천 `source: db`, 재시작 시 건너뜀. 컨테이너 서비스가 비공개 모드 DB에 붙는지는 AWS 문서에 없음 → 안 되면 공개 모드(강한 비밀번호, 심사 후 삭제).
- 아직: Lightsail 실제 배포(AWS 계정·키는 사용자), LLM 키.

## 2026-11-21 — FE 연결 안내와 '시 전체' 지역 코드

- 브랜치: `docs/frontend-guide`
- `docs/FRONTEND.md`: FE 연결 안내(화면별 API, 실제 응답 예시, 오류 처리, FE와 맞춰야 하는 값 14가지).
- FE 공식 법정동 사전의 시군구 269개 중 13개(구가 있는 시의 '시 전체': 수원·성남·안양·부천·안산·고양·용인·화성·청주·천안·포항·창원·전주)를 추천 API가 422로 거절 → `regions.CITY_DISTRICTS`로 그 시의 구 코드를 합쳐 받음. 화성 41590·천안 44130은 옛 코드 표에도 있지만 '시 전체'로는 받는다(구 전체 = 옛 코드 정책 포함).
- 검증: 지역 테스트(13개 모두 200, 화성시 전체 후보 = 4개 구 후보 합) 포함 전체 통과. 개발 DB로 41110·41590·52110 추천 200 확인.

## 2026-11-21 — 추천 품질 (LLM 없이): 지난 행사·관심 분야·이유 문구

- 브랜치: `feat/apply-form` (FE 연결 점검에서 찾은 것)
- 지난 행사가 '상시'로 추천됨(8월 북캉스, 9월 체육대회): `classify.stale_reason`이 제목 날짜만 봤다 → 마감일·진행 종료일이 없고 상시 서비스 제목이 아니면 본문 요약 날짜도 보고, 모두 지났으면 제외. `classify.py --no-llm`으로 다시 만들어(분류는 캐시) 서비스 대상 프로그램 169 → 137(본문 날짜 지남 14, 마감 19). `data/seed/serving/programs_serving.json` 갱신, 개발 DB 적재(closed 33).
- 구직자가 '일자리·취업'을 골라도 일자리 정책 0개: 관심 분야 자리 보장(`rules._keep_interests`, 최대 2개). 점검 페르소나에서 「서울형 청년인턴 직무캠프」, 마음건강 상담 정책이 들어옴.
- 추천 이유 "밖에 거의 안 나간다고 했어요" → "밖에 잘 안 나간다고 했어요" (FE가 5단계 '드물게'를 백엔드 '거의 안 나가요'로 보내 과장돼 보임).
- 검증: 관심 분야 자리 테스트 2개 추가, 전체 테스트 통과.

## 2026-11-21 — 챗봇 신청 ① 대신 제출(구글폼) API

- 브랜치: `feat/apply-form` (`main` b94e0ed에서)
- `app/apply/`: `gform.py`(폼 페이지의 FB_PUBLIC_LOAD_DATA_ 읽기, 마감·로그인 필요·여러 페이지·파일 올리기 판단, formResponse 제출, 기타 답), `fill.py`(문항 제목으로 기본 정보 채우기, 동의 문항은 채우지 않음, 거주지 "동까지"는 구까지만 채우고 묻기, 말풍선 문구), `registry.py`(Git 제외 `*.local.json` 신청서 목록, 결과에 `apply_channel` 표시), `service.py`·`router.py`(`/api/apply/start`·`draft`·`submit`).
- `app/catalog/repository.get_item`: id 로 항목 하나(DB 우선, 실패 시 서비스 JSON).
- 설정 `APPLY_FORMS_PATH`(.env), `.gitignore`에 `*.local.json`. 시연용 테스트 폼 주소는 로컬 파일에만.
- 검증: `tests/test_apply.py` 17개(가짜 폼 페이지·가짜 제출·가짜 LLM: 문항 읽기, 마감 문구, 로그인·여러 페이지·파일 거부, 채우기·동의 안 채움, 기타 답, 필수·선택지 검증, 시작만으로 제출 안 함, 제출 실패·마감, 초안에 이름·연락처·생년월일 안 보냄, 결과의 apply_channel) 포함 전체 95개 통과. 실제 테스트 폼으로 `start` 확인(신청 가능: 4개 채움·4개 질문, 마감: 기관 문구 안내).
- 같은 날 로컬에서 FE(main b65dd42)와 연결해 확인: 상태 체크 문항·요약·추천은 실제 API·DB로 동작, AI 대화 화면은 FE가 아직 예시 응답(`/api/chat` 호출 없음). 대화 API는 LLM 키 인증 실패(HTTP 401)로 503 — 키 갱신 필요.
- 실제 제출 점검(가상 정보, 우리 테스트 폼, 3회 모두 기록됨): 처음 구현(문항 답 + fvv·pageHistory·fbzx)으로도 기록됐다(처음에 "안 들어왔다"고 본 것은 마감 테스트 폼을 확인한 것). 점검 중 바꾼 것: ① 브라우저처럼 폼 페이지의 숨은 값(`partialResponse`·`submissionTimestamp`·선택 문항 `_sentinel`)도 같이 보냄(필수는 아니었지만 브라우저와 같게), ② 성공 판단을 "HTTP 200"에서 "입력 폼이 다시 나오지 않음(접수 완료 화면)"으로 바꿈. 중간 판단 기준("폼 데이터가 다시 있으면 실패")은 접수 완료 화면에도 폼 데이터가 있어 틀렸고, 그 때문에 기록된 제출 1건을 실패로 보고했다 → 지금 기준으로 저장한 실제 화면 두 개를 맞게 구분하는 것 확인. 필수 답이 빠지면 구글은 400.
- 아직: 실제 LLM 초안(키 갱신 후), ②③④ 갈래, 대화의 `apply` 버튼, FE 화면.

## 2026-11-21 — 신청 흐름 설계와 단축 링크 풀기

- 브랜치: `feat/apply-flow` (`feat/ai-chat` 위)
- 신청 흐름 설계 문서 `docs/APPLY.md`(구현 전, 시연·MVP용). 실제 청년센터 구글폼 2개(신청 가능·마감)를 읽어 문항 형식·마감 표시를 확인(제출하지 않음). 테스트 폼 생성 스크립트 `scripts/create_test_forms.gs`.
- 구글폼 링크가 없는 프로그램 128개를 경우별로 분류(APPLY.md 2-1). 그중 bit.ly 4개가 실제로는 구글폼이었다.
- `merge.py`: 단축 링크(bit.ly·naver.me·tinyurl 등)를 열어 최종 주소로 바꾼 뒤 신청폼인지 판단. 캐시 `data/runtime/cache/short_links.json`, 실패는 캐시하지 않음. 풀린 주소가 신청폼이 아니면(지도·뉴스) 신청폼으로 치지 않는다.
- 검증: `tests/test_short_links.py` 8개(네트워크 없음) 포함 전체 테스트 통과. 실제 데이터로 merge 재실행: 단축 링크 77개 풀림·7개 못 풂, 서비스 대상 169개 중 구글폼 42 → 47개, 바뀐 행 70개.
- 한계: zrr.kr·iii.im은 스크립트로 주소를 받아 와서 못 푼다(단축 링크 그대로 후보). 그누보드 글은 신청폼만 남기므로, 단축 링크가 신청폼이 아닌 신청 페이지(채용 공고 등)로 풀리면 `apply_urls`에서 빠진다(이번에 3건, 모두 마감 글).
- `data/seed/serving`은 다시 만들지 않았다. 다음 매일 실행 때 반영된다.

## 2026-11-19 — AI 비서 대화 `POST /api/chat`

- 브랜치: `feat/ai-chat` (449bfae에서 시작, PR #9 병합 뒤 `main` 41d9e4d로 갱신)
- 목적: 사용자의 짧은 말에서 상태·관심 분야·찾는 지원을 알아듣고 추천·검색으로 이어 주는 대화. 자살·자해 관련 말에는 검색보다 위기 안내를 먼저.
- 구현 완료와 배포 구분: API·테스트·문서 완료. FE 연결·배포·대화 저장은 하지 않았다.

### 결정

- LLM은 말을 알아듣고(상태 체크 답·관심 분야·의도·검색어) 답장만 쓴다. 추천·자격·정책 이름은 규칙 엔진과 DB에서 나온다 → LLM이 정책을 지어낼 수 없음.
- 위기 신호는 규칙(정규식)으로 먼저 확인하고 LLM을 부르지 않는다. 109·1577-0199·1388·112/119 안내.
- 자동 추천은 특정 대상 사업을 빼지만, 대화에서 사용자가 직접 찾은 검색에는 포함(`eligible(allow_special=True)`).
- 저장하지 않음(인증 전). FE가 대화·기본 정보·답을 매번 보낸다. 이번에 알아들은 답은 `checkin_update`로 따로 줘 확인할 수 있게 함.
- LLM은 파이프라인과 같은 GMS(OpenAI 호환, gpt-4.1-mini). 실패하면 503 `AI_UNAVAILABLE`, 예시 답변으로 대신하지 않음.

### 주요 변경

- `app/chat/`: `safety.py`(위기 규칙·연락처), `llm.py`(OpenAI 호환 클라이언트, 20초·재시도 1회), `prompt.py`, `search.py`(검색어 검색), `service.py`, `router.py`.
- `app/config.py`: `llm_api_key`(GMS_KEY 등), `llm_base_url`, `llm_model`, `llm_timeout_seconds`. `app/main.py`: 라우터·`AI_UNAVAILABLE` 처리.
- `app/recommend/rules.py`: `eligible(..., allow_special)`.
- 테스트 `tests/test_chat.py` 10개(가짜 LLM: 위기, 503, 추출 검증, 추천·검색 연결, 입력 검증, 위기 표현 48개, LLM 클라이언트 오류).
- `scripts/chat_eval.py`: 실제 LLM 대화 품질·속도 점검(프롬프트·모델 바꿀 때 실행).
- 문서: `docs/CHAT.md` 신규, README·DEPLOYMENT·`.env.example`.

### 실제 실행한 검증

- `python -m unittest discover -s tests`: 51개 통과(로컬 Docker PostgreSQL 17).
- 실제 LLM(GMS gpt-4.1-mini)으로 5개 대화 확인(docs/CHAT.md 6장). 처음에는 "집에만 있어요"를 상태 체크 답으로 안 옮기고, 검색어가 구 단위라 안 맞고, 기본 정보가 있어도 사는 곳을 물었음 → 프롬프트 예시·짧은 검색어 지시·서버 단어 분리·검색 결과 중복 정리로 고친 뒤 재확인.
- 규칙·성능 검증(docs/CHAT.md 6장):
  - 위기 규칙: 처음 31개 중 16개만 탐지(간접 표현 누락), 일상 표현 오탐 3 → 표현 묶음별로 다시 써서 32/32 탐지, 오탐 0/16. 세트를 `tests/test_chat.py`에 고정.
  - LLM 품질: `scripts/chat_eval.py`(23개 × 3회) 처음 34/46 → 프롬프트 chat-v2·temperature 0으로 69/69.
  - 응답 시간: LLM 포함 중앙값 1.8초·p95 2.5초, 서버 처리(DB) 약 30ms, 위기 응답 5ms 이하.

### 2026-11-20 추가: 비서 말투·말풍선 형식 (프롬프트 chat-v3)

피클(AI 비서가 대신 확인하고 결과를 짧게 알려 준 뒤 다음 할 일을 제안)을 말투·흐름 기준으로 삼았다.

- 응답 `reply`(문자열) → `replies`(말풍선 목록). 결과가 있으면 서버가 실제 결과로 결과 말풍선을 만들어 [LLM 첫 말] → [결과] → [LLM 다음 말] 순서로 끼운다(`result_summary`: 검색어·개수·지역 프로그램 없음·소득 조건 표시).
- 말투: 해요체·짧게·공감 한 마디·결과 → 다음 행동. 할 수 있는 일(이야기 듣기·추천·찾기)만 제안하고 전화·알림·신청 대행은 "아직 못 해요".
- 제안 버튼(`offer` → 맞춤 추천 받기 / ○○ 지원 찾기), 위기 안내도 말풍선 3개(공감 → 109 → 지원 찾기).
- 서버 안전장치: 요청 표현 없이 추천·나이 질문으로 넘어가면 제안 버튼으로, 이미 답한 문항을 다시 묻는 문장 제거, 결과를 겹쳐 말하는 문장 제거, 말풍선이 그 문항을 물을 때만 상태 체크 버튼.
- LLM 시간 제한을 재시도 포함 전체 20초로(시간 초과면 재시도 안 함). 점검 중 한 번 40초 응답이 나와서.
- 검증: 테스트 61개 통과. `scripts/chat_eval.py` 26개 × 3회(말투·못 하는 일 약속·결과 중복·버튼 일치 검사 추가) 첫 실행 48/52 → 78/78. 고친 내용은 docs/CHAT.md 7장.

### 2026-11-20 추가: 여러 턴 시나리오 점검

- `scripts/chat_scenarios.py`: FE 동작(버튼 누르기, 기본 정보 입력 후 다시 보내기)을 흉내 내 19개 시나리오를 실제 LLM으로 여러 턴 돌려 대화록을 만든다. 결과·목록: `docs/CHAT_SCENARIOS.md`.
- 찾아 고친 것: "추천해 줘요"를 공감만 하고 끝냄 / "월세지원있냐"·영어 요청을 못 알아들음 / 방금 들은 답을 말을 바꿔 다시 물음 / 흔한 검색어 하나로 관련 없는 결과(첫 검색어 필수로) / 기본 정보가 있는데 사는 지역을 물음 / 결과 뒤 "기다려 주세요" / "못 해요" 한 줄로 끝남(제안 붙임) / 날씨를 지어냄 / 기본 정보를 물으며 버튼이 같이 나옴.
- 남은 한계: 결과를 다시 거르는 질문("이 중에 집 근처 거?") 미지원, 관심 분야만 말할 때 분야 찾기 버튼이 가끔 안 나옴, 위기 이후 흐름 전문가 검토 전.
- 검증: 테스트 64개 통과, `scripts/chat_eval.py` 28개 × 3회 84/84(날씨 지어내지 않음·기본 정보만 묻기 추가), 시나리오 19개 재실행 응답 38회 중앙값 1.9초.

### 남은 작업

- 대화 저장(로그인 도입 이후), 사용량 상한·요청 빈도 제한, 위기 문구·연락처 전문가 검토, FE 연결(말풍선·버튼·입력 중 표시).
- 전화 문의 대행·공고 다시 확인 등 일을 대신 하는 기능(실행 서비스와 저장 필요).

## 2026-11-20 — 거주지 코드 목록 API와 옛 코드 매칭

- 브랜치: `feat/region-codes` (`main` 449bfae에서 생성)
- 목적: FE 지역 선택이 백엔드와 같은 코드를 쓰게 한다. FE `regions.json`(통계청 계열 코드)은 시군구 245개 중 29개(서울·경기 일부)만 백엔드 코드와 일치해 서울 밖은 추천이 422가 된다.
- 구현 완료와 배포 구분: 목록·API·매칭·테스트·문서 완료. FE 교체는 frontend 레포 작업. 배포하지 않았다.

### 변경

- `app/catalog/regions.py`: 시군구 256개 `(code, 시도, 시군구)`. 이름은 온통청년 청년공간 API(`centers_seed.jsonl`)에서 190개, 나머지는 법정동 이름. 화성시 일반구(41591 만세·41593 효행·41595 병점·41597 동탄)와 인천 개편 구(28125 제물포·28155 영종·28275 서해·28290 검단)는 원본 데이터 기관명과 공개 자료로 교차 확인.
- 옛 코드 6개(`28110`, `28140`, `28260`, `41590`, `44130`, `30000`)는 목록에서 빼고 `LEGACY`로 새 코드에 연결. 원본에서 화성시 `41590`만 붙은 정책 82건, 천안시 `44130`만 붙은 정책 87건이 구 단위 사용자에게 빠지던 문제를 함께 고침.
- `GET /api/regions` 추가. `known_sigungu_codes()`는 이제 이 목록을 돌려준다(사용자 입력 검증). 데이터에 나오는 코드는 `data_region_codes()`.
- 매칭: `rows.matches_basic`·`scope_of`·`repository.from_db`가 `match_codes()`(사용자 코드 + 옛 코드)를 쓴다. DB는 `region_cds && codes`(GIN 인덱스 사용).
- `docs/REGIONS.md`: 형식·옛 코드 표·전체 code/label 목록.

### 실제 실행한 검증

- `python -m unittest discover -s tests`: 50개 통과, 전용 테스트 DB(`db-test`) 포함 skip 없음. 신규 `tests/test_regions.py`: 데이터 코드 ⊆ 목록 ∪ 옛 코드, 목록 256개 모두 추천 200, 옛 코드·46720 422, 화성 동탄구·천안 동남구에 옛 코드 정책 포함. 기존 DB/파일 결과 일치 테스트(11620·30200·41117·26350) 통과.

### 남은 작업

- frontend: 지역 선택을 `/api/regions`로 교체(읍면동 검색 대신 시군구 검색).
- 원본이 새 코드를 쓰기 시작하면 `regions.py`에 추가(테스트가 알려 줌). 법정동 이름으로 채운 66개는 공식 목록으로 한 번 더 대조하면 좋다.

## 2026-11-19 — 회원 테이블 (migration 0004)

- 브랜치: `feat/user-schema` (`main` f0a550c에서 생성)
- 목적: 회원 관리 DB 구조를 미리 만들어 둔다. 로그인 방식은 미정.
- 구현 완료와 배포 구분: 테이블·모델·migration·테스트·문서 완료. 가입·로그인·프로필 API, 인증은 만들지 않았다. 배포하지 않았다.

### 결정

- 로그인 방식과 상관없는 4개만 테이블로: `users`, `user_profiles`, `user_consents`, `checkin_responses`.
- 로그인 수단(`user_identities`)·세션(`auth_sessions`)은 `app/users/models.py`에 주석으로 설계만 남김(회원과 로그인 수단 분리, provider_subject 식별, 서버 세션 + 토큰 해시, 익명 시작 후 가입 연결).
- 회원 데이터는 모두 `users`를 CASCADE로 참조 → 회원 행 삭제 = 개인 데이터 삭제.
- 프로필은 추천 API profile과 같은 값, 나이 대신 출생연도. 상황(민감 정보)·상태 체크 응답·대화는 동의(`user_consents`)가 있을 때만 저장(서비스 코드에서 확인).
- 상태 체크 응답은 덮어쓰지 않고 쌓음. 문항 버전 `QUESTION_VERSION`(`app/checkin/questions.py`) 추가.
- 테이블 설명은 `docs/DATABASE.md` 한곳에 모음(카탈로그 상세는 RECOMMENDATION.md 링크).

### 실제 실행한 검증

- 개발 DB `alembic upgrade head` → 0004, `alembic check` 차이 없음.
- `python -m unittest discover -s tests`: 44개 통과(로컬 Docker PostgreSQL 17). 신규 `test_users_db.py`: 기본값(UUID·status·빈 배열), CHECK 제약 6종, 회원 삭제 시 프로필·동의·상태 체크 응답 삭제. `test_database.py` 0004 반영(upgrade/downgrade 왕복 포함).

### 남은 작업

- 로그인 방식 결정 → `user_identities`·`auth_sessions` migration, 가입·로그인·프로필·동의 API, 사용자별 접근 제어.
- 마이페이지 기록(`saved_items`·`activity_records`·`schedule_events`)과 대화 저장 테이블은 화면·기능 연결 때.
- 탈퇴 유예·보관 기간·동의 문구 버전 정책.

## 2026-11-19 — 페르소나 점검으로 찾은 추천 오류 수정

- 브랜치: `feat/recommendation-pipeline` (PR #6에 이어서)
- 목적: 임의 페르소나 5명(관악 구직·은둔, 대전 기혼 회사원, 노원 대학생, 해운대 한부모·수급자, 곡성 농업)으로 설문 → 요약 → 추천을 개발 DB에서 실행해 보고 찾은 오류를 고친다.
- 구현 완료와 배포 구분: 코드·테스트 수정 완료. 배포하지 않았다.

### 찾은 문제와 수정

- 신청기간이 비어 있으면 사업이 끝났어도 추천됨(9건, 예: 9월에 끝난 은평청년축제가 노원 대학생에게 추천) → 신청기간이 없으면 사업 종료일(`bizPrdEndYmd`)을 마감일로 (`rows.policy_deadline`).
- 특정 대상 사업이 일반 사용자에게 추천됨(예: 지원망 high 응답자에게 자살시도자 치료비, 경계선지능청년지원) → 제목 기준 특정 대상 제외(`rules.SPECIAL_TARGET`). 자격 조건 원문은 '국가유공자 우대'처럼 여러 대상 중 하나로 적혀 오탐이 많아 쓰지 않았다.
- 옛 시군구 코드(곡성 `46720`, 광주·전남 통합 뒤 `12720`)를 받으면 조용히 0건 → 원본 코드 목록에 없으면 422 `Unknown sigungu_cd` (`repository.known_sigungu_codes`).
- 추천 응답에 정책 `income_condition`(소득 무관이면 null / 연소득 상한 / 원문 설명)과 `programs_notice`(프로그램 0건 이유: `no_program_data` / `no_program_match`)를 추가. 소득은 추천에서 거르지 않고 신청하려 할 때 FE가 확인하기로 함.
- 위 마감일 수정을 적재해 보니, 원본이 같으면 파생 컬럼(`deadline`)이 바뀌어도 DB에 쓰지 않던 upsert 조건을 발견 → 저장 컬럼 전부를 비교하도록 수정(이력·`updated_at`은 그대로).

### 실제 실행한 검증

- `python -m unittest discover -s tests`: 39개 통과(로컬 Docker PostgreSQL 17).
- 개발 DB에 seed 재적재 → 정책 마감일 1,904건이 새 규칙과 일치.
- 페르소나 5명 재실행: 지난 사업·특정 대상 사업 0건, 옛 코드 46720은 422, 새 코드 12720은 정상 추천.

### 남은 작업 (이번에 고치지 않음)

- 관심 분야 가중치(+10)가 영역 점수(30/18)보다 약해 고른 관심 분야가 결과에 안 나오는 경우(노원 대학생의 교육·해외) — 가중치 조정은 팀 결정 필요.
- 소득 조건 확인 화면(FE), 서울 밖 청년센터 프로그램 수집(지역 통합 플랫폼·사이트별 크롤러), 생애 단계만 겹쳐도 '내 상황에 맞는 지원' +10.

## 2026-11-19 — catalog 변경 감지와 변경 이력 (`catalog_item_changes`)

- 브랜치: `feat/recommendation-pipeline` (PR #6에 이어서)
- 목적: `source_hash`를 저장만 하고 비교하지 않아 매일 전 행을 덮어쓰고 `updated_at`이 '마지막 적재 시각'이 되던 문제를 고치고, 원본 변경을 이력으로 남긴다.
- 구현 완료와 배포 구분: 코드·마이그레이션·테스트 작성 완료. 운영 DB 적용·배포는 하지 않았다.

### 결정

- 해시는 serving 항목 전체의 SHA-256, 단 매일 바뀌는 정책 조회수 `inqCnt`는 뺀다. 조회수는 payload에는 계속 반영한다(추천 동점 정리에 씀).
- 변경 종류: created / updated / reopened / closed. updated·reopened는 이전 payload와 바뀐 최상위 필드를 남긴다. 찜·신청 항목 변경 알림을 위해 덮어쓰기만 하는 방식 대신 이력 저장을 선택했다.
- `updated_at`은 해시·상태가 바뀐 시각만 뜻한다.

### 주요 변경

- `app/catalog/rows.py`: `content_hash`, `changed_fields`, `VOLATILE_FIELDS`.
- `app/catalog/models.py`: `CatalogItemChange`. `migrations/versions/0003_catalog_item_changes.py`.
- `app/catalog/load.py`: `plan_changes`(순수 함수)로 분류 후 upsert. 완전히 같은 행은 쓰지 않고, 닫힘은 `RETURNING`으로 실제 닫힌 id만 이력에 남긴다. 반환값이 `{received, created, updated, reopened, unchanged, closed, previously_active}`로 바뀌었다.
- 테스트: `test_catalog_changes.py` 신규(DB 없이), `test_catalog_db.py`에 이력·조회수 케이스 추가, `test_database.py` 0003 반영.
- 문서: `docs/RECOMMENDATION.md` 2장, README, `docs/DEPLOYMENT.md`.

### 실제 실행한 검증

- 로컬 Docker Desktop(PostgreSQL 17 컨테이너 `db`·`db-test`)에서 실행.
- `python -m unittest discover -s tests -v`: 37개 전부 통과(DB 통합 테스트 포함, `alembic check` 차이 없음).
  - 처음 실행에서 `load.py`가 SQLAlchemy Result를 `dict.update`에 넘겨 실패한 것을 찾아 고쳤다(Result에 `keys()`가 있어 매핑으로 처리됨).
- 개발 DB: `alembic upgrade head` → 0003. `load_catalog --seed` 1회차 created 정책 2,335·프로그램 169, 같은 데이터 2회차 전부 unchanged(이력 추가 없음).

### 남은 작업

- 이력 보관 기간·정리 정책, 찜·신청 기능과 연결한 변경 알림.
- 해시 방식 변경 후 첫 적재에서 기존 행이 모두 `updated`(바뀐 필드 없음)로 한 번 기록된다. 운영 DB가 아직 없어 별도 처리는 하지 않았다.

## 2026-11-19 — 정책·센터 프로그램 추천 파이프라인과 API

- 브랜치: `feat/recommendation-pipeline` (origin/main `d11488c`에서 생성)
- 목적: 로컬 `ai_hackathon` 폴더에서 만든 정책 수집·센터 크롤링·LLM 분류·추천 로직을 저장소 구조로 옮기고, DB 적재와 API로 연결.
- 구현 완료와 배포 구분: 코드·seed 데이터·마이그레이션·API 구현 완료. 스케줄러 연결과 실제 배포·운영 DB 적재는 하지 않았다.

### 결정

- 상태 체크는 `docs/requirements.md` 방식(영역 5문항 + 만족도·바꾸고 싶은 영역·대면 부담·관심 분야). I5 또래 비교 점수는 쓰지 않는다. 진단처럼 보이지 않게, 점수·위험 등급 없이 사용자 답 그대로 영역 수준을 만든다.
- 저장은 PostgreSQL 테이블 하나(`catalog_items`) + JSONB. 필터 컬럼만 컬럼으로 두고 원본은 `payload`. 이유는 docs/RECOMMENDATION.md 2장.
- 추천 계산에는 LLM을 쓰지 않는다(분류만 하루 한 번, 캐시).

### 주요 변경

- `pipeline/`: 정책 fetch·classify, 프로그램 crawl(sync_centers·seoul_orang·gnuboard·merge)·classify, `llm.py`, `paths.py`, `load_catalog.py`, `run_daily.py`.
- `data/seed/`: serving JSON(정책 2,335·프로그램 169), 분류 캐시, 센터 목록. `data/runtime/`은 gitignore.
- `app/catalog/`(모델·행 변환·upsert·후보 조회), `migrations/versions/0002_catalog_items.py`.
- `app/checkin/`, `app/recommend/`, `app/main.py` 라우터 등록.
- `scripts/recommend_demo.py`, `tools/data_check/`.
- 테스트: `test_checkin.py`, `test_recommend_rules.py`, `test_recommend_api.py`, `test_catalog_db.py`, `test_database.py`(0002 반영).
- 문서: `docs/RECOMMENDATION.md` 신규, `POLICY_FIELDS.md`·`CENTER_FIELDS.md`·`DATA_FIELDS.md`·`CRAWLER.md`·`DATA_CHECK.md` 이관(경로 수정), README·`.env.example`·`requirements.txt`(requests, beautifulsoup4).

### 실제 실행한 검증

- 작업 환경에 FastAPI·SQLAlchemy가 없고 패키지 설치가 막혀 있어, 순수 로직 테스트만 로컬에서 실행: `test_checkin`·`test_recommend_rules` 14개 통과.
- `python pipeline/policies/classify.py --no-llm`: 캐시만으로 ok 2,335건 재현, 이전 결과와 같은 보정 건수. 프로그램 classify `--no-llm`: ok 169건.
- `sync_centers --from-seed` 동작, `run_daily` 키 없을 때 정책 단계 실패 후 프로그램 단계 계속 진행 확인.
- `scripts/recommend_demo.py`: 페르소나 5명 결과 확인(예: 관악 고립 페르소나 → 고립·은둔 상담, 심리상담 바우처, 소셜다이닝, 관악 센터 상담 프로그램).
- API·DB 테스트(마이그레이션 0002, upsert·closed 처리·50% 안전장치, DB/파일 결과 일치, API source)는 GitHub Actions PostgreSQL에서 확인한다. 결과는 PR 체크에 기록.

### 발견한 문제

- ok 정책 1,268건이 신청기간(`aplyYmd`)이 이미 지났다. 기본 필터에 마감일 비교를 넣었다.

### 남은 작업

- 매일 실행 스케줄러(서버 안 vs 외부 cron)는 배포 환경을 정한 뒤 결정.
- 프로그램 지역 편중(대부분 서울), 원본 오류 일부, v3 재사용 분류 재검토 옵션.
- AI 비서 대화와 추천 연결, 사용자 저장·인증.

## 2026-11-18 — PostgreSQL 공통 DB 기반

- 브랜치: `chore/database-foundation`
- 목적: 후속 정책 수집과 세션·설문 개발이 공유할 PostgreSQL 연결·요청별 DB 세션·마이그레이션 기반 마련.
- 시작 상태: PR #4 병합 후 최신 origin/main `3998209`에서 생성. 로컬 변경 없음. 이전 README·배포 기준·개발 로그·작업 규칙은 병합된 내용을 보존하고 이어서 갱신했다.
- 구현 완료와 배포 구분: 로컬 DB 기반 구현·검증 완료이며 실제 배포·운영 DB 구성은 수행하지 않았다. 서비스 세션·설문·정책·추천·AI 기능과 테이블은 추가하지 않았다.

### 주요 변경

- `compose.yaml`, `.env.example`: PostgreSQL 17 개발 DB(named volume)와 별도 테스트 DB(tmpfs), 로컬 전용 포트. 실제 비밀번호·URL은 무시되는 로컬 .env에만 생성했다.
- `requirements.txt`: SQLAlchemy, psycopg binary, Alembic 추가.
- `app/config.py`, `app/database.py`, `app/main.py`: SecretStr DATABASE_URL, PostgreSQL URL 검증, 연결 풀, 요청별 세션 의존성, 미커밋 rollback·close, lifespan 종료 dispose. 서버 시작 시 스키마를 변경하지 않음.
- `alembic.ini`, `migrations/`: 공통 Base.metadata 및 이름 규칙, 이후 모델 import와 autogenerate를 위한 환경. 빈 baseline 0001은 기능 테이블 없이 Alembic 버전만 관리.
- `tests/test_database.py`, `.github/workflows/backend.yml`: DB 단위·PostgreSQL 통합 테스트 및 CI 전용 PostgreSQL 서비스.
- `README.md`, `docs/DEPLOYMENT.md`, `AGENTS.md`: 두 팀원 실행 절차, 개발 순서 일치, CLI와 이 대화창의 역할 분담.

### API 변경

- 신규 `GET /readyz`: SELECT 1 성공 시 200 `{"status":"ok"}`, 미설정·연결 실패 시 503 `{"error":{"code":"DATABASE_UNAVAILABLE","message":"Database unavailable"}}`. URL·비밀번호·내부 예외는 응답에 노출하지 않음. 스키마 버전까지 검사하지는 않음.
- 기존 `GET /healthz`: DB 상태와 무관한 프로세스 상태 확인 200 유지. /docs와 OpenAPI에 readyz 포함.

### 실제 실행한 검증

- SQLAlchemy 2.0.58, psycopg 3.3.9, Alembic 1.20.1 설치 완료.
- `docker compose --profile test up -d --wait db-test`: PostgreSQL 17 healthy. 개발 DB는 시작하지 않고 별도 컨테이너·dos_tres_test DB·테스트 포트에서만 테스트했다.
- `python -m unittest discover -s tests -v`: 기존 5개와 신규 5개, 총 10개 통과(skip 없음).
- 통합 검증: 실제 DB 연결, readyz 200, 존재하지 않는 DB 역할 인증 실패와 readyz 503, 실패 응답 비밀값 미노출, DB 실패 시 healthz 200, 요청별 세션 분리, 예외 후 미커밋 트랜잭션 rollback·풀 반환, 앱 종료 dispose 확인.
- Alembic Python 명령 API로 upgrade head → check → downgrade base → upgrade head → 재upgrade 실행. 버전 0001, autogenerate 차이 없음, alembic_version 외 기능 테이블 없음 확인. 앱 시작 전후 테이블 목록 동일 확인.
- 실제 Uvicorn 서버도 전용 테스트 DB URL을 주입해 실행했다. 정상 연결과 인증 실패 각각 HTTP /readyz 200·503, /healthz 200, /docs 200, OpenAPI readyz 경로 확인 후 서버 종료. 개발 DB 데이터에는 접근하지 않았다.
- `python -m pip check`: 의존성 충돌 없음. `git diff --check`: 통과. .env·.venv·Python 캐시 제외 확인.
- 기존 Starlette TestClient의 httpx 사용 중단 예정 경고는 남아 있으며 테스트 성공과 별도로 추후 정비할 사항이다.
- GitHub CI는 PR 생성 후 해당 커밋의 체크에서 확인한다. 로컬 성공을 CI·배포 완료로 간주하지 않는다.

### 팀원 인수인계와 남은 작업

각자 Python 3.13 가상환경에 requirements-dev.txt를 설치한다. 기존 .env를 덮어쓰지 말고 예시에 추가된 개발·테스트 비밀번호, URL, 포트를 각각 채운다. 실제 값은 공유·커밋하지 않는다. `docker compose up -d --wait db` → `python -m alembic upgrade head` → `python -m alembic current` → Uvicorn 실행 순서다. 전용 DB 테스트는 `docker compose --profile test up -d --wait db-test` 후 unittest 명령으로 실행한다. TEST_DATABASE_URL이 없으면 통합 테스트 3개가 skip되므로 DB 검증 완료로 기록하면 안 된다. 종료는 API Ctrl+C, 각 DB는 compose stop을 사용한다. 상세 명령과 병렬 마이그레이션 협업 절차는 README를 따른다.

다음 순서는 **공통 DB·API 구조 → 정책 수집 / 세션·설문 병렬 개발 → 추천·AI 대화 → 프론트 연결·배포**다. 이번 PR 리뷰 반영과 기능 API 계약 합의 후 두 팀원이 병렬 개발한다. 인증·개인 기록 접근 제어, 기능별 모델·revision, 실제 AI 제공업체와 운영 배포는 후속 범위다. CLI는 구현·문서·검증·커밋·푸시·PR까지만 진행하며, 이 대화창에서 PR 검토·병합·다음 작업을 지정한다.

## 2026-11-18 — FastAPI 실행 기반 구축 및 PR 준비

- 브랜치: `chore/backend-bootstrap`
- 목적: 팀원이 동일한 절차로 backend를 설치·실행하고 프론트 연결을 준비할 수 있는 최소 실행 기반 마련.
- 시작 상태: README와 요구사항·배포 기준 문서만 존재. 기존 작업 트리 변경 없음. 최신 `origin/main`의 `bfc816c2e90234457136a4ef8bf57c25ce2dc50a`에서 브랜치 생성.

### 주요 변경 파일

| 파일 | 변경 |
| --- | --- |
| app/__init__.py, app/main.py | FastAPI 앱, healthz, CORS, HTTP·검증·서버 오류 처리 |
| app/config.py, .env.example | APP_ENV, JSON 배열 ALLOWED_ORIGINS, 환경변수 우선 적용 및 시작 시 검증 |
| requirements.txt, requirements-dev.txt, .gitignore | 실행 의존성 고정, 테스트용 httpx, 로컬 환경·캐시 제외 |
| tests/test_bootstrap.py, .github/workflows/backend.yml | 자동 테스트 및 Python 3.13 CI, pip check |
| README.md, docs/DEPLOYMENT.md | 실행 절차·구현 현황 정리, 과거 미구현 설명 수정, 후속 계획 분리 |
| AGENTS.md, docs/DEVELOPMENT_LOG.md | 문서 갱신·검증·커밋·푸시·PR·리뷰 대기 규칙 및 인수인계 기록 |

### API 변경

- `GET /healthz`: HTTP 200, `{"status":"ok"}`. 외부 서비스 상태나 설정값은 반환하지 않음.
- `GET /docs`: Swagger UI HTML, `GET /openapi.json`: OpenAPI 명세.
- 앱 오류: `{"error":{"code":"...","message":"..."}}`. HTTP 오류는 `HTTP_상태코드`, 검증 오류는 `VALIDATION_ERROR`(422), 내부 오류는 `INTERNAL_SERVER_ERROR`(500).
- HTTP 오류 헤더 보존. 검증 입력값과 내부 예외 내용은 응답에서 제외.
- 로컬 Vite origin 두 개만 기본 허용하며 credentials는 비활성화. CORS preflight 오류는 미들웨어의 400 텍스트 응답.

### 실제 검증과 결과

- Python 3.13.3 가상환경에서 `python -m pip install -r requirements-dev.txt` 설치 완료.
- `python -m unittest discover -s tests -v`: 5개 테스트 통과. healthz·문서·OpenAPI, CORS 허용/거부, 환경 설정 우선순위·검증, 404·405·422·500 및 헤더 보존 확인. PR 준비 시 재실행해 통과.
- `python -m pip check`: 의존성 충돌 없음. `git diff --check`: 통과.
- `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`으로 실제 서버 실행 후 httpx HTTP 요청 검증: /healthz 200 및 예상 JSON, /docs 200 HTML, /openapi.json 200 및 healthz 경로, 허용 origin OPTIONS 200과 CORS 헤더, 없는 경로 404 및 공통 JSON 확인. 검증 후 서버 정상 종료.
- `git check-ignore`로 .env, .env.local, .venv 및 Python 캐시 제외 확인. 커밋 대상은 소스·문서·예시 설정·CI만 포함.
- 테스트 성공과 별개로 Starlette TestClient의 httpx 사용 중단 예정 경고가 있음. 향후 테스트 클라이언트 의존성 정비 시 확인할 사항이며 이번에는 추가 라이브러리를 도입하지 않음.
- GitHub CI 결과는 PR의 해당 커밋 체크에서 확인한다. CI 성공은 배포 완료를 의미하지 않는다.

### 이어서 실행하는 절차

저장소 루트에서 Python 3.13으로 진행한다. 기존 .env가 있으면 덮어쓰지 말고 .env.example과 비교한다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
# 최초 설정 시에만 실행
cp .env.example .env
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

다른 터미널에서 /healthz와 /docs에 접속하고 README의 검증 명령을 실행한다. 프론트 포트가 다르면 ALLOWED_ORIGINS의 JSON 배열에 실제 origin을 넣고 서버를 재시작한다. 프로세스 환경변수가 .env보다 우선한다. 운영용 바인딩·포트 명령은 README에 별도로 기록했다.

### 남은 작업 및 상태

로컬 실행 기반 구현·검증 완료. 이 PR의 리뷰를 기다리고 리뷰 결과를 반영한 후 다음 개발을 시작한다. 대화 API 계약·프론트 공통 API 모듈, 실제 AI 제공업체·모델 연결, HTTPS 미리보기 배포, 인증·DB 및 개인 기록 저장은 후속 계획이다. DB·세션·설문·정책·AI 기능과 실제 배포는 이번 작업에 포함되지 않는다. 배포 제공업체·운영 URL은 미정이다.

## 2026-11-21 · 정책·프로그램 탐색 API (로컬 구현)

- GET /api/catalog/items와 /api/catalog/items/{item_id}를 추가했다. 목록 검색/지역/나이/종류/카테고리/마감 제외/정렬/페이지 및 상세 공고 필드를 제공한다.
- 기존 추천 응답에도 실제 카테고리/지역/키워드와 일관된 신청 상태·기간 필드를 추가했다. 기존 키는 유지하며 apply_period도 동일 기간 문구를 사용한다.
- DB 우선 source=db, 기존 파일 대체 시 source=file. 개인정보 저장·DB 스키마/데이터 변경 없음.
- 관련 테스트 24개 통과, 실제 DB HTTP 및 프론트 브라우저 연결 확인. main 반영/배포/커밋/푸시/PR 생성은 하지 않았다. 실제 AI API는 미구현이다.
- 계약: [카탈로그 탐색](CATALOG_BROWSER.md).

## 2026-11-21 · 주변센터 실제 정보 연결 (로컬)

- 기존 가상 센터/거리/지도/운영 시간 및 작동하지 않는 위치 버튼을 실제 수집 센터 목록·상세로 교체했다. 서울 34곳이며 실시간 위치순 조회가 아니다.
- 백엔드 GET /api/centers?q=&district= 및 GET /api/centers/{id} 추가. runtime centers.csv가 있으면 활성 행, 없으면 기존 centers_seed.jsonl 사용. source=file, dataset=runtime/seed로 구분하며 DB 센터라고 표현하지 않는다.
- 이름·주소 검색/구 필터/빈 결과/오류 재시도와 8초 요청 제한을 제공한다. 센터명 공백을 제외한 정확 일치로 프로그램을 연결한다. 프로그램은 기존 DB 우선 조회 및 파일 대체를 따르며 programs_source=db/file을 별도 표시한다.
- 실제 브라우저: 전체 34곳, 강동구 1곳, 서울청년센터 강동 상세/주소/운영시간 미제공, DB 프로그램 4개, 선택 공고의 조이 이동, 검색 0건 안내 확인. 홈페이지 주소 없는 경우 미제공 표시, 외부 신청·문의 없음.
- 센터 파일의 전체/최신성은 보장하지 않는다. 좌표/거리/운영 시간·누락 홈페이지 보강은 후속 백엔드 데이터 작업. 프로그램 연결 0건은 운영 프로그램이 없다는 의미가 아님을 표시한다. DB 저장 센터 API·실시간 지도는 미구현.
- 검증: FE npm run build 통과(기존 청크 크기 경고). verify-centers 실제 FE→ASGI 계약/출처/지역/검색/빈 결과/503·timeout 전파 통과. backend tests.test_centers_api + tests.test_catalog_browser 4개 통과. 데스크톱 브라우저 검증, 모바일 센터 화면 별도 검증은 미완료.
- 기존 작업 보존. 두 작업 브랜치의 로컬 미커밋 구현이며 main 반영/PR 갱신/푸시/배포 없음. 서버 유지.

## 2026-11-21 · 센터 별칭으로 누락된 프로그램 복구

- 기존 공백 제거 정확 일치가 공식 센터명의 부가 이름을 처리하지 못해 관악·금천·서초 프로그램을 누락시켰다.
- 공식 서울청년센터 지점 이름을 키로 정규화한다. 관악의 신림동쓰리룸, 금천의 청춘삘딩, 서초의 괄호 공식명과 프로그램의 짧은 지점명을 연결한다. 같은 구의 별도 기관(관악청년청 등)에는 합치지 않는다.
- 수집 파일 기준 관악8/금천14/서초5건 복구, 실제 브라우저 관악 상세에서 DB공고8개 표시 확인. 센터 API2테스트 통과(별칭·기관 구분·연결 결과 회귀 포함). 서버 재시작·유지, 커밋/푸시/PR 변경 없음.
- 센터 ID가 serving 프로그램 필드에 남아 있지 않아 현재 공식 지점명으로 연결한다. 장기적으로 center_sns를 serving/DB 응답까지 유지하는 것이 필요하다. 기타 미수집 센터는 여전히 프로그램이 없을 수 있으며 기관 미운영으로 단정하지 않는다.

## 2026-11-21 · 센터 프로그램 건수 및 카카오 위치 지도 준비

- 센터 목록 API가 동일 연결 기준으로 program_count/open_program_count를 계산한다. 총 수집 수는 마감 공고 포함, 모집 중은 open/always_open만 포함한다. 프로그램 출처는 programs_source=db/file이다.
- 목록에서 수집 수/모집 중 수를 구분한다. 실제 브라우저 DB 연결: 관악8/8, 금천14/13, 서초5/5 확인. 미수집 센터는 ‘프로그램 수집 정보 없음’으로 표시한다.
- 센터 상세에 Kakao JavaScript SDK + services.Geocoder로 주소→좌표→지도/핀 표시를 구현했다. SDK10초/주소검색8초 제한, 실패 재시도, 센터 변경 취소, 반응형 크기 재조정을 제공한다. 주소 미발견/키 미설정/네트워크 실패 시 임의 좌표를 표시하지 않으며 공개 센터 주소 카카오맵 링크를 제공한다. 사용자 위치는 요청하지 않는다.
- 현재 로컬 키가 없어 실제 SDK 지도·좌표·핀 성공은 미검증이다. 브라우저는 키 미설정 안내/주소/지도 외부 링크를 확인했다. 키는 채팅·소스·로그에 출력하지 않았다.
- npm run build 및 verify-centers 통과. backend tests.test_centers_api 3개 통과(전체 센터 목록 수=상세 수, 모집 중 수의 일치 포함). 기존 빌드 청크 경고 유지.
- 커밋/푸시/PR/배포 없음. 로컬 서버 유지.

## 2026-11-21 · 센터 정렬·프로그램 필터·공식 공간 소개

- 정렬 선택을 가까운순/기본순 두 개로 제공한다. 두 모드 모두 연결된 프로그램이 있는 센터를 먼저 두고 각 그룹 안에서 거리순 또는 기존 기본순을 유지한다. 지역이 없으면 기본순, 가까운순 선택은 지역 등록/선택 후 가능하다.
- ‘프로그램 안내 있는 센터만’ 필터를 추가했다(연결 공고 program_count>0 기준). 화면 건수는 필터 결과와 일치한다. 목록의 총 프로그램 수/수집 정보 없음/0개 표시는 제거하고, 모집 중 공고가 있는 센터만 ‘현재 모집 중 n개’를 표시한다. 마감된 공고만 있는 센터도 프로그램 안내 그룹에 포함되지만 모집 중 배지는 없다.
- backend app/catalog/center_guides.json에 공식 기관·지자체 소개를 근거로 공간 용도/시설/이용 안내/출처 URL·확인일을 추가했다. 17개 개별 공간 안내와 17개 서울청년센터의 공식 공통 서비스 안내로 현재34곳을 제공한다. 임의로 프로그램 미운영 기관이라고 분류하지 않는다. 관악청년청은 카페·공유주방뿐 아니라 프로그램도 운영한다는 공식 안내를 반영했다.
- 센터 상세는 ‘어떤 곳인가요?/이용할 수 있는 것/이용 전에/공식 공간 안내’가 먼저다. 연결 프로그램이 없으면 프로그램0개·미수집 경고 대신 공간 이용 안내를 보여준다. 소개는 DB 생성값이 아니라 공식 출처를 정리한 서버 파일이며 주소/프로그램 DB 출처와 구분한다.
- 성북구 공식 페이지의 2026-05-15 수정 안내에 따라 길이음 주소를 삼양로29 성북 청년 스마트창업센터1층으로 보정했다. 관악청년청 운영 시간은 관악문화재단 공식 안내로 제공한다. 나머지 미확인 운영 시간은 추정하지 않는다.
- 앞선 주소 수정도 포함: 원주소로 좌표가 없으면 층/건물 설명을 제거한 도로명·건물번호로 재검색한다. 지도와 거리 계산이 같은 geocodeAddress를 사용한다. 앞선 브라우저에서 관악청년청의 지도/핀 표시를 확인했다.
- 검증: npm run build 통과(기존 청크 크기 경고 유지). verify-center-display 실제 React 정적 렌더에서0개/미수집 문구 제거, 모집중 수, 소개/출처, 정렬2개·필터 확인. verify-center-distance의 두 모드 그룹 우선/거리/필터/원본 보존 검사, verify-center-address와 verify-centers 계약 검사 통과. backend tests.test_centers_api + tests.test_catalog_browser 총7개 통과.
- 실제 HTTP: http://127.0.0.1:5173/api/centers 200, 34곳 모두 guide 포함, programs_source=db. 관악청년청 상세는 program_count0이지만 공식 청년카페·시설 안내가 제공됨 확인. HTTP응답 전체/키/개인정보는 출력하지 않았다.
- 이번 정렬/필터/소개 변경 후 실제 브라우저 상호작용·반응형 재검증은 도구 연결 불가로 미검증. 정적 React 렌더/빌드/실제HTTP 결과와 구분한다.
- 기존 작업 보존. 프론트 test/checkin-response-audit/백엔드 feat/catalog-browser-api 로컬 미커밋 변경이며 main·기존PR 반영/커밋/푸시/병합/배포 없음. FE5173/BE8000 서버 재실행 후 유지.

## 2026-11-21 · 사용자 요청에 따른 커밋·PR·병합 정리

- 사용자가 여기까지의 변경을 한국어 커밋/PR로 기록하고 main 병합 및 완료 브랜치 정리를 명시적으로 요청했다. 기존 프론트 PR #10은 이미 병합된 상태임을 확인했고, 이번 후속 기능은 최신 frontend main b65dd42에서 feat/catalog-centers-chat로 분리한다.
- backend 최신 main b2686fb의 챗봇/신청/지역 보완을 기존 작업에 병합했다. 이들 다른 작업자의 기능을 보존하며, 이번 프론트 조이는 공고 기반 안내이고 새 /api/chat·실제 신청 API 연결은 후속 작업이다. 이전 기록의 ‘백엔드 대화 API 없음’은 당시 상태이며 현재 main에 API가 추가돼 있다.
- 프론트 npm ci/npm run build와 센터 표시·거리·주소·API, 정책 탐색, 대화형 프로필, 기존 설정/저장소/점검/이력/지역 검증 스크립트를 모두 재실행해 통과했다. 큰 청크 경고는 남는다.
- 백엔드는 main 반영 후 비DB 포함88개 검사와 전용 dos_tres_test 전체106개 검사를 통과했다. pip check도 통과했다. 전용 테스트 DB만 시작해 마이그레이션 검사를 수행했으며 개발 DB는 보존했다.
- 새로 포함할31개 프론트/13개 백엔드 후보 파일에서 로컬 비밀값·휴대전화 패턴·구글폼 링크를 검사해 검출0건을 확인했다. .env/.env.local과 실제 키는 Git에 포함하지 않는다.
- 실제 화면의 최종 소개/정렬/필터 변경은 React 렌더와 계약/HTTP로 검증했으며, 브라우저 도구 연결 불가로 마지막 시각 재확인은 미완료다. 앞선 지도/거리 브라우저 검증과 구분한다.
- PR의 검증/남은 작업을 명시하고 사용자 요청 범위에서 squash 병합한다. 배포는 하지 않는다. 병합 완료 여부와 링크는 PR 자체가 최종 근거다.

## 2026-11-21 센터 공식 상세 정보 보강

- feat/center-official-content에서 공식 intro/notice 페이지 수집기와 API official 필드를 추가.
- 공식 사이트 17곳 모두 실제 수집 성공. 운영시간 17건, 공지 최근 10개씩 170건. 제목·등록일·원문 링크 제공; 모바일 연락처·폼 링크 미포함 검사.
- 날짜/형식 확인 없이 HTTP 200만 성공 처리하지 않음. 오류 페이지는 파싱 실패, 이전 성공 데이터 유지. 공지 실패 시 기존 목록과 확인 시각 유지.
- parser/API 관련 unittest 8개 통과. 실제 Vite 프록시에서 중구 운영시간·이용방법·공지를 확인.
- 정적 파일 데이터이며 개인 DB/스키마 변경 없음. 런타임 정기 갱신은 기존 일일 파이프라인 실행 시 수행. 자동 배포/스케줄러 설치는 하지 않음.

## 2026-11-21 개별 센터 정보 보완·최종 검증

- 개별 센터 17곳의 홈페이지와 공식 지자체 안내 재검토. 운영시간 12곳과 공지 게시판 링크 9곳 보완. 노량진·도봉청년취업·도봉창업의 공식 주소 반영.
- 운영시간 미확인: 구로 청년이룸, 노원 일삶, 청년내일, 노원청년정책거버넌스, 종로청년창업. 추정값이나 프로그램 운영시각을 대체 입력하지 않음.
- 구로 홈페이지는 HTTP 접근은 가능하지만 HTTPS 인증서 오류가 있어 출처는 기존 구로구 공식 안내를 유지. 노량진 홈페이지 연결 시간 초과는 공식 지자체/검색에서 확인된 안내로 보완. 일부 기관 블로그 프레임/인스타그램은 운영시간을 확인할 수 없음.
- 실제 Chrome 데스크톱·모바일에서 프론트 연동 및 관악청년청 지도 타일 로드 확인. backend 센터 관련 unittest 9개 통과.
- 공식 소개에서 제거된 예약 링크의 빈 라벨을 정리. 개인정보·폼 링크 추가 없음. 사용자 요청으로 한국어 커밋만 수행하며 푸시·PR·병합·배포 없음.

### 대화 우선 흐름 (2026-11-22)
- FE의 상시 추천 버튼 제거. BE에서 상황만 말할 때 탐색 제안으로 강제 전환하던 규칙과 막힌 답에 자동 추천을 붙이는 규칙을 대화 확인 질문으로 변경. 명시적 추천·검색은 유지.
- 검증: FE 빌드, BE 대화 unittest 20개. 로컬 적용, 배포하지 않음.

### 대화 프로그램 후보 선별 (2026-11-22)
- 프로그램·교류 활동 요청에서는 정책 제외, 기존 검색/추천 후보 내 문화·교류·소모임 근거로 최대 3개 선별. 큰 행사 부담 시 행사 제목 감점.
- 추천 이유를 공고 근거로 표시하며 인원 미확인 시 소규모 확정 금지. 후보 전체를 재검색하는 최적화는 아님.
- 검증: 대화/선별 unittest 22개, FE 빌드, 실제 FE 프록시 요청 200/정책0/프로그램3 및 미확인 조건 표시 확인. 로컬 적용, 배포하지 않음.

### 공고 기반 활동 설명 (2026-11-22)
- 추천 카드에 원문을 다시 읽은 활동 요약·사용자 선호와의 연결·개최 장소·활동 시간 표시. 신청 기간과 활동 시간을 구분.
- 사용자에게 확인을 떠넘기는 카드 문구 제거. 원문에 없는 장소·시간은 미기재로 표시하며 규모·부담 적음의 근거 없는 단정은 차단.
- 검증: FE 빌드, BE 대화/후보 테스트 22개, 실제 AI API 200 및 후보별 설명 생성 확인. 추가 요약 LLM 호출로 지연이 늘 수 있음. 로컬 구현, 배포하지 않음.

### 해요체·시연 초기화 (2026-11-22)
- 카드 요약/추천 이유에 해요체 지시 강화. 개발 화면에 시연 데이터 초기화 버튼 추가(둘셋 로컬 저장값·대화 이력·CacheStorage 제거).
- 사용자 요청으로 초기화 실행, 마이페이지의 생년월일·거주지 미등록/맞춤 설정 선택 안 함 확인. FE 빌드·BE 테스트 22개 통과.

### 공고 대화 응답 복구 (2026-11-22)
- 일정 입력 도중 신청·설명 등 다른 질문을 날짜 입력으로 가로채던 문제 수정. 공고 선택 후 일반 대화의 고정 문구 경로 제거.
- chat 요청에 selected_item_id 추가, BE가 해당 공고의 공개 원문을 읽고 답변하도록 연결. 세부 조회 실패가 전체 채팅 입력을 차단하지 않도록 보완.
- 검증: BE 대화/선별 테스트 22개·FE 빌드 통과. 브라우저에서 선택 공고 질문→실제 AI 설명, 일정 등록→설명 질문 전환 후 날짜 재질문 없이 답변 확인. 로컬 적용, 배포하지 않음.

## 2026-11-23 공고 품질·취업 신청 시연

- 전체 본문 보존, 메일/인사/연락처 정리, 필드별 AI 추출과 원문 인용 검증, 내용/버전 캐시, 실패 시 이전 결과 보존. 검증된 사실 127/137개를 기본 서비스 데이터에 포함. 원문 미확보 9개·근거 미충족 1개는 실패로 유지.
- 목록·추천·상세·대화·FE 스냅샷 공통 표시. 대화마다 원문을 재요약하던 임시 호출 제거.
- 직접 자소서/면접 피드백 요청을 전체 지역 후보에서 선별. 부적합 프로그램·지난 활동 제외, 새 정책 요청의 이전 프로그램 맥락 분리.
- 선택 공고/저장 조건 기반 실제 AI 답변, 문의 대본/문의 일정 선택지, FE 로컬 채움·치환·AI 미리보기·동기 초안·최종 확인. 폼 revision 변경 시 외부 제출 전 중단.
- 실제 브라우저에서 대화→정보 입력→자동 추천→공고 질문/자격/준비→팀 소유 테스트 폼 최종 확인(미제출)→마감 폼→문의 대본→문의 일정 미리보기/저장→달력 표시·새로고침/이력 복원 확인. 모바일 화면과 선택지 확인.
- 실제 열린 폼은 베이킹 테스트이므로 취업 공고와 분리. 외부 제출·편집 링크 사용·배포·병합 없음. 테스트 폼 주소/설정·원문·캐시는 Git 제외.

## 취업 테스트 폼 실제 접수 검증 (2026-11-23)

사용자 승인 후 팀 소유 취업 테스트 폼을 생성·게시하고 로컬 설정의 `demo:career`로 연결했다. 8개 필수 문항과 가상 클래스 안내, 이메일 수집 안 함, 응답 요약 비공개를 설정했다. FE에서 가상 정보 입력 → AI 입력 미리보기 → 실제 AI 초안 생성/수정 → 직접 테스트 동의 → 최종 확인 → 제출을 진행했다. 00:24 KST 서버 접수 성공과 Google Forms 응답 1개 및 모든 답변 일치를 확인했다. 추가 제출은 하지 않았다. 실제 기관 신청·배포·병합은 하지 않았다. 폼 주소/연결 설정은 Git 제외 로컬 파일에만 두었다. 기존 베이킹·마감 폼 설정을 유지했다.

## 취업 정책 누락과 설명 보완 (2026-11-23)

프로그램 큐레이션이 정책 배열을 무조건 비우던 원인을 수정했다. 취업 관련 요청은 전체 지역/나이/자격 후보에서 관련 취업 정책 1개를 함께 선별하며 전체 카드 수는 3개 이하로 유지한다. 프로그램만 또는 정책 제외 요청은 정책을 추가하지 않는다. 실제 API에서 중구 전문가 상담과 국민취업지원제도가 함께 나오는 것을 확인했다. 소득/재산 미확인 조건을 최종 자격 확정으로 설명하지 않는다. 설명 프롬프트와 말풍선 상한을 늘려 지원 내용/준비/다음 행동을 충분히 안내한다. 전체 unittest 144개 통과. 프론트 문항별 신청은 추가 외부 제출 없이 최종 확인까지 검증했다.

## 자격 설명 후 신청 제안 (2026-11-23)

선택 공고의 신청 가능 여부를 물으면 근거에 따른 답변 뒤 현재 공고의 신청 준비 제안과 신청 같이하기 선택지를 제공한다. 다른 지원 추천으로 이탈하는 문장은 제거한다. 관련 chat 회귀 23개 통과. 실제 브라우저에서 AI 답변과 신청 선택지 연결을 확인했다.

## 대화 길이 복구와 카드 누락 수정 (2026-11-23)

최근 공고 설명을 3~6문장으로 늘리던 지시를 되돌리고 보통 1~2문장으로 답하게 했다. 추천 요청 전에는 구체적 프로그램/신청 권유가 나오지 않도록 방어한다. 이전 선택 공고가 남아도 명시적인 새 추천/찾아줘 요청은 선택 문맥을 해제하고 추천을 실행한다. 대화/큐레이션 회귀 28개 통과.
