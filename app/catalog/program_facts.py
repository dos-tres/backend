"""공고의 원문과 검증된 추출 결과. 공개 API에는 원문·증거·연락처를 내보내지 않는다."""
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from pipeline import paths

VERSION='facts-v1'
FIELDS=('summary','target','method','application_period','schedule','place','preparations')

def clean_source(text):
    text=str(text or '')
    # 홍보 협조 메일 뒤 구분선은 실제 모집 본문 시작점이다.
    if re.search(r'홍보\s*협조|홍보.*요청|메일을\s*드',text):
        parts=re.split(r'-{3,}|={3,}',text,maxsplit=1)
        if len(parts)>1:text=parts[1]
    text=re.sub(r'안녕하세요[.!\s,~🙂:)]*.{0,100}?(?:입니다|드립니다)[.!\s🙂:)]*','',text)
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[이메일]',text)
    text=re.sub(r'(?<!\d)01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)','[연락처]',text)
    text=re.sub(r'(?:공간관리자|담당자|매니저)\s*[가-힣]{2,4}(?=\s|님|입니다|$)','담당자',text)
    return re.sub(r'\s+',' ',text).strip()

def fingerprint(source):
    return hashlib.sha256((VERSION+json.dumps(source,ensure_ascii=False,sort_keys=True)).encode()).hexdigest()

def verified(data,source):
    """모든 필드의 인용 구절 각각이 실제 원문에 있어야 저장한다."""
    text=' '.join(str(v) for v in source.values())
    out={}
    for key in FIELDS:
        fact=data.get(key)
        if not isinstance(fact,dict):continue
        value,evidence=fact.get('value'),fact.get('evidence')
        pieces=evidence if isinstance(evidence,list) else [evidence]
        if isinstance(value,str) and value.strip() and pieces and all(isinstance(part,str) and part.strip() and part.strip() in text for part in pieces):
            evidence=' / '.join(part.strip() for part in pieces)
            if key=='target' and re.search(r'제한.{0,3}없|누구나|무관',value) and not re.search(r'제한.{0,3}없|누구나|무관',evidence):continue
            if key=='summary' and re.search(r'안녕하세요|홍보\s*협조|공간관리자|[\w.+-]+@|01[016789][- .]?\d',value):continue
            out[key]={'value':value[:600],'evidence':evidence[:1500]}
    return out if out.get('summary') else None

@lru_cache(maxsize=2)
def _read(path,mtime):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return {}

def saved(item_id):
    p=paths.CACHE_DIR/'program_facts.json'
    try:return _read(str(p),p.stat().st_mtime_ns).get(item_id,{})
    except OSError:return {}

def public_facts(row):
    if row['kind']!='program':return {}
    p=row['payload'];record=saved(row['id']);facts=record.get('facts') or p.get('facts') or {}
    return {k:v['value'] for k,v in facts.items() if k in FIELDS and isinstance(v,dict) and v.get('value') and not (k=='target' and re.search(r'제한.{0,3}없|누구나|무관',v['value']) and not re.search(r'제한.{0,3}없|누구나|무관',v.get('evidence','')))}

def confirmed_links(p):
    # 직접 폼 주소만 신청 링크로 취급. 단축/기관 홈페이지는 자동 확정하지 않는다.
    return re.findall(r'https://(?:docs\.google\.com/forms/[^\s]+|forms\.gle/[^\s]+|form\.naver\.com/[^\s]+|[\w.-]*typeform\.com/[^\s]+|tally\.so/[^\s]+)',p.get('apply_urls',''))

def application_links(source):
    text=source.get('content','')
    links=[]
    for url in confirmed_links({'apply_urls':text}):
        at=text.find(url);context=text[max(0,at-180):at]
        if re.search(r'신청|접수',context) and not re.search(r'만족도|사후\s*설문|후기',context[-50:]):links.append(url)
    return list(dict.fromkeys(links))

def presentation(row):
    if row['kind']!='program':return {}
    p=row['payload'];f=public_facts(row);links=saved(row['id']).get('apply_urls',[]) or p.get('verified_apply_urls',[])
    summary=f.get('summary') or clean_source(p.get('summary'))
    if '홍보' in summary and re.search(r'메일|협조|요청',summary):summary='활동 소개를 정리 중이에요. 공식 공고를 함께 확인할 수 있어요.'
    method=f.get('method') or ('온라인 신청서로 신청해요.' if links else '방문해서 이용해요.' if row.get('access_type')=='visit' else '')
    return {'summary':summary,'support':summary,'activity_brief':summary,'target':f.get('target') or p.get('target',''),'method':method,'activity_place':f.get('place') or p.get('place',''),'activity_schedule':f.get('schedule') or p.get('prog_text',''),'documents':f.get('preparations',''),'apply_urls':' '.join(links),'apply_url':links[0] if links else ''}
