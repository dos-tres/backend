"""대화에서 요청한 대상과 공고 근거로 짧은 후보를 고른다. 자격·모임 규모는 추정하지 않는다."""
import re


def curate(results: dict, messages: list[dict], session=None, profile=None, today=None) -> dict:
    user_text = ' '.join(m['content'] for m in messages[-12:] if m['role'] == 'user')
    wants_program = bool(re.search(r'프로그램|문화\s*활동|모임|사람.*만나', user_text))
    if not wants_program:
        return results
    last_user=next((m['content'] for m in reversed(messages) if m['role']=='user'),'')
    if re.search(r'정책|지원금|월세|전세',last_user) and not re.search(r'프로그램|모임|활동',last_user):return results
    culture = bool(re.search(r'문화|여가|취미|예술', user_text))
    small = bool(re.search(r'소규모|큰\s*모임|부담|적은\s*인원', user_text))
    career=bool(re.search(r'취업|자소서|자기소개서|면접|이력서',user_text))
    if re.search(r'취업|자소서|자기소개서|면접|이력서',last_user):culture=False
    elif re.search(r'문화|예술|취미',last_user):career=False
    feedback=career and bool(re.search(r'피드백|첨삭|직접.*(?:봐|받|도움)',user_text))
    if profile:
        from datetime import date
        from app.catalog.repository import find_candidates
        from app.recommend.rules import eligible
        from app.recommend.service import to_item
        rows,source=find_candidates(session,profile['sigungu_cd'],profile.get('age'),today or date.today())
        results={**results,'programs':[to_item(0,[],r,profile['sigungu_cd'],today) for r in rows if r['kind']=='program' and eligible(r,profile)],'source':source}
    picked = []
    for original in results['programs']:
        item = dict(original)
        from datetime import date
        schedule=item.get('activity_schedule','')
        activity_dates=[]
        for y,m,d in re.findall(r'(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})',schedule):
            try:activity_dates.append(date(int(y),int(m),int(d)))
            except ValueError:pass
        if activity_dates and max(activity_dates)<(today or date.today()):continue
        text = ' '.join(str(item.get(k) or '') for k in ['title','summary','target'])
        if career and not re.search(r'취업|자소서|자기소개서|면접|이력서|직무|커리어|진로',text):continue
        if feedback and not (re.search(r'첨삭|피드백|클리닉|모의\s*면접',text) and re.search(r'자소서|자기소개서|면접|이력서',text)):continue
        if culture and not re.search(r'문화|예술|취미|공예|독서|책|영화|음악|전시|동아리',text):continue
        reasons = []
        score = 0
        if career:
            score+=5
            reasons.append('진로·취업 준비를 돕는 프로그램이라 먼저 살펴볼 만해요.')
        if feedback:
            score+=5
            reasons.insert(0,'공고에 첨삭·피드백 또는 모의면접이 명시돼 있어 직접 피드백받고 싶다는 말씀에 맞춰 골랐어요.')
        if culture and re.search(r'문화|예술|취미|공예|독서|책|영화|음악|전시', text):
            score += 3
            reasons.append('문화·취미 활동을 원한다는 말씀과 공고 내용이 맞아요.')
        if re.search(r'교류|커뮤니티|함께|모임|연결', text):
            score += 2
            reasons.append('공고에 교류·함께하는 활동이 안내돼 있어요.')
        if small and re.search(r'소규모|소모임', text):
            score += 4
            reasons.append('공고에 소규모 모임으로 안내돼 있어요.')
        if item.get('scope') == '시군구':
            score += 2
            reasons.append('저장한 거주 구를 기준으로 찾은 지역 프로그램이에요.')
        if small and re.search(r'파티|축제|체육대회|행사', item.get('title','')):
            score -= 3
        item['why'] = reasons or ['찾아본 프로그램 중 하나예요. 구체적인 활동 내용은 공고에서 확인해 주세요.']
        item['fit_notice'] = '참여 인원과 진행 방식은 확인이 필요해요. 소규모라고 확정할 수는 없어요.' if small and not re.search(r'소규모|소모임', text) else ''
        picked.append((score,item))
    picked.sort(key=lambda pair: -pair[0])
    return {**results, 'policies': [], 'programs': [item for _,item in picked[:3]], 'curated': True, 'selection_need':'자소서·면접 직접 피드백' if feedback else '취업 준비' if career else '문화·교류 활동'}
