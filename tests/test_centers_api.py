import unittest
from fastapi.testclient import TestClient
from app.main import app

class CentersApiTest(unittest.TestCase):
    def test_collected_seoul_list_search_and_detail(self):
        with TestClient(app) as client:
            response = client.get('/api/centers')
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body['source'], 'file')
            self.assertTrue(body['items'])
            self.assertTrue(all(r['region_code'].startswith('11') for r in body['items']))
            item = body['items'][0]
            result = client.get('/api/centers', params={'q': item['name'], 'district': item['district']}).json()
            self.assertTrue(any(r['id'] == item['id'] for r in result['items']))
            detail = client.get('/api/centers/'+item['id'])
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()['item']['id'], item['id'])
            self.assertEqual(len(detail.json()['programs']), item['program_count'])
            self.assertLessEqual(item['open_program_count'], item['program_count'])
            self.assertIn(detail.json()['programs_source'], ['file', 'db'])
            self.assertNotIn('distance', detail.json()['item'])
            self.assertNotIn('hours', detail.json()['item'])
            self.assertEqual(client.get('/api/centers', params={'q':'no_matching_center_qa'}).json()['items'], [])
            self.assertEqual(client.get('/api/centers/not-a-center').status_code, 404)

    def test_seoul_branch_aliases_preserve_center_identity(self):
        from app.catalog.centers import center_key, center_detail
        self.assertEqual(center_key('서울청년센터 관악 청년문화공간 신림동쓰리룸'), center_key('서울청년센터 관악'))
        self.assertEqual(center_key('서울청년센터 금천 청춘삘딩'), center_key('서울청년센터 금천'))
        self.assertEqual(center_key('서초청년센터 (서울청년센터 서초)'), center_key('서울청년센터 서초'))
        self.assertNotEqual(center_key('관악청년청'), center_key('서울청년센터 관악'))
        for center_id in ['10030', '10033', '10044']:
            self.assertTrue(center_detail(center_id, None)['programs'])

    def test_all_counts_match_detail_including_aliases(self):
        from app.catalog.centers import browse_centers, center_detail
        for item in browse_centers()['items']:
            detail = center_detail(item['id'], None)
            self.assertEqual(item['program_count'], len(detail['programs']))
            self.assertEqual(item['open_program_count'], sum(p['application_status'] in {'open', 'always_open'} for p in detail['programs']))

    def test_verified_center_guides_are_not_program_availability_claims(self):
        from app.catalog.centers import browse_centers, center_detail
        items = browse_centers()['items']
        self.assertTrue(all(item.get('guide', {}).get('summary') for item in items))
        for item in items:
            guide = item['guide']
            self.assertTrue(guide['source']['url'].startswith('https://'))
            self.assertTrue(guide['facilities'])
            self.assertNotIn('프로그램이 없', guide['summary'])
        gwanak = center_detail('10029', None)
        self.assertEqual(gwanak['programs'], [])
        self.assertIn('청년카페', gwanak['item']['guide']['facilities'])
        self.assertIn('프로그램도 운영', gwanak['item']['guide']['summary'])
        self.assertIn('삼양로 29', center_detail('10280', None)['item']['address'])
