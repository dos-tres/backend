"""Public collected center files, explicitly separate from program DB data."""
import csv
import json
import re
from functools import lru_cache
from pathlib import Path
from pipeline import paths
from app.catalog.browser import all_rows, full_item
from app.catalog.presentation import presentation_fields


@lru_cache(maxsize=1)
def center_guides():
    return json.loads(Path(__file__).with_name('center_guides.json').read_text(encoding='utf-8'))


def add_center_guide(item):
    guides = center_guides()
    guide = guides.get(item['id'])
    if guide is None and '서울청년센터' in item['name']:
        guide = guides['_seoul']
    if not guide:
        return item
    return {**item, 'guide': guide, 'address': guide.get('address') or item['address'], 'homepage': item['homepage'] or guide.get('homepage', '')}


def center_rows():
    runtime = paths.PROGRAM_DIR / 'centers.csv'
    if runtime.exists():
        with runtime.open(encoding='utf-8-sig', newline='') as stream:
            rows = [r for r in csv.DictReader(stream) if r.get('status') != 'removed']
        dataset = 'runtime'
    else:
        with (paths.SEED_PROGRAM_DIR / 'centers_seed.jsonl').open(encoding='utf-8') as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        dataset = 'seed'
    items = [{'id': str(r['cntrSn']), 'name': r.get('cntrNm', ''),
              'address': ' '.join(str(r.get(k) or '').strip() for k in ['cntrAddr', 'cntrDaddr']).strip(),
              'region_code': str(r.get('region_cd') or str(r.get('stdgCtpvCd', '')) + str(r.get('stdgSggCd', ''))),
              'district': r.get('stdgSggCdNm', ''), 'province': r.get('stdgCtpvCdNm', ''),
              'homepage': r.get('homepage') or r.get('cntrUrlAddr') or '',
              'updated_at': r.get('last_seen') or ''} for r in rows]
    return sorted((add_center_guide(item) for item in items), key=lambda r: (r['name'], r['id'])), dataset


def center_key(name):
    # Official Seoul branch labels omit the venue name in program crawls.
    match = re.search(r'서울청년센터\s*([가-힣]+)', name)
    return '서울청년센터' + match.group(1) if match else ''.join(name.split())


def program_centers(row):
    names = row['payload'].get('center_names') or []
    if isinstance(names, str):
        names = names.split(';')
    return {center_key(name.strip()) for name in names if name.strip()}


def browse_centers(q='', district='', session=None):
    rows, dataset = center_rows()
    rows = [r for r in rows if r['region_code'].startswith('11')]
    districts = sorted({r['district'] for r in rows if r['district']})
    programs, programs_source = all_rows(session)
    counts = {}
    for program in programs:
        if program['kind'] != 'program':
            continue
        is_open = presentation_fields(program)['application_status'] in {'open', 'always_open'}
        for key in program_centers(program):
            total, opened = counts.get(key, (0, 0))
            counts[key] = (total + 1, opened + int(is_open))
    rows = [{**r, 'program_count': counts.get(center_key(r['name']), (0, 0))[0], 'open_program_count': counts.get(center_key(r['name']), (0, 0))[1]} for r in rows]
    return {'items': [r for r in rows if (not district or r['district'] == district) and all(term in (r['name']+' '+r['address']).lower() for term in q.lower().split())],
            'districts': districts, 'source': 'file', 'dataset': dataset, 'programs_source': programs_source,
            'notice': '온통청년에서 수집한 실제 센터 정보예요. 현재 수집 파일을 조회하며 실시간 정보가 아니에요. 거리·운영 시간은 제공되지 않아요.'}


def center_detail(center_id, session):
    centers, dataset = center_rows()
    center = next((r for r in centers if r['id'] == center_id and r['region_code'].startswith('11')), None)
    if not center:
        return None
    rows, source = all_rows(session)
    normalized = center_key(center['name'])
    programs = []
    for row in rows:
        if row['kind'] == 'program' and normalized in program_centers(row):
            programs.append(full_item(row))
    return {'item': center, 'source': 'file', 'dataset': dataset, 'programs': programs, 'programs_source': source,
            'notice': '방문 전 공식 안내에서 최신 운영 시간과 이용 조건을 확인해 주세요. 지도는 센터 주소 기준이에요.'}
