"""원본은 GET만 하고, 같은 질문을 가진 복제 폼에만 POST한다."""
import copy
import unittest
from unittest.mock import Mock
from app.apply import gform, service
from tests.test_apply import page, VIEW, ITEMS, response

TARGET='https://docs.google.com/forms/d/e/replica-form/viewform'

class ReplicaTests(unittest.TestCase):
    def setUp(self):
        self.source=gform.parse(page(),VIEW)
        self.target=copy.deepcopy(self.source)
        self.target.submit_url='https://docs.google.com/forms/d/e/replica-form/formResponse'
        for q in self.target.questions:q.entry+=1000
        self.forms={'demo:replica':{'form_url':VIEW,'submission_form_url':TARGET,'test_only':True,'submission_enabled':True}}
        self.fetch=Mock(side_effect=lambda url:self.source if url==VIEW else self.target)
        self.post=Mock();self.post.post.return_value=response('ok',self.target.submit_url)
        self.answers={'q1':'가상수아','q2':'23','q3':'여','q4':'010-0000-0000','q5':'서울 강동구 천호동','q6':'자기소개서 피드백을 받고 싶습니다.','q8':'동의합니다.'}
    def test_original_entries_never_used_for_submission(self):
        result=service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post,expected_revision=service.form_revision(self.source))
        self.assertEqual((result['status'],result['confirmed_by']),('simulated','server'))
        self.assertEqual(self.post.post.call_args.args[0],self.target.submit_url)
        self.assertIn(('entry.1101','가상수아'),self.post.post.call_args.kwargs['data'])
        self.assertNotIn(('entry.101','가상수아'),self.post.post.call_args.kwargs['data'])
    def test_changed_question_or_same_destination_stops_before_post(self):
        self.target.questions[0].label='다른 질문'
        with self.assertRaises(service.FormChanged):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)
        self.post.post.assert_not_called()
        self.target.submit_url=self.source.submit_url
        with self.assertRaises(service.NotAvailable):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)
    def test_name_without_virtual_prefix_is_accepted(self):
        self.answers['q1']='홍길동'
        result=service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)
        self.assertEqual(result['status'],'simulated')
        self.assertIn(('entry.1101','홍길동'),self.post.post.call_args.kwargs['data'])

    def test_real_contact_is_rejected(self):
        self.answers['q4']='010-1234-5678'
        with self.assertRaises(gform.InvalidAnswers):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)
        self.post.post.assert_not_called()
    def test_source_pages_and_grid_read_but_not_posted(self):
        grid=[55,'희망 시간',None,7,[[901, [['월요일'],['화요일']],0,['오후 2시'],None,None,None,None,None,None,None,[1]]]]
        html=page([[77,'다음 페이지',None,8,None],grid])
        with self.assertRaises(gform.FormNotSupported):gform.parse(html,VIEW)
        source=gform.parse(html,VIEW,read_only=True)
        q=source.questions[0]
        self.assertEqual((q.kind,q.rows[0]['label']),('multi_grid','오후 2시'))
        self.assertEqual(gform.build_payload(source,{'q1r1':['월요일','화요일']}),[('entry.901','월요일'),('entry.901','화요일')])
        with self.assertRaises(gform.InvalidAnswers):gform.build_payload(source,{'q1r1':['수요일']})
    def test_start_exposes_original_labels_and_grid_without_entry_ids(self):
        result=service.start(None,self.forms,'demo:replica',None,None,fetch=self.fetch)
        self.assertTrue(result['replica'])
        self.assertEqual(result['source_form_url'],VIEW)
        self.assertEqual(result['questions'][0]['label'],self.source.questions[0].label)
        self.assertNotIn('entry',result['questions'][0])

    def test_open_text_questions_offer_drafts_without_inventing_experiences(self):
        self.source.questions[5].label='나의 올해 돌아보기! (참여 후기)'
        result=service.start(None,self.forms,'demo:replica',None,None,fetch=self.fetch)
        self.assertTrue(next(q for q in result['questions'] if q['id']=='q6')['can_draft'])

    def test_disabled_replica_never_fetches_or_posts(self):
        self.forms['demo:replica']['submission_enabled']=False
        with self.assertRaises(service.NotAvailable):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)
        self.fetch.assert_not_called();self.post.post.assert_not_called()
    def test_source_revision_change_and_missing_answer_never_post(self):
        with self.assertRaises(service.FormChanged):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post,expected_revision='0'*64)
        del self.answers['q8']
        with self.assertRaises(gform.InvalidAnswers):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)
        self.post.post.assert_not_called()
    def test_provider_failure_is_not_success(self):
        self.post.post.return_value=response(page(),TARGET)
        with self.assertRaises(gform.SubmitFailed):service.submit(None,self.forms,'demo:replica',self.answers,fetch=self.fetch,post=self.post)


    def test_conditional_region_is_not_prefilled(self):
        self.source.questions[4].label='(선택) 생활권 지역 : 서울시 외 타지역 거주할 경우'
        result=service.start(None,self.forms,'demo:replica',None,None,fetch=self.fetch)
        question=next(q for q in result['questions'] if q['id']=='q5')
        self.assertIsNone(question.get('fill_key'))

if __name__=='__main__':unittest.main()
