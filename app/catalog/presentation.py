"""Public catalog presentation fields shared by recommendation and browsing APIs."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from functools import lru_cache
import re
from app.catalog.regions import region_list


def split_labels(value):
    return list(dict.fromkeys(v.strip().replace('･', '·') for v in (value or '').split(',') if v.strip()))


def categories(payload, kind):
    legacy = {'교육': '교육·직업훈련', '복지문화': '금융·복지·문화', '참여권리': '참여·기반'}
    if kind == 'program':
        return split_labels(payload.get('category')) or ['센터 프로그램']
    return list(dict.fromkeys(legacy.get(v, v) for v in split_labels(payload.get('lclsfNm'))))


@lru_cache(maxsize=1)
def province_names():
    return {r['code'][:2]: r['label'].split()[0] for r in region_list()}


def region_label(row):
    codes = row.get('sido_cds') or []
    if len(set(codes)) >= 16:
        return '전국'
    names = province_names()
    return ' · '.join(dict.fromkeys(names.get(c, c) for c in codes)) or '지역 미제공'


def catalog_today():
    return datetime.now(ZoneInfo('Asia/Seoul')).date()


def application_info(row, today=None):
    today = today or catalog_today()
    p = row['payload']
    policy = row['kind'] == 'policy'
    raw = (p.get('aplyYmd') or p.get('aplyPrdSeCd_nm') or '') if policy else (p.get('aply_text') or '')
    start_raw = '' if policy else (p.get('aply_start') or '')
    dates = re.findall(r'\d{4}[-.]?\d{2}[-.]?\d{2}', raw if policy else start_raw)
    start = None
    if dates:
        try:
            digits = re.sub(r'\D', '', dates[0])
            start = date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
        except ValueError:
            pass
    deadline = row.get('deadline')
    if isinstance(deadline, str):
        deadline = date.fromisoformat(deadline)
    explicit_always = p.get('aplyPrdSeCd_nm') == '상시' if policy else bool(p.get('evergreen') or re.search(r'상시|연중', raw))
    if row.get('status') == 'closed' or deadline and deadline < today:
        status, label = 'closed', '마감'
    elif start and start > today:
        status, label = 'upcoming', '모집 예정'
    elif explicit_always:
        status, label = 'always_open', '상시'
    elif raw or deadline:
        status, label = 'open', '모집 중'
    else:
        status, label = 'unknown', '기간 미제공'
    if status == 'always_open':
        display = '상시'
    elif status == 'closed' and explicit_always:
        display = '모집 마감'
    else:
        display = raw or (f'~ {deadline.isoformat()}' if deadline else '기간 미제공')
    return {'application_status': status, 'application_status_label': label, 'application_period': display,
            'application_start': start.isoformat() if start else None, 'raw_application_period': raw}


def presentation_fields(row, today=None):
    p = row['payload']
    policy = row['kind'] == 'policy'
    return {'categories': categories(p, row['kind']), 'subcategories': split_labels(p.get('mclsfNm')) if policy else [],
            'keywords': split_labels(p.get('plcyKywdNm')) if policy else list(p.get('topics') or []),
            'region_label': region_label(row), **application_info(row, today)}
