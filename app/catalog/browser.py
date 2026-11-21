"""Read-only public catalog browsing; personal information is never saved."""
from datetime import date
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from app.catalog.models import CatalogItem
from app.catalog.repository import COLUMNS, _fallback_rows
from app.catalog.rows import matches_basic
from app.catalog.presentation import presentation_fields, catalog_today
from app.recommend.service import to_item


def all_rows(session):
    if session is not None:
        try:
            rows = [{c: getattr(item, c) for c in COLUMNS} for item in session.scalars(select(CatalogItem).where(CatalogItem.status.in_(['ok', 'closed'])))]
            if rows:
                return rows, 'db'
        except SQLAlchemyError:
            session.rollback()
    return list(_fallback_rows()), 'file'


def full_item(row, sigungu_cd='11620', today=None):
    item = to_item(0, [], row, sigungu_cd, today)
    p = row['payload']
    policy = row['kind'] == 'policy'
    age = '' if row['age_min'] is None and row['age_max'] is None else f"만 {row['age_min'] or 0}세 ~ {str(row['age_max'])+'세' if row['age_max'] else '상한 없음'}"
    item.update(presentation_fields(row, today))
    item.update({'summary': p.get('plcyExplnCn') or '' if policy else p.get('summary') or '',
                 'support': p.get('plcySprtCn') or '' if policy else p.get('summary') or '',
                 'target': '\n'.join(v for v in [age, p.get('jobCd_nm'), p.get('schoolCd_nm'), p.get('addAplyQlfcCndCn')] if v and v != '제한없음') if policy else p.get('target') or '',
                 'method': p.get('plcyAplyMthdCn') or '' if policy else ('방문 이용' if row['access_type'] == 'visit' else ''),
                 'documents': p.get('sbmsnDcmntCn') or '', 'exclusions': p.get('ptcpPrpTrgtCn') or '',
                 'age_min': row['age_min'], 'age_max': row['age_max'],
                 'updated_at': p.get('lastMdfcnDt') or '',
                 'reference_url': (p.get('refUrlAddr1') or p.get('refUrlAddr2') or '') if policy else p.get('url') or ''})
    return item


def browse(session, *, q='', kind=None, category='', sigungu_cd=None, age=None, only_open=True, page=1, page_size=12, sort='title'):
    rows, source = all_rows(session)
    today = catalog_today()
    available = sorted({c for row in rows if row['kind'] == (kind or 'policy') for c in presentation_fields(row, today)['categories']})
    items = []
    for row in rows:
        if kind and row['kind'] != kind:
            continue
        info = presentation_fields(row, today)
        if only_open and info['application_status'] == 'closed':
            continue
        if category and category not in info['categories']:
            continue
        if age is not None and not ((row['age_min'] or 0) <= age <= (row['age_max'] or 120)):
            continue
        if sigungu_cd:
            # Region selection accepts a province or district. Reuse recommendation region rules.
            if len(sigungu_cd) == 2:
                if sigungu_cd not in row['sido_cds']:
                    continue
            else:
                region_row = {**row, 'status': 'ok', 'deadline': None}
                if not matches_basic(region_row, sigungu_cd, None, today):
                    continue
        item = full_item(row, sigungu_cd if sigungu_cd and len(sigungu_cd) == 5 else '11620', today)
        haystack = ' '.join([item['title'], item['summary'], item.get('institution', ''), item.get('center', ''), *item['categories'], *item['keywords']]).lower()
        if not all(term in haystack for term in q.lower().split()):
            continue
        items.append(item)
    items.sort(key=lambda x: ((x['deadline'] or '9999-12-31') if sort == 'deadline' else x['title'], x['id']))
    return {'items': items[(page-1)*page_size:page*page_size], 'total': len(items), 'page': page, 'page_size': page_size,
            'categories': available, 'source': source, 'notice': '검색 결과는 신청 자격을 확정하지 않아요. 세부 조건은 공고에서 확인해 주세요.'}
