/**
 * 시연용 테스트 구글폼 2개를 만든다 (docs/APPLY.md 5장).
 *
 * - 신청 가능 폼: 서울청년센터 프로그램 신청서와 같은 양식(이름·나이·성별·연락처·거주지·신청 이유·알게 된 경로·개인정보 동의)
 * - 마감된 폼: 같은 양식이지만 응답을 받지 않음(마감 처리 시연·테스트용)
 *
 * 실제 기관 폼이 아니다. 제목과 설명에 [둘셋 테스트]를 붙여 실제 모집으로 오해하지 않게 한다.
 *
 * 실행 방법
 *   1. https://script.google.com → 새 프로젝트
 *   2. 이 파일 내용을 전부 붙여 넣고 저장
 *   3. 위쪽 함수 선택에서 createTestForms → 실행 → 권한 허용(본인 구글 계정에 폼 2개가 생김)
 *   4. 아래 "실행 로그"에 나온 두 폼 주소(응답용)를 backend/.env 의 APPLY_FORMS_PATH 파일에 넣는다
 *      주소는 Git·채팅방·문서에 올리지 않는다.
 */
function createTestForms() {
  const open = buildForm_('[둘셋 테스트] 11월 청년 베이킹 클래스 참여자 모집');
  open.setAcceptingResponses(true);

  const closed = buildForm_('[둘셋 테스트] 2026 청년 마음상담 신청서 (마감)');
  closed.setAcceptingResponses(false);
  closed.setCustomClosedFormMessage('[둘셋 테스트] 2026년 상담 예산 소진으로 더 이상 신청을 받지 않습니다. 감사합니다.');

  Logger.log('신청 가능 폼(응답용): ' + open.getPublishedUrl());
  Logger.log('신청 가능 폼(편집용): ' + open.getEditUrl());
  Logger.log('마감 폼(응답용): ' + closed.getPublishedUrl());
  Logger.log('마감 폼(편집용): ' + closed.getEditUrl());
}

function buildForm_(title) {
  const form = FormApp.create(title);
  form.setDescription([
    '※ 둘셋 시연용 테스트 폼입니다. 실제 모집이 아닙니다.',
    '',
    '✨일정✨',
    '2026. 11. 24.(화) 13:00 ~ 15:00 (예정)',
    '',
    '✨모집인원✨',
    '12명',
    '',
    '✨장소✨',
    '둘셋 테스트 센터 (가상 장소)',
    '',
    '작성 1분 소요',
  ].join('\n'));
  form.setCollectEmail(false);            // 이메일 수집 안 함
  form.setLimitOneResponsePerUser(false); // 켜면 로그인이 필요해져 서버가 제출할 수 없다
  form.setAllowResponseEdits(false);
  form.setShowLinkToRespondAgain(true);   // 테스트를 여러 번 할 수 있게
  form.setConfirmationMessage('신청이 접수되었습니다. (둘셋 테스트)');

  form.addTextItem().setTitle('성명').setRequired(true);

  form.addTextItem().setTitle('만 나이').setRequired(true)
    .setValidation(FormApp.createTextValidation().requireNumberBetween(0, 120)
      .setHelpText('숫자만 적어 주세요.').build());

  form.addMultipleChoiceItem().setTitle('성별').setChoiceValues(['남', '여']).setRequired(true);

  form.addTextItem().setTitle('연락처').setHelpText('ex) 010-xxxx-xxxx 양식을 꼭 지켜주세요 !').setRequired(true)
    .setValidation(FormApp.createTextValidation().requireTextMatchesPattern('01[0-9]-[0-9]{3,4}-[0-9]{4}')
      .setHelpText('010-xxxx-xxxx 양식으로 적어 주세요.').build());

  form.addParagraphTextItem().setTitle('거주지역 (ex.OO구 OO동) (반드시 "동"까지 필수기재 해주세요!)').setRequired(true);

  form.addParagraphTextItem().setTitle('베이킹 클래스에 신청하신 이유를 적어주세요 !')
    .setHelpText('참여자 선정에 참고할 예정이니 정성껏 작성해주세요 : )').setRequired(true);

  form.addMultipleChoiceItem().setTitle('프로그램을 알게 된 경로를 알려주세요.')
    .setChoiceValues(['센터 블로그', '센터 인스타그램', '청년몽땅정보통', 'SNS 광고', '지인추천'])
    .showOtherOption(true).setRequired(false);

  form.addMultipleChoiceItem().setTitle('개인정보 수집·이용 동의 여부')
    .setHelpText([
      '[개인정보 동의 내용] (둘셋 테스트)',
      '■ 수집·이용 목적: 테스트 프로그램 신청 접수',
      '■ 수집 항목: 성명, 만 나이, 성별, 연락처, 거주지역, 신청 이유',
      '■ 보유·이용 기간: 시연 종료 후 즉시 삭제',
      '■ 동의를 거부할 권리가 있으며, 거부 시 선정되지 않을 수 있습니다.',
    ].join('\n'))
    .setChoiceValues(['동의합니다.', '동의하지 않습니다.(동의하지 않을 시, 선정되지 않을 수 있습니다.)'])
    .setRequired(true);

  return form;
}
