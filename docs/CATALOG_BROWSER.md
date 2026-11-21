# 카탈로그 탐색 API (로컬 구현)

GET /api/catalog/items

- q: 검색어, kind: policy/program, category: 서버가 반환한 분야 이름
- sigungu_cd: 시도 2자리 또는 시군구 5자리, age: 0~120 선택
- only_open: 기본 true(마감 제외), sort: title/deadline
- page: 1 이상, page_size: 1~100(기본 12)
- 응답: items, total, page, page_size, categories, source, notice
- 기본 분야 목록은 정책의 대분류이며 프로그램 선택 시 프로그램 원본 분야를 반환한다.

GET /api/catalog/items/{item_id}

- 응답: item, source. 없는 ID는 404.
- item: 기존 추천 item 필드와 categories, subcategories, keywords, region_label, application_status, application_label, application_period, application_start, application_period_raw, target, method, documents, exclusions, age_min, age_max, updated_at, reference_url.
- 실제 원본에 없는 상세 필드는 빈 값으로 반환한다. 프론트 과거 스냅샷으로 메우지 않는다.
- application_status: always_open/open/upcoming/closed/unknown. 명시적 상시 조건이 있어야 상시다. 날짜가 없다는 이유로 상시를 만들지 않는다. 마감 상태가 우선하며 기준일은 서울 시간이다.
- 대분류는 기존 원본의 교육/복지문화/참여권리 표기를 교육·직업훈련/금융·복지·문화/참여·기반으로 정규화한다. 키워드·중분류는 실제 원본 필드다.
- source=db는 DB 응답, source=file은 기존 백엔드 파일 대체다. 목록은 현재 전체 카탈로그를 읽어 처리한다. 규모 증가 시 DB 필터/페이징 개선 필요.
- 개인정보 저장 및 대화/자동 신청 API가 아니다. 조건 표시가 자격 확정을 의미하지 않는다.

검증: .venv/bin/python -m unittest tests.test_catalog_browser tests.test_recommend_api tests.test_checkin tests.test_recommend_rules (24개 통과). 실제 서울 금융·복지·문화 조회 43건/source=db와 상세 응답 확인.
