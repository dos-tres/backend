"""추천 카드 설명은 생성 단계에서 검증·저장한 공고 정보만 사용한다.

대화마다 원문을 다시 요약하지 않는다. 개인화 이유는 선별 규칙에서 만든 근거를 사용한다.
"""
from app.catalog.repository import get_item
from app.catalog.program_facts import presentation


def explain(results, model, messages, session):
    if not results.get('curated'):
        return
    for item in results['programs']:
        row = get_item(session, item['id'])
        if row:
            item.update(presentation(row))
        item['fit_reason'] = ' '.join(item.get('why', [])[:2])
