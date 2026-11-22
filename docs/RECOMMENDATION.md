# 정책·프로그램 추천

청년정책(온통청년)과 청년센터 프로그램을 같은 기준으로 분류하고, 사용자의 상태 체크 답변과 기본 정보에 맞춰 추천한다. 2026-11-19 기준이다.

- 구현 완료: 수집·분류 파이프라인, `catalog_items` 테이블, 적재 스크립트, 상태 체크·추천 API, 파일 fallback
- 계획: 매일 실행 스케줄러(서버 안 또는 외부 cron), 운영 DB 적재, AI 비서 대화와의 연결
- 배포: 아직 하지 않음

관련 문서: [POLICY_FIELDS.md](POLICY_FIELDS.md) · [CENTER_FIELDS.md](CENTER_FIELDS.md) · [DATA_FIELDS.md](DATA_FIELDS.md) · [CRAWLER.md](CRAWLER.md) · [DATA_CHECK.md](DATA_CHECK.md)

## 1. 전체 흐름

```text
[매일]  pipeline/run_daily.py
  정책: policies/fetch.py (온통청년 API) → policies/classify.py (규칙 + LLM, 캐시)
  센터: programs/crawl/sync_centers → seoul_orang → gnuboard → merge → programs/classify.py
  → data/runtime/serving/*.json → pipeline/load_catalog.py → catalog_items (PostgreSQL)

[요청]  POST /api/recommendations
  catalog_items 기본 필터(SQL) → 자격 규칙 → 점수 → 정책 6 · 프로그램 4
  DB가 없거나 비어 있으면 serving JSON으로 같은 계산 (응답 source = "file")
```

추천 계산에는 LLM을 쓰지 않는다. LLM은 하루 한 번 분류에만 쓰고, 결과는 캐시해서 바뀐 글만 다시 분류한다. 같은 입력이면 항상 같은 추천이 나온다.

### 폴더

| 경로 | 내용 | Git |
| --- | --- | --- |
| `pipeline/` | 수집·분류·적재 스크립트 | O |
| `data/seed/` | 첫 실행·CI·DB 없는 환경용 결과물 (serving JSON, 분류 캐시, 센터 목록) | O |
| `data/runtime/` | 매일 실행 결과 | X (gitignore) |
| `app/catalog/` | `catalog_items` 모델, 행 변환, upsert, 후보 조회 | O |
| `app/checkin/` | 상태 체크 문항과 요약 | O |
| `app/recommend/` | 자격·점수 규칙, 서비스, API | O |
| `tools/data_check/` | 원본 API 조사 스크립트 (결과는 `data/runtime/data_check/`) | O |

### 실행

```bash
# .env에 YOUTH_POLICY_API_KEY, YOUTH_CENTER_API_KEY, OPENAI_API_KEY 입력
python -m pipeline.run_daily              # 수집 → 분류 → DB 적재
python -m pipeline.run_daily --no-llm     # 캐시에 있는 분류만 사용
python -m pipeline.load_catalog --seed    # 키 없이 seed 데이터만 DB에 넣기
python scripts/recommend_demo.py          # 페르소나 5명 추천 결과 (파일 기준)
```

첫 실행(서울청년센터 결과 파일이 없을 때)은 `run_daily`가 자동으로 목록 전체를 받는다. 운영 기준과 개발용 실행 방법 전체는 README "데이터 파이프라인".

## 2. 왜 이렇게 저장하나

정책·프로그램은 **테이블 하나(`catalog_items`) + JSONB**로 둔다. 2026-11-19 결정.

| 방식 | 장점 | 단점 |
| --- | --- | --- |
| JSON 파일만 | 단순, DB 없이 동작 | 요청마다 수천 건을 읽고 거름. 마감·지역 필터를 매번 파이썬으로. 이력(언제 처음 봤나, 언제 닫혔나) 없음 |
| 정규화 테이블 여러 개 | 조회가 가장 정확 | 원본 필드가 많고 자주 바뀌어서 마이그레이션 부담이 큼. 해커톤 일정에 맞지 않음 |
| **테이블 하나 + JSONB (선택)** | 필터에 쓰는 컬럼(나이·지역·영역·상황·마감·상태)만 컬럼으로, 나머지 원본은 `payload`에 통째로. 지역은 GIN 인덱스. 사용자·신청 이력과 같은 DB에서 조인 가능 | 필터 컬럼을 추가하면 마이그레이션 필요 |

SQLite는 파일 하나라 JSON과 운영상 차이가 크지 않고, 레포가 이미 PostgreSQL 17로 정해져 있어서 쓰지 않는다.

로컬·CI에서 PostgreSQL을 Docker로 띄우는 이유: 운영과 같은 버전·기능(ARRAY, JSONB, GIN)을 모든 팀원 PC와 CI에서 똑같이 재현하기 위해서다. 운영은 관리형 PostgreSQL을 쓰고 앱은 `DATABASE_URL`만 바꾼다.

### `catalog_items`

| 컬럼 | 설명 |
| --- | --- |
| `id` | `policy:{plcyNo}` / `program:{program_id}` |
| `kind` | policy / program |
| `status` | ok / hold / excluded / closed |
| `title`, `age_min`, `age_max`, `deadline`, `access_type` | 필터·표시용 |
| `region_cds` (ARRAY, GIN) | 정책: 시군구 코드 목록 / 프로그램: 센터 시군구 |
| `sido_cds` (ARRAY, GIN) | 시도 코드 앞 2자리 |
| `domains`, `situations` (ARRAY) | 분류 결과 |
| `source_hash` | serving 항목의 SHA-256. 매일 바뀌는 조회수 `inqCnt`는 뺀다(`rows.VOLATILE_FIELDS`) |
| `payload` (JSONB) | serving JSON 항목 전체 |
| `first_seen_at` | 처음 적재한 시각 |
| `updated_at` | 내용(해시)이나 상태가 마지막으로 바뀐 시각. 조회수만 바뀐 날은 그대로 |

### `catalog_item_changes` (변경 이력, migration 0003)

| 컬럼 | 설명 |
| --- | --- |
| `id` | BIGINT identity |
| `item_id` | `catalog_items.id` (FK, 항목 삭제 시 함께 삭제) |
| `kind` | policy / program |
| `change_type` | created / updated / reopened / closed |
| `old_hash`, `new_hash` | 바뀌기 전·후 `source_hash` |
| `changed_fields` (TEXT[]) | 값이 달라진 payload 최상위 필드 (예: `aplyYmd`, `title`) |
| `old_payload` (JSONB) | updated·reopened(내용도 바뀐 경우)일 때 바뀌기 전 payload |
| `changed_at` | 기록 시각 |

인덱스: `(item_id, changed_at)`(항목별 이력), `changed_at`(기간별 조회). 보관 기간·정리는 아직 정하지 않았다.

적재(`app/catalog/load.py`): 기존 행의 `source_hash`·`status`와 비교해 나눈다.

| 경우 | 처리 | 이력 |
| --- | --- | --- |
| 처음 보는 id | INSERT | `created` |
| 해시가 다름 | 필터 컬럼·payload 갱신, `updated_at` 갱신 | `updated` + 이전 payload·바뀐 필드 |
| 닫혔던 id가 다시 나타남 | `status='ok'`, `updated_at` 갱신 | `reopened` (내용도 바뀌었으면 이전 payload) |
| 해시 같음 | 조회수 등 해시 밖 값, 변환 규칙이 바뀐 파생 컬럼(예: `deadline`)만 반영, `updated_at` 그대로. 저장 컬럼이 모두 같으면 쓰지 않음 | 없음 |
| 오늘 목록에 없음 | `status='closed'` | `closed` |

반환값은 `{received, created, updated, reopened, unchanged, closed, previously_active}`. 오늘 건수가 기존 ok 건수의 50% 미만이면 수집 실패로 보고 적재하지 않는다(`--force`로 무시). 종류별로 한 트랜잭션이라 실패하면 기존 데이터와 이력이 그대로 남는다.

LLM 재분류는 적재와 별개로 앞 단계 캐시가 정한다(정책: `plcyNo`+`lastMdfcnDt`+프롬프트 버전, 프로그램: 제목·요약 해시). 해시 계산 방식을 바꾼 뒤 첫 적재에서는 기존 행이 모두 `updated`(바뀐 필드 없음)로 한 번 기록된다.

## 3. 분류 기준

정책과 프로그램에 같은 태그를 붙인다.

### `i5_domains` — 어떤 어려움을 덜어주나 (0~2개, 주 영역이 앞)

| 코드 | 영역 | 예 |
| --- | --- | --- |
| E | 경제 | 일자리, 창업, 주거비, 대출, 자산형성, 출산·육아 지원금 |
| P | 모임 참여 | 동아리, 소모임, 커뮤니티, 봉사 |
| O | 외출·여가 | 문화패스, 공연·전시, 체육, 클래스 |
| C | 사람과의 교류 | 만남 프로그램, 소셜다이닝, 네트워킹 |
| U | 도움·상담 | 심리상담, 고립·은둔 지원, 법률·노무·재무 상담, 돌봄 |

### 나머지 태그

- `access_type`: apply(신청·모집) / visit(가서 이용) / none(시설 조성·공지·결과 발표 → 제외)
- `situations`: 임신·출산, 육아, 기혼, 미혼, 한부모가정, 가족돌봄청년, 자립준비청년, 기초생활수급자, 장애인, 군인, 농업인, 중소기업재직, 여성, 지역인재. 정책은 원본 코드(`sbizCd`, `mrgSttsCd`)와 키워드로 규칙이 먼저 붙이고 LLM이 확정한다.
- `topics`: 프로그램 전용 관심 분야 0~2개 (정책은 중분류로 연결)
- `confidence` high/low, `status`: none → excluded, 영역 없음·확신 낮음 → hold, 나머지 ok. 수동 보정 대신 **애매하면 보류**로 정했다.

현재 seed: 정책 ok 2,335건, 프로그램 ok 169건 (프로그램은 대부분 서울).

## 4. 상태 체크 (레포 요구사항 방식)

`docs/requirements.md`의 선택형 현재 상태 체크를 따른다. 2026-11-19 결정: 이전에 검토한 I5 11문항 또래 비교 방식 대신 레포 방식. 이유는 진단처럼 보이지 않고, 문항이 짧고, 점수·위험 등급을 만들지 않기 때문이다.

- 영역 5문항(경제·모임 참여·외출·교류·도움) — 각각 높음/보통/낮음 + 공통 `잘 모르겠어요`·`건너뛰기`·`나중에`
- 추가: 만족도, 바꾸고 싶은 영역(복수), 대면 부담, 관심 분야(최대 3)

요약 규칙(`app/checkin/summary.py`):

- 영역 수준은 사용자 답 그대로. 모름·건너뛰기·나중에는 수준 없음
- 바꾸고 싶은 영역을 골랐으면 고르지 않은 영역은 한 단계 낮춤
- 모임 참여 어려움이 높으면 경제를 최소 보통으로 (모임 비용 부담 반영)
- 점수나 위험 등급은 내지 않는다. 응답에 "진단이 아님" 안내 포함

## 5. 추천 알고리즘 (`app/recommend/rules.py`)

0. **지역 코드 확인**: `sigungu_cd`가 원본(온통청년) 코드 목록에 없으면 422 `Unknown sigungu_cd`. 원본은 행정구역 개편 뒤 코드를 쓴다(광주·전남 통합 `12xxx`, 강원 `51xxx`, 전북 `52xxx`). 옛 코드(예: 곡성 `46720`, 지금은 `12720`)를 받으면 후보가 0건이 되므로 조용히 빈 결과를 주지 않는다. 받는 코드는 거주지 목록 `app/catalog/regions.py`(256개, `GET /api/regions`, [REGIONS.md](REGIONS.md))와 같다. 원본 정책 일부는 개편 전 코드(화성시 `41590`, 천안시 `44130`, 인천 중·동·서구, 대전 전체 `30000`)로만 지역을 표시하므로, 매칭할 때 사용자 코드에 그 지역의 옛 코드를 더한다(`regions.match_codes`, DB는 배열 overlap). 서비스 데이터에 목록에 없는 새 코드가 생기면 `tests/test_regions.py`가 실패한다.
1. **기본 필터** (SQL): status ok, 마감 안 지남, 나이 포함, 지역. 정책은 사용자 시군구 코드가 `region_cds`에 있어야 하고, 프로그램은 같은 시군구 또는 같은 시도 센터. 정책 마감일은 신청기간(`aplyYmd`) 끝, 신청기간이 비어 있으면 사업 종료일(`bizPrdEndYmd`).
2. **자격 규칙**: 특정 대상 사업 제외(제목에 자살시도자·중독자·외국인근로자·전세사기/전세피해·다문화·북한이탈·제대군인·경계선지능 — 기본 정보로 확인할 수 없는 대상, `rules.SPECIAL_TARGET`), 직업(`jobCd`), 학력(`schoolCd`), 자격 상황(GATE: 모두 해당해야), 생애 단계 상황(STAGE: 하나만 해당해도).
3. **점수**: 영역 수준 높음 30 / 보통 18 (주 영역 만점, 보조 영역 절반) · 관심 분야 +10 · 상황 일치 +10 · 지역(정책 시군구 +4, 광역 +2 / 프로그램 같은 구 +10) · 상시 프로그램 −4 · 대면 부담 높음 −8, 보통 −3 (모임·교류 영역이나 방문형) · 조회수로 동점 정리
4. **정리**: 제목 중복 제거, 영역당 최대 3개(관심 영역이 하나뿐이면 예외), 정책 6개·프로그램 4개. 항목마다 추천 이유 문장.

가중치는 데모 기준 초안이다. 실제 사용자 반응을 보고 조정한다.

**관심 분야 자리 보장 (2026-11-21):** 관심 분야 +10이 영역 점수보다 약해, 외출·대화가 높은 구직자가 '일자리·취업'을 골라도 일자리 정책이 0개였다(후보 24개 중 최고 13점, 6위 17.9점). 가중치는 그대로 두고, 고른 관심 분야가 목록에 하나도 없으면 그 분야의 가장 높은 항목을 목록 맨 뒤(관심 분야와 무관한 항목)와 바꾼다. 최대 2개 (`rules._keep_interests`).

### API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/regions` | 거주지 시군구 목록 `{regions: [{code, sido, sigungu, label}]}`. FE는 `code`를 `profile.sigungu_cd`로 보낸다 |
| GET | `/api/checkin/questions` | 문항 목록 |
| POST | `/api/checkin/summary` | `{answers}` → 영역 수준 요약. 잘못된 답은 422 |
| POST | `/api/recommendations` | `{profile, checkin}` → `summary`, `policies`, `programs`, `source` |

`profile`: age, sex, sigungu_cd(5자리), job, school, situations.

응답 추가 필드:

- 정책 `income_condition`: 소득 조건. **추천에서는 소득으로 거르지 않고**, 사용자가 신청하려 할 때 FE가 확인한다(소득은 묻지도 저장하지도 않는다).
  - `null`: 소득 무관
  - `{"kind": "annual_income", "max_manwon": 5000, "text": "연소득 5,000만 원 이하"}`: 상한이 숫자 → 예/아니요 한 번
  - `{"kind": "other", "max_manwon": null, "text": "청년가구 중위소득 150% 이하"}`: 원문 설명 → 그대로 보여줌
  - 추천 대상 정책 1,059건 기준 무관 895 · 연소득 24 · 기타 139 (2026-11-19 seed)
- `programs_notice`: 프로그램이 0건일 때 이유. `null`(프로그램 있음) / `no_program_data`(이 지역 센터 프로그램을 아직 모으지 못함 — 서울 밖 대부분) / `no_program_match`(데이터는 있지만 조건에 안 맞음). `message`는 화면에 그대로 쓸 수 있는 문구.

## 6. 고친 문제 기록

| 문제 | 처리 |
| --- | --- |
| 특화분야 코드가 안 들어감 (`sBizCd` → 실제 `sbizCd`) | 필드명 수정 |
| 나이 상한 0을 '0세까지'로 처리 (1,127건) | 0 → 제한 없음 |
| 지자체 정책 90건이 전국 지역코드 | 등록기관 시도로 좁힘 |
| '창업보육'이 육아로 분류 | 규칙·serving 양쪽 보정 |
| 상황 하나만 겹쳐도 한부모 정책 통과 | 자격 상황 / 생애 단계 분리 |
| 영역 2개 정책이 점수를 두 번 받음 | 주 영역 만점·보조 절반, 영역당 3개 |
| 프로그램 22%가 지난 글 | 제목 날짜·글번호로 거름, 상시 서비스는 유지. 2026-11-21: 마감일·진행 종료일이 없는 글은 본문 요약의 날짜(예: "26. 8. 27.", "2026년 9월 12일")도 보고, 모두 지났으면 제외 (상담·공간 같은 상시 서비스 제목은 제외하지 않음). 9월 체육대회·8월 북캉스 등 14건 |
| **ok 정책 1,268건이 신청기간(`aplyYmd`)이 이미 지남** | 기본 필터에서 마감일 비교 (백엔드 이식 중 발견) |
| 신청기간이 비어 있으면 사업이 끝났어도 통과 (9건, 예: 9월에 끝난 은평청년축제) | 신청기간이 없으면 사업 종료일을 마감일로 (페르소나 점검 중 발견) |
| 자살시도자 치료비·중독자 치료 등 특정 대상 사업이 일반 사용자에게 추천됨 (예: 지원망 high 응답자에게 자살시도자 치료비) | 제목 기준 특정 대상 제외. 자격 조건 원문은 '국가유공자 우대'처럼 여러 대상 중 하나로 적힌 경우가 많아 쓰지 않음 |
| 옛 시군구 코드(46720 등)를 받으면 조용히 0건 | 원본 코드 목록에 없으면 422 |

## 7. 남은 과제

- 매일 실행 스케줄러 연결 (FastAPI 안 스케줄러 vs 외부 cron — 배포 환경 정해지면 결정)
- 지역 편중: 프로그램은 대부분 서울(서울청년센터 통합 사이트 144건). 서울 밖은 그누보드로 만든 센터 13곳만 읽을 수 있어 25건(경기·충북·경남·강원·전북 일부)뿐이고, 나머지 센터는 자체 사이트·SNS라 지금 크롤러로 못 읽는다. 다른 지역은 정책만 나오고 `programs_notice`로 이유를 알린다. 늘리려면 지역 통합 플랫폼·사이트별 크롤러 추가
- 소득 조건 확인 화면(FE): `income_condition`으로 신청 직전에 확인
- 원본 오류: 나이 상한·상황 태그가 빠진 '청소년쉼터 퇴소청소년 수당', 안산 센터로 연결된 '구로청년이룸' 글
- v3에서 재사용한 분류 541건 재검토 옵션(`--recheck-reused`) 미구현
