"""추천 규칙·행 변환 테스트 (DB 없이)."""
import json
import unittest
from datetime import date
from pathlib import Path

from app.catalog.rows import build_rows, matches_basic, policy_deadline, scope_of
from app.checkin.summary import summarize
from app.recommend.rules import eligible, interest_match, rank, score

ROOT = Path(__file__).resolve().parents[1]
TODAY = date(2026, 11, 19)
PROFILE = {"age": 24, "sex": "여", "sigungu_cd": "11620", "job": "구직 중", "school": None, "situations": ["미혼"]}


def policy(no, name, domains, situations=(), zips=("11620",), mclsf="취업", **extra):
    return build_rows("policy", {"policies": [{
        "plcyNo": no, "plcyNm": name, "i5_domains": list(domains), "situations": list(situations),
        "access_type": "apply", "zipCd": list(zips), "mclsfNm": mclsf, "region_scope": "시군구",
        "age_min_clean": None, "age_max_clean": None, "aplyYmd": "", "lastMdfcnDt": "2026-11-01", **extra}]})[0]


def program(pid, title, domains, topics=(), regions=("11620",), **extra):
    return build_rows("program", {"programs": [{
        "program_id": pid, "title": title, "i5_domains": list(domains), "topics": list(topics),
        "situations": [], "access_type": "apply", "region_cds": list(regions), "aply_end": "", **extra}]})[0]


class RowTests(unittest.TestCase):
    def test_policy_deadline_and_basic_filters(self):
        self.assertEqual(policy_deadline({"aplyYmd": "20261102 ~ 20261211"}), date(2026, 12, 11))
        self.assertIsNone(policy_deadline({"aplyYmd": ""}))
        # 신청기간이 비어 있으면 사업 종료일로 마감 (끝난 축제·행사가 통과하지 않게)
        self.assertEqual(policy_deadline({"aplyYmd": "", "bizPrdEndYmd": "20260919"}), date(2026, 9, 19))
        self.assertEqual(policy_deadline({"aplyYmd": "20261102 ~ 20261211", "bizPrdEndYmd": "20261231"}),
                         date(2026, 12, 11))
        ended_event = policy("4", "끝난 축제", "P", aplyYmd="", bizPrdEndYmd="20260919")
        self.assertFalse(matches_basic(ended_event, "11620", 24, TODAY))
        closed = policy("1", "지난 정책", "E", aplyYmd="20260101 ~ 20260919")
        self.assertFalse(matches_basic(closed, "11620", 24, TODAY))
        aged = policy("2", "34세까지", "E", age_max_clean=34)
        self.assertFalse(matches_basic(aged, "11620", 36, TODAY))
        self.assertTrue(matches_basic(aged, "11620", 24, TODAY))
        self.assertFalse(matches_basic(policy("3", "다른 구", "E", zips=("11680",)), "11620", 24, TODAY))

    def test_program_same_sido_center_is_reachable(self):
        other_gu = program("orang:1", "강남 프로그램", "O", regions=("11680",))
        seoul_wide = program("orang:2", "서울 전체", "O", regions=("11",))
        self.assertTrue(matches_basic(other_gu, "11620", None, TODAY))
        self.assertTrue(matches_basic(seoul_wide, "11620", None, TODAY))
        self.assertFalse(matches_basic(other_gu, "41117", None, TODAY))
        self.assertEqual(scope_of(program("orang:3", "관악", "O"), "11620"), "시군구")

    def test_seed_data_builds(self):
        data = json.loads((ROOT / "data/seed/serving/programs_serving.json").read_text(encoding="utf-8"))
        rows = build_rows("program", data)
        self.assertEqual(len(rows), len(data["programs"]))
        self.assertTrue(all(r["id"].startswith("program:") and r["sido_cds"] for r in rows))


class RuleTests(unittest.TestCase):
    def test_situation_gate_and_stage(self):
        single_parent = policy("10", "한부모 양육비", "E", situations=("한부모가정", "육아"))
        self.assertFalse(eligible(single_parent, {**PROFILE, "situations": ["기혼", "육아"]}))
        self.assertTrue(eligible(single_parent, {**PROFILE, "situations": ["한부모가정", "육아"]}))
        marriage = policy("11", "결혼장려금", "E", situations=("기혼", "임신·출산", "육아"))
        self.assertTrue(eligible(marriage, {**PROFILE, "situations": ["기혼"]}))
        self.assertFalse(eligible(marriage, PROFILE))
        women = policy("12", "여성 인턴", "E", situations=("여성",))
        self.assertTrue(eligible(women, PROFILE))
        self.assertFalse(eligible(women, {**PROFILE, "sex": "남"}))

    def test_job_requirement(self):
        workers = policy("20", "재직자 지원", "E", jobCd_nm="재직자")
        self.assertFalse(eligible(workers, PROFILE))
        self.assertTrue(eligible(workers, {**PROFILE, "job": "회사원"}))

    def test_income_condition(self):
        from app.recommend.service import income_condition
        self.assertIsNone(income_condition({"earnCndSeCd_nm": "무관", "earn_max_clean": 0}))
        self.assertEqual(income_condition({"earnCndSeCd_nm": "연소득", "earn_max_clean": 5000}),
                         {"kind": "annual_income", "max_manwon": 5000, "text": "연소득 5,000만 원 이하"})
        other = income_condition({"earnCndSeCd_nm": "기타", "earn_max_clean": 0, "earnEtcCn": "청년가구 중위소득\n150% 이하"})
        self.assertEqual(other, {"kind": "other", "max_manwon": None, "text": "청년가구 중위소득 150% 이하"})
        self.assertIsNone(income_condition({"earnCndSeCd_nm": "기타", "earnEtcCn": ""}))   # 설명이 없으면 보여줄 것 없음

    def test_special_target_titles_are_not_recommended(self):
        for name in ("부산 청년층 자살시도자 치료비 지원사업", "중독 예방·치료 지원(중독자 정신건강 지원사업)",
                     "외국인근로자 고용안정 지원", "부산 전세피해 임차인 주거안정지원금 지원",
                     "다문화청년 취업창업지원 사업", "2026 청년 부상 제대군인 상담센터 운영", "경계선지능청년지원",
                     "(광양시)경계선 지능인 평생교육 지원사업"):
            self.assertFalse(eligible(policy("s", name, "U"), PROFILE), name)
        # 예방 교육·일반 상담은 누구나 대상이라 그대로 둔다
        for name in ("청년 중심 마약류 중독예방 교육활동 지원", "(복지부) 26년 정신건강 심리상담 바우처사업",
                     "공공근로 사업(청년실업대책)"):
            self.assertTrue(eligible(policy("o", name, "U"), PROFILE), name)

    def test_interest_mapping_splits_mind_and_body_health(self):
        mind = policy("30", "청년 마음건강 지원", "U", mclsf="건강")
        meal = policy("31", "천원의 아침밥", "O", mclsf="건강")
        self.assertTrue(interest_match(mind, "마음건강·상담"))
        self.assertFalse(interest_match(mind, "몸 건강·식사"))
        self.assertTrue(interest_match(meal, "몸 건강·식사"))
        abroad = policy("32", "한류 교류단 모집", "C", mclsf="청년참여")
        self.assertFalse(interest_match(abroad, "사람 만나기·모임"))

    def test_primary_domain_scores_more_and_face_burden_lowers_in_person(self):
        summary = summarize({"support": "high", "conversation": "high", "face_to_face": "high"})
        counseling = policy("40", "1:1 심리상담", "U")
        meetup = program("orang:40", "청년 소모임", "CU")
        secondary = policy("41", "주거 상담", "EU")
        s_counsel, why = score(counseling, PROFILE, summary)
        s_meet, _ = score(meetup, PROFILE, summary)
        s_second, _ = score(secondary, PROFILE, summary)
        self.assertGreater(s_counsel, s_second)
        self.assertIn("도움을 부탁할 사람이 없다고 했어요", why)
        self.assertLess(s_meet - 10, s_counsel)   # 같은 구 가산점(10)을 빼도 대면 부담 때문에 상담보다 낮다

    def test_rank_dedup_and_domain_cap(self):
        summary = summarize({"economy": "high", "support": "high"})
        rows = [policy(str(100 + i), f"경제 지원 {i}번 사업", "E") for i in range(6)]
        rows += [policy("200", "경제 지원 0번 사업 (추가모집)", "E"), policy("201", "상담", "U")]
        ranked = rank(rows, PROFILE, summary, top=6)
        titles = [r["title"] for _, _, r in ranked]
        self.assertEqual(sum(t.startswith("경제") for t in titles), 3)   # 영역당 최대 3개
        self.assertIn("상담", titles)
        only_economy = rank(rows, PROFILE, summarize({"economy": "high"}), top=6)
        self.assertEqual(len(only_economy), 6)   # 필요한 영역이 하나면 제한 없이 채운다
        self.assertEqual(len({r["title"][:8] for _, _, r in only_economy}), 6)


class InterestSlotTests(unittest.TestCase):
    def test_chosen_interest_gets_a_slot_even_with_low_score(self):
        # 외출·대화 영역이 높고 관심 분야로 '일자리·취업'을 고른 사람 (2026-11-21 점검 사례)
        summary = summarize({"outing": "high", "conversation": "high", "interests": ["일자리·취업"]})
        rows = [policy(str(i), f"외출 활동 {i}", ["O"], mclsf="문화활동") for i in range(4)]
        rows += [policy(str(10 + i), f"대화 모임 {i}", ["C"], mclsf="청년참여") for i in range(4)]
        rows += [policy("99", "청년 인턴 직무캠프", ["E"], mclsf="취업")]
        top = rank(rows, PROFILE, summary, 6)
        titles = [r["title"] for _, _, r in top]
        self.assertEqual(len(top), 6)
        self.assertIn("청년 인턴 직무캠프", titles)
        self.assertEqual(titles[-1], "청년 인턴 직무캠프")      # 맨 뒤 자리와 바꾼다
        self.assertIn("관심 분야: 일자리·취업", top[-1][1])

    def test_no_swap_when_interest_already_shown_or_missing(self):
        summary = summarize({"outing": "high", "interests": ["일자리·취업", "해외 경험"]})
        rows = [policy(str(i), f"외출 활동 {i}", ["O"], mclsf="문화활동") for i in range(3)]
        rows += [policy("99", "청년 일자리 지원", ["O"], mclsf="취업")]   # 이미 위에 있음 / 해외 경험 항목은 없음
        before = [r["title"] for _, _, r in rank(rows, PROFILE, summary, 3)]
        self.assertIn("청년 일자리 지원", before)


if __name__ == "__main__":
    unittest.main()
