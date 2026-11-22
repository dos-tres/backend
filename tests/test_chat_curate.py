import unittest
from app.chat.curate import curate

class CurateTests(unittest.TestCase):
    def test_program_request_limits_and_does_not_invent_small_group(self):
        result={'policies':[{'id':'policy'}], 'programs':[
            {'id':'party','title':'연말 파티','summary':'교류 행사','scope':'광역'},
            {'id':'art','title':'문화 공예 소모임','summary':'함께 만드는 시간','scope':'광역'},
            {'id':'book','title':'독서 모임','summary':'함께 책 읽기','scope':'광역'},
            {'id':'music','title':'음악 감상','summary':'음악 듣기','scope':'광역'}]}
        actual=curate(result,[{'role':'user','content':'큰 모임은 부담돼. 문화 활동 프로그램 찾아줘'}])
        self.assertEqual(actual['policies'],[])
        self.assertEqual(len(actual['programs']),3)
        self.assertEqual(actual['programs'][0]['id'],'art')
        self.assertEqual(actual['programs'][0]['fit_notice'],'')
        self.assertIn('확인',actual['programs'][1]['fit_notice'])
        self.assertEqual(result['programs'][0].get('why'),None)
    def test_policy_request_unchanged(self):
        result={'policies':[{'id':'p'}],'programs':[]}
        self.assertIs(curate(result,[{'role':'user','content':'월세 정책 찾아줘'}]),result)

    def test_career_includes_relevant_policy_unless_program_only(self):
        result={'policies':[{'id':'national','title':'국민취업지원제도'}],'programs':[{'id':'p','title':'자소서 첨삭','summary':'자기소개서 직접 피드백'}]}
        actual=curate(result,[{'role':'user','content':'취업 준비 중이야. 자소서 직접 피드백 프로그램 찾아줘'}])
        self.assertEqual(actual['policies'][0]['id'],'national')
        self.assertLessEqual(len(actual['policies'])+len(actual['programs']),3)
        only=curate(result,[{'role':'user','content':'취업 프로그램만 찾아줘'}])
        self.assertEqual(only['policies'],[])
