# 정책 데이터 필드 정리

> 로컬 `ai_hackathon` 폴더에서 옮겨 온 문서다. 경로는 저장소 구조 기준으로 바꿨다 (2026-11-19). 추천 전체 흐름은 [RECOMMENDATION.md](RECOMMENDATION.md).

정책 데이터 파이프라인: `pipeline/policies/fetch.py` → `pipeline/policies/classify.py`
원본 필드의 자세한 형식·주의사항은 `docs/POLICY_FIELDS.md`를 참고한다.

## 출력 파일

| 파일 | 만드는 스크립트 | 1행 = | 용도 |
|---|---|---|---|
| `data/runtime/policies/policies_raw.jsonl` | export | 정책 1건 (API 원본) | 재처리용. 버리지 않는다 |
| `data/runtime/policies/policies.csv` | export | 정책 1건 | 원본 필드 + 정리 필드 + `situations` |
| `data/runtime/policies/policy_regions.csv` | export | 정책 × 시군구 | `plcyNo`, `zipCd` — 거주지 조건 필터 |
| `data/runtime/policies/policy_codes.csv` | export | 정책 × 요건코드 | `plcyNo`, `kind`(취업/학력/전공/특화), `code`, `name` |
| `data/runtime/policies/fill_rate.csv` | export | 필드 1개 | 채움률 (전체 / 마감 제외) |
| `data/runtime/policies/policy_tags.csv` | enrich | 정책 1건 (마감 제외) | `i5_domains`, `access_type`, `situations`(확정), `confidence`, `status` |
| `data/runtime/serving/policies_serving.json` | enrich | 정책 1건 (`status = ok`만) | **서비스용.** 화면·추천 필드 + 분류 태그, 담당자 이름 제외 |
| `data/runtime/cache/policy_tags_cache.jsonl` | enrich | 정책 1건 | LLM 결과 캐시 (`plcyNo` + `lastMdfcnDt` + 프롬프트 버전 기준) |

## 우리가 추가한 필드

| 필드 | 파일 | 설명 | 만드는 방법 | 넣는 위치 |
|---|---|---|---|---|
| `*_nm` (`aplyPrdSeCd_nm` 등 7개) | policies.csv | 단일 코드값의 이름 | 코드표(API코드정보.xlsx) 매핑 | export 중 바로 |
| `jobCd_nm` / `schoolCd_nm` / `plcyMajorCd_nm` / `sbizCd_nm` | policies.csv | 다중 코드값의 이름 (쉼표 구분) | 코드표 매핑 | export 중 바로 |
| `age_min_clean` | policies.csv | 최소 나이. 빈값 = 제한 없음 | `sprtTrgtMinAge` 0 → 빈값 | export 중 바로 |
| `age_max_clean` | policies.csv | 최대 나이. 빈값 = 제한 없음 | `sprtTrgtMaxAge` 0·99 이상 → 빈값 | export 중 바로 |
| `earn_max_clean` | policies.csv | 소득 상한(만원). 빈값 = 제한 없음 | `earnMaxAmt` 99999 이상 → 빈값 | export 중 바로 |
| `is_closed` | policies.csv | 신청 마감 여부 | `aplyPrdSeCd` = 마감 | export 중 바로 |
| `region_count` | policies.csv | 거주지 요건 시군구 수 (많으면 사실상 전국) | `zipCd` 개수 | export 중 바로 |
| `situations` (규칙) | policies.csv | 특정 상황인 사람만 해당되는 정책의 상황. 빈값 = 누구나 | 아래 규칙 | export 중 바로 |
| `i5_domains` | policy_tags.csv | 정책이 덜어주는 어려움 (E/P/O/C/U, 0~2개) | LLM 분류 | enrich (별도 단계) |
| `access_type` | policy_tags.csv | 청년이 어떻게 이용하나 (`apply` / `visit` / `none`) | LLM 분류 | enrich (별도 단계) |
| `situations` (확정) | policy_tags.csv | 위 규칙 태그를 힌트로 LLM이 확정한 상황 | LLM 분류 (규칙 힌트) | enrich (별도 단계) |
| `confidence` | policy_tags.csv | LLM 자체 확신도 (`high` / `low`) | LLM 분류 | enrich (별도 단계) |
| `status` | policy_tags.csv | `ok` 서비스 사용 / `hold` 보류 / `excluded` 제외 | 아래 규칙 | enrich (별도 단계) |
| `model` | policy_tags.csv | 분류에 쓴 LLM 모델명 | 실행 설정 | enrich (별도 단계) |

### `situations` 규칙 (export)

| 상황 태그 | 근거 |
|---|---|
| 군인 · 한부모가정 · 기초생활수급자 · 장애인 · 여성 · 농업인 · 중소기업재직 · 지역인재 | `sbizCd` 특화분야 코드 (제한없음·기타 제외) |
| 기혼 · 미혼 | `mrgSttsCd` (0055001 / 0055002) |
| 임신·출산 · 육아 | `plcyKywdNm` 키워드 `출산`·`육아` (키워드가 7개 이상 붙은 정책은 무시) |
| 임신·출산 · 육아 · 군인 · 한부모가정 · 장애인 · 자립준비청년 · 가족돌봄청년 | 정책명 키워드 (임신·난임·산후 / 육아·양육 / 군복무·장병 등) |

원본 코드가 틀린 경우가 있다(예: 미혼 코드가 붙은 신혼부부 정책, 출산 키워드가 붙은 결혼장려금). 그래서 추천에는 enrich가 확정한 `policy_tags.csv`의 `situations`를 쓰고, 규칙 태그는 LLM 힌트와 fallback으로만 쓴다.

### `i5_domains` 기준 (enrich)

| 코드 | 영역 | 해당하는 정책 |
|---|---|---|
| E | 경제 | 소득·일자리·창업·생활비·주거비·대출·자산형성·출산/육아 지원금 |
| P | 모임 참여 | 동아리·소모임·커뮤니티·봉사 등 단체 활동 기회 |
| O | 외출·여가 | 문화·체육·여행·여가 활동 계기 (문화패스, 공연·체험) |
| C | 사람과의 교류 | 만남·교류 프로그램, 청년공간 네트워킹 |
| U | 도움·상담 | 심리상담, 마음건강, 고립·은둔 지원, 위기 지원, 생활 돌봄 |

### `status` 규칙 (enrich)

| status | 조건 | 서비스 |
|---|---|---|
| `excluded` | `access_type = none` | 제외 |
| `hold` | `i5_domains` 없음, `confidence = low`, 또는 `access_type` 없음 | 보류 (서비스 제외, 나중에 검토) |
| `ok` | 나머지 | `policies_serving.json`에 포함 |

### `access_type` 기준 (enrich)

| 값 | 의미 | 예 | 추천 |
|---|---|---|---|
| `apply` | 신청·선정을 거쳐 받는 혜택 | 지원금, 대출이자, 바우처, 프로그램 참가자 모집 | 신청 준비로 연결 |
| `visit` | 가서 이용·참여하는 공간·행사·센터 | 청년공간, 청년주간·축제, 일자리센터 상담 | 외출(O)·교류(C) 추천에 특히 적합 |
| `none` | 개인이 이용할 수 없음 | 시설 조성, 대회 유치, 위원회, 기업 육성, 종사자 대상 | 추천에서 제외 |

## 원본 필드 (온통청년 청년정책 API)

| 묶음 | 필드 | 설명 | 추천에서 쓰는 곳 |
|---|---|---|---|
| 식별 | `plcyNo` | 정책번호 (PK, 20자리) | 모든 표의 연결 키 |
| 식별 | `plcyNm` | 정책명 | 카드 제목 |
| 분류 | `lclsfNm` / `mclsfNm` | 대분류 / 중분류 (쉼표 위치로 짝, 2025 등록분은 옛 체계) | LLM 입력 |
| 분류 | `plcyKywdNm` | 키워드 17종 (쉼표 구분) | `situations` 규칙 |
| 분류 | `plcyPvsnMthdCd` | 제공방법 | 표시 |
| 분류 | `pvsnInstGroupCd` | 제공기관 그룹 (중앙부처/지자체) | 표시 |
| 분류 | `plcyAprvSttsCd` | 승인상태 (전부 승인) | - |
| 분류 | `bscPlanCycl` / `bscPlanPlcyWayNo` / `bscPlanFcsAsmtNo` / `bscPlanAsmtNo` | 청년정책 기본계획 차수·방향·중점과제·과제 | - |
| 내용 | `plcyExplnCn` | 정책 설명 (요약) | 카드 설명, LLM 입력 |
| 내용 | `plcySprtCn` | 지원 내용 | 상세, LLM 입력 |
| 신청 | `plcyAplyMthdCn` | 신청 방법 | 상세, 신청 준비 |
| 신청 | `srngMthdCn` | 심사 방법 | 상세 |
| 신청 | `sbmsnDcmntCn` | 제출 서류 | 서류 준비 |
| 신청 | `etcMttrCn` | 기타 사항 | 상세 |
| 신청 | `aplyUrlAddr` | 신청 URL (일부 `http://` 없음) | 신청 버튼 |
| 신청 | `refUrlAddr1` / `refUrlAddr2` | 참고 URL | 출처 링크 |
| 기간 | `aplyPrdSeCd` | 신청기간 구분 (특정기간/상시/마감) | `is_closed` |
| 기간 | `aplyYmd` | 신청기간 (`YYYYMMDD ~ YYYYMMDD`) | 마감일 표시·정렬 |
| 기간 | `bizPrdSeCd` / `bizPrdBgngYmd` / `bizPrdEndYmd` / `bizPrdEtcCn` | 사업기간 구분·시작·종료·기타 | 표시 |
| 자격 | `zipCd` | 거주지 요건 시군구 코드 (쉼표 구분, 운영 지역 아님) | 지역 필터 (`policy_regions.csv`) |
| 자격 | `sprtTrgtMinAge` / `sprtTrgtMaxAge` | 나이 범위 (0 = 제한 없음) | `age_*_clean` |
| 자격 | `sprtTrgtAgeLmtYn` | 나이 제한 여부 (일관되지 않음) | 쓰지 않음 |
| 자격 | `mrgSttsCd` | 결혼상태 | `situations` |
| 자격 | `earnCndSeCd` / `earnMinAmt` / `earnMaxAmt` / `earnEtcCn` | 소득조건 구분·범위(만원, 일부 원 단위)·서술 | 자격 확인 안내 |
| 자격 | `plcyMajorCd` / `jobCd` / `schoolCd` / `sbizCd` | 전공·취업상태·학력·특화분야 (여러 개) | 자격 필터 (`policy_codes.csv`) |
| 자격 | `addAplyQlfcCndCn` | 추가 자격 서술 (거주 기간 등) | 확인 필요 안내 |
| 자격 | `ptcpPrpTrgtCn` | 참여 제한 대상 | 확인 필요 안내 |
| 규모 | `sprtSclLmtYn` / `sprtSclCnt` | 규모 제한 여부 / 지원 인원 (0 = 미기재) | 표시 |
| 규모 | `sprtArvlSeqYn` | 선착순 여부 | 표시 |
| 기관 | `sprvsnInstCd` / `sprvsnInstCdNm` | 주관기관 | 표시, 문의처 |
| 기관 | `sprvsnInstPicNm` | 주관기관 담당자 | ⚠ 개인 이름, 화면 노출 금지 |
| 기관 | `operInstCd` / `operInstCdNm` | 운영기관 | 표시, 문의처 |
| 기관 | `operInstPicNm` | 운영기관 담당자 | ⚠ 개인 이름, 화면 노출 금지 |
| 기관 | `rgtrInstCd` / `rgtrUpInstCd` / `rgtrHghrkInstCd` (+ `Nm`) | 등록기관 / 상위 / 최상위 | - |
| 기타 | `inqCnt` | 조회수 | 인기순 정렬 |
| 기타 | `frstRegDt` / `lastMdfcnDt` | 최초 등록 / 최종 수정 일시 | 신규 표시, enrich 캐시 키 |
