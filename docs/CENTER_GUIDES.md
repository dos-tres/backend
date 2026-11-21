# 센터 공간 안내 보강 (로컬 구현)

app/catalog/center_guides.json은 청년센터·지자체 공식 안내를 사람이 확인해 요약한 자료다. 센터 목록·상세의 item.guide로 제공한다. DB 프로그램의 존재 여부로 용도를 추측하지 않는다.

필드: kind(공간 역할), summary(소개), facilities(확인된 시설·서비스), usage_note(이용 안내), source{name,url,checked_at}. 공식 확인이 된 일부 항목에는 hours/homepage/address가 추가된다. 현재 17개 개별 안내와 서울청년센터 17개 공통 서비스 안내를 적용한다. 기관 명칭만으로 서비스 내용을 새로 생성하지 않는다.

개별 출처는 JSON source.url에서 직접 확인할 수 있다. 대표 근거:
- 서울청년센터 공통 서비스: https://youth.seoul.go.kr/orang/content.do?key=2309210004
- 관악청년청 시설/운영: https://gfac.or.kr/site/main/content/youthoffice
- 노원 청년공감: https://youth.seoul.go.kr/infoData/sprtInfo/view.do?key=2309130006&sprtInfoId=67157
- 길이음 주소/공간 안내: https://sb.go.kr/www/contents.do?key=7349

공식 소개와 수집 공고는 별도다. 프로그램0건이 미운영을 뜻하지 않는다. 특히 관악청년청·청년공감 등의 공식 안내에는 프로그램 운영도 명시돼 있다. 시설 이용 조건·요금·운영 시간은 방문 전 공식 채널에서 재확인한다. 이 작업은 실제 기관에 신청·문의하지 않는다.

현재 홈페이지 링크 누락, 프로그램 수집 범위 밖 기관의 공고 확장, 전체 현장 운영 상태·주소 최신성 전수 확인은 후속 데이터 작업이다. 실제 개인정보·연락처·테스트 폼 링크·API키는 포함하지 않는다.
