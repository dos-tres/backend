"""Collect official Seoul centre introductions, hours and notice links; no contacts/forms.
Run: python -m pipeline.programs.crawl.seoul_centers
"""
from __future__ import annotations
import json
import re
from datetime import datetime
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from pipeline.programs.crawl.common import Fetcher
from pipeline import paths

BASE = 'https://youth.seoul.go.kr/orang/cntr/'
KEY = '2309210001'
OUT = paths.PROGRAM_DIR / 'center_official.json'
SEED = paths.SEED_PROGRAM_DIR / 'center_official.json'


def url(page, **params):
    return BASE + page + '.do?' + urlencode({'key': KEY, **params})


def clean(text):
    text = re.sub(r'\b01[016789][-\s]?\d{3,4}[-\s]?\d{4}\b', '', text or '')
    text = re.sub(r'\b0\d{1,2}[-\s]\d{3,4}[-\s]\d{4}\b', '', text)
    text = re.sub(r'https?://\S+|[\w.+-]+@[\w.-]+', '', text)
    return re.sub(r'\s+', ' ', text).strip()


def parse_directory(html):
    soup = BeautifulSoup(html, 'html.parser')
    return list(dict.fromkeys(re.findall(r"goView\(['\"](CT\d+)['\"]\)", str(soup))))


def parse_intro(html, center_id):
    soup = BeautifulSoup(html, 'html.parser')
    box = soup.select_one('.center-infomation-box')
    content = soup.select_one('.center-introduce-wrap')
    if not box or not content:
        raise ValueError('Official centre structure missing')
    name = box.select_one('.lf strong')
    if not name:
        raise ValueError('Official centre identity missing')
    summary = box.select_one('.lf p')
    address = box.select_one('li.address')
    hours = box.select_one('li.time')
    facts = {}
    for row in content.select('table tr'):
        heading, value = row.find('th'), row.find('td')
        if heading and value:
            facts[clean(heading.get_text(' ', strip=True)).replace(' ', '')] = clean(value.get_text(' ', strip=True))
    sections = []
    body = content.select_one('.tith1')
    if body:
        for p in body.find_all(['p', 'li']):
            text = clean(p.get_text(' ', strip=True))
            if not text:
                continue
            if re.match(r'^[✅✔☑⚠]|^\d+[.)]\s', text):
                sections.append({'title': re.sub(r'^\d+[.)]\s*', '', text.lstrip('✅✔☑⚠️ ').strip()), 'body': ''})
            elif re.search(r'문의|연락처|이메일|전화', text):
                # End the factual introduction before any contact block.
                if '문의' in text:
                    break
            elif sections:
                sections[-1]['body'] = clean(sections[-1]['body'] + ' ' + text)
    if body and not any(section['body'] for section in sections):
        paragraphs = []
        for p in body.find_all(['p', 'li']):
            text = clean(p.get_text(' ', strip=True))
            if re.search(r'문의|연락처|이메일|전화', text):
                continue
            if text and text not in paragraphs:
                paragraphs.append(text)
        if paragraphs:
            sections = [{'title': '공간 안내', 'body': ' '.join(paragraphs)[:2500]}]
    return {'center_id': center_id, 'name': clean(name.get_text(' ', strip=True)),
            'summary': clean(summary.get_text(' ', strip=True)) if summary else '',
            'address': facts.get('위치') or (clean(address.get_text(' ', strip=True)) if address else ''),
            'hours': facts.get('운영시간') or facts.get('이용시간') or (clean(hours.get_text(' ', strip=True)) if hours else ''),
            'directions': facts.get('오시는길', ''), 'usage': facts.get('공간이용방법', ''),
            'sections': [s for s in sections if s['title'] and s['body']],
            'homepage': url('intro', cntrId=center_id), 'notice_url': url('notice', cntrId=center_id)}


def parse_notices(html, center_id):
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.select_one('table.board-st1')
    if not table:
        raise ValueError('Official notice structure missing')
    result = []
    for row in table.select('tbody tr'):
        link = row.find('a', onclick=re.compile(r"goView\(['\"]\d+['\"]\)"))
        if not link:
            continue
        post_id = re.search(r"goView\(['\"](\d+)['\"]\)", link['onclick']).group(1)
        date = re.search(r'\d{4}-\d{2}-\d{2}', row.get_text(' ', strip=True))
        result.append({'id': post_id, 'title': clean(link.get_text(' ', strip=True)),
                       'date': date.group() if date else '',
                       'url': url('noticeView', cntrId=center_id, pstSn=post_id)})
    return result[:10]


def collect(fetcher=None):
    fetcher = fetcher or Fetcher(delay=1, retries=1)
    previous = OUT if OUT.exists() else SEED
    items = json.loads(previous.read_text()).get('items', {}) if previous.exists() else {}
    ids = []
    # The official directory currently has two pages; stop at an empty/repeated page.
    for page in range(1, 11):
        _, html = fetcher.get(url('list', pageIndex=page))
        found = [i for i in parse_directory(html) if i not in ids]
        if not found:
            break
        ids.extend(found)
    if not ids:
        raise ValueError('No official centres found; previous data preserved')
    succeeded = failed = 0
    for center_id in ids:
        try:
            _, html = fetcher.get(url('intro', cntrId=center_id))
            item = parse_intro(html, center_id)
            item['fetched_at'] = datetime.now().astimezone().isoformat(timespec='seconds')
            old = items.get(center_id, {})
            try:
                _, html = fetcher.get(url('notice', cntrId=center_id))
                item['notices'] = parse_notices(html, center_id)
                item['notices_fetched_at'] = item['fetched_at']
            except Exception:
                if 'notices' in old:
                    item['notices'] = old['notices']
                    item['notices_fetched_at'] = old.get('notices_fetched_at', '')
            items[center_id] = item
            succeeded += 1
        except Exception:
            failed += 1  # Keep last successful snapshot. Never print response bodies/contact data.
    if not succeeded:
        raise ValueError('No introductions collected; previous data preserved')
    paths.write_atomic(OUT, json.dumps({'source': 'seoul-youth-official', 'items': items}, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'centres': len(ids), 'updated': succeeded, 'failed': failed, 'notices': sum(len(v.get('notices', [])) for v in items.values())}))


if __name__ == '__main__':
    collect()
