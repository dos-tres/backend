import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from pipeline.programs.crawl.seoul_centers import parse_intro, parse_notices, parse_directory, clean
from app.catalog.centers import official_content, official_snapshot

INTRO = '''<div class="center-infomation-box"><div class="lf"><strong>서울청년센터 중구</strong><p>청년의 모임과 상담을 돕는 공간</p></div><li class="address">서울 중구 공개로 1</li><li class="time">평일 10:00~21:30</li></div><div class="center-introduce-wrap"><div class="tith1"><p>✅ 이용 대상</p><p>만 19~39세</p><p>✅ 회의실</p><p>사전 예약</p><p>📞 문의</p><p>연락처는 저장하지 않음</p></div><table><tr><th>오시는 길</th><td>지하철 출구 도보 5분</td></tr><tr><th>공간 이용방법</th><td>라운지 자유 이용</td></tr></table></div>'''
NOTICE = '''<table class="board-st1"><tbody><tr><td>1</td><td><a onclick="goView('2610270003')">휴관 안내</a></td><td>2026-10-27</td></tr></tbody></table>'''

class OfficialCenterTest(unittest.TestCase):
    def test_structured_intro_and_no_contact_blocks(self):
        item = parse_intro(INTRO, 'CT00162')
        self.assertEqual(item['hours'], '평일 10:00~21:30')
        self.assertEqual(item['directions'], '지하철 출구 도보 5분')
        self.assertEqual(len(item['sections']), 2)
        self.assertEqual(item['sections'][0]['body'], '만 19~39세')
        self.assertNotIn('연락처', json.dumps(item, ensure_ascii=False))
        self.assertIn('cntrId=CT00162', item['homepage'])
        self.assertEqual(clean('공개 https://example.org/placeholder'), '공개')

    def test_notices_keep_real_title_date_and_center_scoped_link(self):
        notices = parse_notices(NOTICE, 'CT00162')
        self.assertEqual(notices[0]['date'], '2026-10-27')
        self.assertIn('noticeView.do?', notices[0]['url'])
        self.assertIn('cntrId=CT00162', notices[0]['url'])
        self.assertEqual(parse_notices('<table class="board-st1"><tbody></tbody></table>', 'CT00162'), [])

    def test_broken_pages_are_not_successful_empty_results(self):
        with self.assertRaises(ValueError):
            parse_intro('<html>error</html>', 'CT00162')
        with self.assertRaises(ValueError):
            parse_notices('<html>error</html>', 'CT00162')
        self.assertEqual(parse_directory('<a onclick="goView(\'CT00162\')">센터</a>'), ['CT00162'])

    def test_exact_center_binding_and_file_refresh(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'center_official.json'
            path.write_text(json.dumps({'items': {'CT00162': parse_intro(INTRO, 'CT00162')}}))
            official_snapshot.cache_clear()
            with patch('app.catalog.centers.paths.PROGRAM_DIR', Path(folder)):
                self.assertEqual(official_content('서울청년센터 중구')['center_id'], 'CT00162')
                self.assertIsNone(official_content('서울청년센터 관악'))

    def test_independent_guides_use_confirmed_hours_without_guessing(self):
        from app.catalog.centers import center_detail
        self.assertIn('09:00~18:00', center_detail('10280', None)['item']['guide']['hours'])
        self.assertIn('평일 09:00~18:00', center_detail('10041', None)['item']['guide']['hours'])
        self.assertNotIn('hours', center_detail('10281', None)['item']['guide'])
        for id in ['10282', '10038', '10034', '10278', '10042', '10277', '10047']:
            link = center_detail(id, None)['item']['guide']['notice_url']
            self.assertTrue(link.startswith('https://'))
            self.assertNotIn('PHPSESSID', link)
