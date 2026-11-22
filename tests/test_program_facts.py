import unittest
from unittest.mock import patch
from app.catalog.program_facts import clean_source,verified,fingerprint,presentation,application_links
from app.chat.curate import curate
class FactsTests(unittest.TestCase):
 def test_mail_intro_and_contacts_removed(self):
  raw='안녕하세요, 공간관리자 김가상입니다. 홍보 협조를 요청드립니다. ----- 청년들이 함께 그림을 그리는 모임이에요. test@example.test 010-1234-5678'
  result=clean_source(raw)
  for token in ['김가상','홍보 협조','test@example','010-1234']:self.assertNotIn(token,result)
  self.assertIn('그림',result)
 def test_evidence_must_be_real_contiguous_source(self):
  source={'content':'매주 목요일 함께 그림을 그려요.'}
  self.assertIsNone(verified({'summary':{'value':'10명이 모여요','evidence':'10명'}},source))
  self.assertIsNotNone(verified({'summary':{'value':'함께 그림을 그리는 모임이에요.','evidence':'함께 그림을 그려요.'}},source))
  self.assertIsNotNone(verified({'summary':{'value':'그림 모임이에요.','evidence':['매주 목요일','그림을 그려요.']}},source))
  self.assertIsNone(verified({'summary':{'value':'없는 내용','evidence':['매주 목요일','원문에 없는 구절']}},source))
  self.assertNotEqual(fingerprint(source),fingerprint({'content':'변경된 활동'}))
 def test_program_method_only_confirmed_form(self):
  row={'id':'program:unit','kind':'program','payload':{'summary':'활동','apply_urls':'https://map.naver.com/a'},'access_type':'apply'}
  self.assertEqual(presentation(row)['method'],'')
  row['payload']['verified_apply_urls']=['https://docs.google.com/forms/d/e/FAKE/viewform']
  self.assertEqual(presentation(row)['method'],'온라인 신청서로 신청해요.')
 def test_direct_feedback_requires_supported_content(self):
  result={'policies':[],'programs':[{'id':'a','title':'취업 특강','summary':'강의로 준비해요.'},{'id':'b','title':'자소서 첨삭','summary':'자기소개서 개별 피드백을 받아요.'}]}
  actual=curate(result,[{'role':'user','content':'자소서 직접 피드백받는 프로그램 찾아줘'}])
  self.assertEqual([i['id'] for i in actual['programs']],['b'])

 def test_form_domain_alone_does_not_prove_application(self):
  url='https://forms.gle/fake'
  self.assertEqual(application_links({'content':'만족도 조사 '+url}),[])
  self.assertEqual(application_links({'content':'신청방법: 구글폼 신청서 작성 '+url}),[url])

 def test_policy_request_does_not_inherit_old_program_focus(self):
  result={'policies':[{'id':'p'}],'programs':[]}
  messages=[{'role':'user','content':'문화 프로그램 찾아줘'},{'role':'user','content':'이번에는 월세 정책 찾아줘'}]
  self.assertIs(curate(result,messages),result)
 def test_past_dated_activity_is_not_recommended_as_always_open(self):
  from datetime import date
  result={'policies':[],'programs':[{'id':'p','title':'문화 행사','summary':'문화 모임','activity_schedule':'2026. 4. 18'}]}
  self.assertEqual(curate(result,[{'role':'user','content':'문화 프로그램 찾아줘'}],today=date(2026,11,22))['programs'],[])
