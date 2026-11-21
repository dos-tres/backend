import unittest
from datetime import date
from fastapi.testclient import TestClient
from app.main import create_app
from app.config import Settings
from app.catalog.presentation import application_info, presentation_fields

class CatalogBrowserTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(Settings(_env_file=None, database_url='')))

    def test_catalog_filters_and_detail(self):
        response = self.client.get('/api/catalog/items', params={'sigungu_cd':'11','category':'금융·복지·문화','page_size':12})
        self.assertEqual(response.status_code,200)
        data=response.json()
        self.assertEqual(data['source'],'file')
        self.assertGreater(data['total'],12)
        self.assertTrue(all('금융·복지·문화' in item['categories'] for item in data['items']))
        self.assertTrue(all('서울특별시' in item['region_label'] or item['region_label']=='전국' for item in data['items']))
        self.assertIn('금융·복지·문화',data['categories'])
        self.assertNotIn('복지문화',data['categories'])
        item=data['items'][0]
        detail=self.client.get('/api/catalog/items/'+item['id'])
        self.assertEqual(detail.status_code,200)
        self.assertEqual(detail.json()['item']['id'],item['id'])
        self.assertIn('target',detail.json()['item'])
        self.assertIn('method',detail.json()['item'])
        self.assertIn('income_condition',detail.json()['item'])
        self.assertEqual(self.client.get('/api/catalog/items/not-found').status_code,404)

    def test_query_pagination_and_validation(self):
        data=self.client.get('/api/catalog/items',params={'q':'보조금','kind':'policy','page_size':2}).json()
        self.assertEqual(len(data['items']),2)
        self.assertTrue(all('보조금' in ' '.join([i['title'],i['summary'],*i['keywords']]) for i in data['items']))
        next_data=self.client.get('/api/catalog/items',params={'q':'보조금','kind':'policy','page_size':2,'page':2}).json()
        self.assertTrue(set(i['id'] for i in data['items']).isdisjoint(i['id'] for i in next_data['items']))
        self.assertEqual(self.client.get('/api/catalog/items',params={'page_size':101}).status_code,422)
        self.assertEqual(self.client.get('/api/catalog/items',params={'q':'존재하지않는검증문자열XYZ'}).json()['total'],0)

    def test_period_states_do_not_invent_always_open(self):
        row={'kind':'policy','status':'ok','deadline':None,'payload':{'aplyPrdSeCd_nm':'상시'}}
        info=application_info(row,date(2026,11,21))
        self.assertEqual((info['application_status_label'],info['application_period']),('상시','상시'))
        unknown=application_info({'kind':'program','status':'ok','deadline':None,'payload':{}},date(2026,11,21))
        self.assertEqual(unknown['application_status'],'unknown')
        self.assertEqual(unknown['application_period'],'기간 미제공')
        closed=application_info({**row,'deadline':date(2026,10,1)},date(2026,11,21))
        self.assertEqual(closed['application_status'],'closed')
        self.assertNotEqual(closed['application_period'],'상시')
        upcoming=application_info({**row,'payload':{'aplyYmd':'20261201 ~ 20261231'},'deadline':date(2026,12,31)},date(2026,11,21))
        self.assertEqual(upcoming['application_status'],'upcoming')

if __name__=='__main__':unittest.main()
