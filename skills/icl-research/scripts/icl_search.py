"""Non-browser ICL research: public APIs, bounded HTTP crawling, cached local text.
Results explicitly distinguish native search, metadata, mirrors and incomplete crawls.
"""
from __future__ import annotations
import argparse, concurrent.futures, hashlib, html as html_lib, http.cookiejar, io, json, os, re, sys, threading, time, unicodedata
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, quote
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
CHANNELS = json.loads((ROOT / 'references/channels.json').read_text(encoding='utf-8'))
ACTIVE_CHANNELS = {k: v for k, v in CHANNELS.items() if v.get('active', True)}
LEGACY_CHANNELS = {k: v for k, v in CHANNELS.items() if not v.get('active', True)}
UA = 'ICLResearch/1.0 (public legal research; direct HTTP)'
# opil.ouplaw.com answers a burst of requests with an HTTP 405 human-verification
# page for a few minutes; a per-host gap keeps the adapter under that threshold.
HOST_INTERVALS={'opil.ouplaw.com':2.0}
HOST_LOCK=threading.Lock(); HOST_LAST={}
NOW = lambda: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())

def clean(value):
    value = str(value or '')
    return BeautifulSoup(value, 'html.parser').get_text(' ', strip=True) if '<' in value else html_lib.unescape(value)

def norm(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)).casefold() if not unicodedata.combining(c))

def terms(query):
    return re.findall(r'\w+', norm(query))

def matches(query, value):
    return all(t in norm(value) for t in terms(query))

def snippet(query, value, width=800):
    value = clean(value)
    positions = [norm(value).find(t) for t in terms(query)]
    start = max(0, min((i for i in positions if i >= 0), default=0) - 120)
    return ('…' if start else '') + value[start:start+width]

def channel_for_url(url):
    """Channel whose declared browser User-Agent governs this host, if any."""
    host = (urlparse(url).hostname or '').lower()
    if not host: return None
    for cfg in CHANNELS.values():
        if not cfg.get('user_agent'): continue
        hosts = [str(h).lower().lstrip('.') for h in (cfg.get('user_agent_hosts') or [urlparse(cfg.get('url','')).hostname]) if h]
        if any(host == h or host.endswith('.'+h) for h in hosts): return cfg
    return None

class AccessError(RuntimeError):
    pass

class HTTP:
    def __init__(self, cache, ttl=86400, offline=False, cookie_jar=None):
        self.cache = Path(cache); self.cache.mkdir(parents=True, exist_ok=True)
        self.ttl, self.offline = ttl, offline
        self.session = requests.Session(); self.session.headers['User-Agent'] = UA
        self.evidence, self.last = [], 0.0
        self.cookie_jar, self.had_session_cookies = (Path(cookie_jar) if cookie_jar else None), False
        if self.cookie_jar:
            # opil.ouplaw.com serves the product-filtered result page only to a
            # session that has finished its redirect handshake. Remembering that
            # session removes three redirects from every later run.
            self.session.cookies = http.cookiejar.LWPCookieJar(str(self.cookie_jar))
            try: self.session.cookies.load(ignore_discard=True)
            except (OSError, http.cookiejar.LoadError): pass
            self.had_session_cookies = len(self.session.cookies) > 0

    def forget_session_cookies(self):
        """Drop a remembered handshake; True when there was one to drop."""
        if not self.had_session_cookies: return False
        self.had_session_cookies = False
        self.session.cookies.clear()
        if self.cookie_jar:
            try: self.cookie_jar.unlink()
            except OSError: pass
        return True

    def get(self, url, params=None, method='GET', data=None, headers=None):
        if urlparse(url).scheme not in ('https', 'http'):
            raise AccessError('Only HTTP(S) URLs are supported')
        prepared = requests.Request(method, url, params=params, data=data).prepare()
        identity = method + prepared.url + str(prepared.body or '')
        if headers: identity += json.dumps(headers, sort_keys=True)
        key = hashlib.sha256(identity.encode()).hexdigest()
        bp, mp = self.cache/(key+'.bin'), self.cache/(key+'.json')
        if method == 'GET' and bp.exists() and mp.exists():
            meta = json.loads(mp.read_text(encoding='utf-8'))
            if self.offline or time.time()-mp.stat().st_mtime < self.ttl:
                self.evidence.append({**meta, 'cached':True})
                return bp.read_bytes(), meta
        if self.offline:
            raise AccessError('offline cache miss: '+prepared.url)
        host=urlparse(url).hostname or ''
        interval=HOST_INTERVALS.get(host)
        if interval:
            with HOST_LOCK:
                pause=interval-(time.monotonic()-HOST_LAST.get(host,0.0))
                if pause>0: time.sleep(pause)
                HOST_LAST[host]=time.monotonic()
        time.sleep(max(0, 0.35-(time.monotonic()-self.last)))
        self.last = time.monotonic()
        try:
            with self.session.request(method, url, params=params, data=data, headers=headers, timeout=(12,35), stream=True) as r:
                meta = {'url':r.url, 'status':r.status_code, 'content_type':r.headers.get('Content-Type',''), 'retrieved_at':NOW()}
                if headers: meta['request_headers'] = dict(headers)
                self.evidence.append(meta)
                if not r.ok:
                    raise AccessError(f'HTTP {r.status_code}: {r.url}')
                chunks, size = [], 0
                for b in r.iter_content(65536):
                    size += len(b)
                    if size > 40*1024*1024:
                        raise AccessError('40 MiB response limit: '+r.url)
                    chunks.append(b)
                body = b''.join(chunks)
                lower = body[:20000].lower()
                if any(x in lower for x in [
                    b'<title>just a moment',
                    b'<title>human verification',
                    b'<title>request not compliant',
                    b'<title>403 forbidden',
                    b'loading site please wait',
                    b'sorry, you have been blocked',
                    b'security service to protect itself',
                ]):
                    raise AccessError('access challenge: '+r.url)
                meta['sha256'] = hashlib.sha256(body).hexdigest()
                if method == 'GET':
                    # Atomic publication supports simultaneous read-only API queries.
                    import uuid
                    tmp = self.cache/(key+'.'+uuid.uuid4().hex+'.tmp')
                    tmp.write_bytes(body); tmp.replace(bp)
                    tmp = self.cache/(key+'.'+uuid.uuid4().hex+'.tmp')
                    tmp.write_text(json.dumps(meta), encoding='utf-8'); tmp.replace(mp)
                if self.cookie_jar and not self.offline:
                    try: self.session.cookies.save(ignore_discard=True)
                    except (OSError, ValueError): pass
                return body, meta
        except requests.RequestException as e:
            raise AccessError(f'{type(e).__name__}: {url}') from e

    def json(self, url, params=None):
        b,m = self.get(url,params)
        try: return json.loads(b),m
        except (ValueError, UnicodeError) as e: raise AccessError('Expected JSON, received '+m['content_type']+': '+m['url']) from e

def html(http, url, params=None, headers=None):
    b,m = http.get(url,params,headers=headers)
    s = BeautifulSoup(b,'html.parser')
    page_text = s.get_text(' ',strip=True).lower()
    if 'enable javascript to run this app' in page_text:
        raise AccessError('JavaScript shell without searchable content: '+url)
    if any(x in page_text for x in [
        'loading site please wait',
        'sorry, you have been blocked',
        'security service to protect itself',
    ]):
        raise AccessError('access challenge: '+url)
    return s,m

def result(title, url, via, text='', **extra):
    return {'title':clean(title), 'url':url, 'via':via, 'snippet':clean(text), **extra}

def pdf_pages(body):
    try:
        import pymupdf
        with pymupdf.open(stream=body, filetype='pdf') as doc:
            return [{'page':i+1,'text':page.get_text()} for i,page in enumerate(doc)]
    except ImportError:
        from pypdf import PdfReader
        return [{'page':i,'text':p.extract_text() or ''} for i,p in enumerate(PdfReader(io.BytesIO(body)).pages,1)]

def customary_books(http,q,n,offset):
    books=[('Volume I: Rules','78a250'),('Volume II: Practice, Part I','a5bc79'),('Volume II: Practice, Part II','d8df48')]
    hits=[];inventory=[];errors=[]
    for label,slug in books:
        u='https://www.legal-tools.org/doc/'+slug+'/pdf/'
        try:
            body,m=http.get(u)
            if not body.startswith(b'%PDF'):raise AccessError('Not a PDF: '+u)
            cache=http.cache/(m['sha256']+'.pages.json')
            if cache.exists():pages=json.loads(cache.read_text(encoding='utf-8'))
            else:
                pages=pdf_pages(body);cache.write_text(json.dumps(pages,ensure_ascii=False),encoding='utf-8')
            inventory.append({'volume':label,'url':u,'pages':len(pages),'sha256':m['sha256'],'retrieved_at':m['retrieved_at']})
            for p in pages:
                if matches(q,p['text']):hits.append(result('Customary International Humanitarian Law — '+label,u+'#page='+str(p['page']),'customary-book-local-text',snippet(q,p['text']),page=p['page'],volume=label,access='full-book PDF page text; dated edition, not current online practice',sha256=m['sha256']))
        except (AccessError,ValueError,ImportError) as e:errors.append(str(e))
    return hits[offset:offset+n],{'matched_pages':len(hits),'offset':offset,'limit':n,'next_offset':offset+n if offset+n<len(hits) else None,'volumes':inventory,'errors':errors}

def ltd(http, query, limit, offset=0, where=None):
    j,m = http.json('https://legal-tools.org/api/ltddocs/search', {'term':query, 'filter':json.dumps({'from':offset,'limit':limit,'where':{'deleted':False,**(where or {})}})})
    if not isinstance(j.get('results'),list): raise AccessError('Legal Tools response schema changed')
    rows=[]
    for record in j['results']:
        h=record['hit']; highlights=record.get('highlight') or {}
        txt=' '.join(str(v) for values in highlights.values() for v in (values if isinstance(values,list) else [values]))
        rows.append(result(h.get('title'),h.get('documentUrl') or ('https://www.legal-tools.org/doc/'+h['slug']+'/'),'legal-tools-api',snippet(query,txt or h.get('abstract','')),
            id=h.get('externalId') or h.get('id'), case_number=h.get('caseNumber'),case_name=h.get('caseName_en') or h.get('caseName'),date=h.get('dateCreated'),
            organisation=h.get('organisation'),author=h.get('author'),document_type=h.get('judicialDocumentType') or h.get('contentType'),
            source_role=h.get('source'),origin_url=(h.get('documentOrigin') or {}).get('url'),pdf_url=h.get('pdfURL'),
            download_permission_required=h.get('requireDownloadPermission'),authoritative_language=h.get('isAuthoritativeLanguage'),
            language_ids=h.get('languageIds'),access='search-metadata-and-index-snippet; full text not yet fetched'))
    return rows,j.get('total')

def ucr_public(http,q,n,offset):
    j,_=http.json('https://ucr.irmct.org/api/Record/GetRecentlyFiled')
    if not isinstance(j,list):raise AccessError('UCR public recent-filings schema changed')
    hits=[]
    fields=('documentTitle','caseNumber','caseDescription','docTypeDesc','docFilingDate','filingDate','signatureDate')
    for record in j:
        text=' '.join(str(record.get(k) or '') for k in fields)
        if matches(q,text):
            hits.append(result(record.get('documentTitle') or 'UCR recent filing','https://ucr.irmct.org/','ucr-public-recent',text,
                record_id=record.get('recordID'),document_id=record.get('documentID'),case_number=record.get('caseNumber'),
                case_name=record.get('caseDescription'),document_type=record.get('docTypeDesc'),date=record.get('docFilingDate') or record.get('filingDate'),
                access='public recent-filings metadata; full UCR search requires an authenticated account'))
    return dedupe(hits)[offset:offset+n],{'total':len(hits),'offset':offset,'limit':n,'next_offset':offset+n if offset+n<len(hits) else None}

def crossref(http,q,n,offset):
    j,_=http.json('https://api.crossref.org/journals/1478-1387/works',{'query':q,'rows':n,'offset':offset})
    rows=[]
    for h in j['message']['items']:
        rows.append(result('; '.join(h.get('title',[])),h['URL'],'crossref',clean(h.get('abstract','')),doi=h['DOI'],date=h.get('issued',{}).get('date-parts'),
            authors=[' '.join([a.get('given',''),a.get('family','')]).strip() for a in h.get('author',[])],journal=h.get('container-title'),volume=h.get('volume'),issue=h.get('issue'),pages=h.get('page'),access='metadata-only; full text may require subscription'))
    return rows,j['message'].get('total-results')

def cld(http,q,n,offset):
    j,_=http.json('https://cld.irmct.org/assets/homedata.json')
    hits=[r for r in j['data'] if matches(q,' '.join(str(x or '') for x in r[1:12]))]
    hits.sort(key=lambda r:str(r[4]),reverse=True)
    rows=[]
    for r in hits[offset:offset+n]:
        u='https://cld.irmct.org/home/jsonExtract/'+str(r[0]); warning=None
        try: extract,_=http.json(u); body=clean(extract.get('extract',''))
        except AccessError as e: body='';warning=str(e)
        rows.append(result(f'{r[2]} — {r[3]} — {r[1]}',urljoin('https://cld.irmct.org/',r[12]),'irmct-cld-json',snippet(q,body),
            id=str(r[0]),date=r[4],notions=r[1],extract_url=u,extract_text=body,extract_error=warning,
            access='official curated appellate extract; verify footnotes in judgment PDF'))
    return rows,len(hits)

def content(soup, selector=None):
    s=(soup.select_one(selector) if selector else None) or soup.select_one('main, [role="main"], #content, article') or soup
    for x in s.select('script, style, nav, header, footer, form, .breadcrumb, .breadcrumbs'): x.decompose()
    return s

def crawl(http, cfg, q, n, offset, max_pages, depth=1):
    queue=[(u,0,'') for u in cfg['seeds']];seen=set();rows=[];errors=[];fetched=0
    domains=cfg.get('domains') or [urlparse(u).hostname for u in cfg['seeds']]
    paths=cfg.get('paths',['/'])
    def allowed(u):
        p=urlparse(u)
        return p.scheme in ('http','https') and p.hostname in domains and any(p.path.startswith(x) for x in paths) and not re.search(r'\.(png|jpg|gif|mp4|mp3|zip|css|js)$',p.path,re.I) and 'pdfcreator' not in u
    while queue and fetched<max_pages:
        url,d,label=queue.pop(0);url=urldefrag(url)[0]
        if url in seen:continue
        seen.add(url);fetched+=1
        try:
            b,m=http.get(url)
            if b.startswith(b'%PDF'):
                for page in pdf_pages(b):
                    txt=page['text'];pn=page['page']
                    if matches(q,txt):rows.append(result(label or url,m['url']+'#page='+str(pn),'http-pdf',snippet(q,txt),page=pn,access='pdf-page-text'))
                continue
            soup=BeautifulSoup(b,'html.parser');title=clean(soup.title.text if soup.title else label or url)
            if 'enable javascript to run this app' in soup.get_text(' ',strip=True).lower():raise AccessError('JavaScript shell: '+url)
            s=content(soup);txt=s.get_text(' ',strip=True)
            if matches(q,txt):rows.append(result(title,m['url'],'http-local-text',snippet(q,txt),access='page-text'))
            # Matched catalogue links are useful even before the target is downloaded.
            for a in s.select('a[href]'):
                target=urldefrag(urljoin(m['url'],a['href']))[0];label=clean(a.text)
                if not allowed(target):continue
                if label and matches(q,label):rows.append(result(label,target,'http-catalogue-link',label,discovered_on=m['url'],access='link-label-only; target not fetched'))
                if d<depth and target not in seen:
                    queue.append((target,d+1,label))
            queue.sort(key=lambda v:(v[1], -sum(t in norm(v[2]+' '+v[0]) for t in terms(q))))
        except (AccessError,ValueError,ImportError) as e:errors.append(str(e))
    rows=dedupe(rows)
    rows.sort(key=lambda r:sum(t in norm(r['title']) for t in terms(q)),reverse=True)
    return rows[offset:offset+n], {'pages_attempted':fetched,'queued_unvisited':len(queue),'matched_in_visited_pages':len(rows),'errors':errors,'exhaustive':False}

def dedupe(rows):
    out={}
    for r in rows:
        # Preserve different CLD extracts of the same judgment.
        key=(r['url'].replace('http://','https://').rstrip('/'),r.get('id') if r['via']=='irmct-cld-json' else None)
        if key not in out:out[key]=r
    return list(out.values())

# International Crimes Database (Asser Institute).
#
# The public keyword search is a GET result list. The site's own quick-search
# box posts to /Home and answers with a 302 to this same URL, so the GET form
# is the native route, not a workaround. The ASP.NET renderer behind it is a
# plain server-side page: no JavaScript shell, no login, no session handshake.
#
# Verified 2026-10-15. Two traps are deliberately handled below instead of
# being reported as site unavailability:
#   * the Azure front door answers any query whose text contains "command"
#     followed by whitespace and another word with HTTP 403, so the phrase
#     `command responsibility` cannot be sent as one query by any route
#     (`command` alone returns 116 results; `command and control` and
#     `command structure` are blocked the same way);
#   * the server page size is fixed at five and ignores page-size parameters.
ICD_SEARCH = 'https://www.internationalcrimesdatabase.org/SearchResults/'
ICD_PAGE_SIZE = 5
ICD_FALLBACK_PAGES = 6

def icd_results_page(http,q,page):
    """One page of the public ICD result list: (rows, total, pages)."""
    s,m = html(http,ICD_SEARCH,{'q':q,'p':str(page)})
    block = s.select_one('div.search-results')
    if block is None:
        raise AccessError('ICD search results container missing; page layout changed or the request was filtered: '+m['url'])
    head = block.find('h2')
    label = clean(head.get_text(' ',strip=True)) if head else ''
    if re.search(r'no results',label,re.I):
        return [],0,0
    count = re.search(r'(\d+)\s+results',label)
    if not count:
        raise AccessError('ICD result count not recognised: '+label[:80])
    total = int(count.group(1))
    paging = re.search(r'page\s+(\d+)\s+of\s+(\d+)',block.get_text(' ',strip=True),re.I)
    pages = int(paging.group(2)) if paging else page
    nodes = [c for c in block.children if getattr(c,'name',None)]
    rows = []
    for i,node in enumerate(nodes):
        if node.name != 'strong': continue
        link = node.find('a',href=re.compile(r'/Case/\d+'))
        if not link: continue
        name = link.find('strong')
        title = clean(link.get_text(' ',strip=True))
        case_name = clean(name.get_text(' ',strip=True)) if name else title
        subtitle = title[len(case_name):].lstrip(' :') if name else ''
        citation = summary = ''
        for nxt in nodes[i+1:]:
            if nxt.name == 'strong': break
            if not citation and nxt.name == 'p':
                citation = clean(nxt.get_text(' ',strip=True))
            elif not summary and nxt.name == 'div' and 'search-summary' in (nxt.get('class') or []):
                summary = clean(nxt.get_text(' ',strip=True))
        date = re.search(r'\b\d{1,2}\s+[A-Z][a-z]{2,8}\s+\d{4}\b',citation)
        rows.append(result(title,urljoin(m['url'],link['href']),'icd-search',snippet(q,summary or citation),
            case_name=case_name,subtitle=subtitle,citation=citation,date=date.group(0) if date else None,
            access='public ICD search-result page: case name, citation and summary snippet; detail page not yet fetched'))
    return dedupe(rows),total,pages

def icd(http,q,n,offset):
    """Keyword search over the ICD case records."""
    base = (offset//ICD_PAGE_SIZE)*ICD_PAGE_SIZE
    page = base//ICD_PAGE_SIZE+1
    end = offset+n
    rows = [];total = pages = None;fetched = 0
    while (page-1)*ICD_PAGE_SIZE < end and fetched < 20:
        batch,total,pages = icd_results_page(http,q,page)
        rows.extend(batch);fetched += 1
        if not batch or (pages and page >= pages): break
        page += 1
    selected = rows[offset-base:offset-base+n]
    more = total is None or offset+len(selected) < total
    return selected,{'total':total,'offset':offset,'limit':n,'page_size':ICD_PAGE_SIZE,
        'page':base//ICD_PAGE_SIZE+1,'pages':pages,'pages_fetched':fetched,
        'next_offset':offset+len(selected) if selected and more else None}

def icd_token_fallback(http,q,n,offset):
    """Bounded term-by-term search used when the front door rejects a phrase.

    The site's search is relevance-ranked over the whole case record, and its
    front door filters a few English phrases that look like command-injection
    payloads. Single tokens are not filtered, so each term is queried
    separately and the case URLs are intersected locally. This is a labelled
    bounded approximation, not the site's own ranking or phrase semantics.
    """
    tokens = list(dict.fromkeys(terms(q)))[:4]
    if len(tokens) < 2:
        raise AccessError('ICD phrase rejected but no multi-term fallback applies: '+q)
    per_token = []
    for token in tokens:
        seen = {}
        for page in range(1,ICD_FALLBACK_PAGES+1):
            batch,total,pages = icd_results_page(http,token,page)
            if not batch: break
            for row in batch: seen.setdefault(row['url'],row)
            if pages and page >= pages: break
        per_token.append((token,seen))
    common = set.intersection(*[set(seen) for _,seen in per_token])
    ordered = [row for url,row in per_token[0][1].items() if url in common]
    for row in ordered:
        row['via'] = 'icd-token-intersection'
        row['matched_terms'] = tokens
        row['access'] = ('public ICD search results matched term-by-term and intersected locally; '
                         'bounded to %d result pages per term, not the site ranking' % ICD_FALLBACK_PAGES)
    info = {'terms':tokens,'pages_per_term':ICD_FALLBACK_PAGES,
            'candidates_per_term':{token:len(seen) for token,seen in per_token},
            'total':len(ordered),'offset':offset,'limit':n,
            'next_offset':offset+n if offset+n < len(ordered) else None}
    return ordered[offset:offset+n],info

def icrc(http,cfg,q,n,offset,lang):
    rows=[];counts={}
    for idx in cfg['indexes']:
        j,m=http.json(f'https://ihl-databases.icrc.org/{lang}/jsonapi/index/{idx}',{'page[limit]':n,'page[offset]':offset,'filter[fulltext]':q})
        if not isinstance(j.get('data'),list):raise AccessError('ICRC JSON:API schema changed')
        counts[idx]=j.get('meta',{}).get('count')
        for h in j['data']:
            a=h.get('attributes') or {};path=a.get('field_path');body=a.get('body') or a.get('field_cihl_content') or ''
            if isinstance(body,dict):body=body.get('processed') or body.get('value') or ''
            rows.append(result(a.get('title') or a.get('field_short_title') or a.get('field_treaty_content_title') or a.get('field_np_english_title') or f'{idx}: {h["id"]}',
                urljoin('https://ihl-databases.icrc.org/'+lang+'/',str(path).lstrip('/')) if path else h.get('links',{}).get('self',{}).get('href',m['url']),
                'icrc-jsonapi',snippet(q,body),id=h['id'],index=idx,metadata=a,access='api-record',language=lang))
    return rows,counts

def opil(http,cfg,q,n,offset):
    """Facet-scoped search of the Oxford Public International Law platform.

    The platform answers the generic research agent with HTTP 403, so a
    browser-like User-Agent is required, and the session carrying the
    publisher's redirect handshake is cached on disk. No browser automation is
    involved. gil-research uses the same request shape for its `mpil` and
    `oril` sources.

    The two facet families need opposite search state, measured separately:

    * `prd` (MPIL) needs `access=all` and `level=all`. Without them the server
      drops the product filter silently: genocide returns 411 filtered rows
      with them and 3,814 mixed MPIL/OSAIL rows without.
    * `pc_*` UUID facets (ORIL sub-series) must not receive `access=all`, which
      silently narrows them: the ORIL product drops from 1,011 rows to 4, and
      the ICL sub-series from 365 to 3. `level` alone had no measured effect.

    A silently wrong filter is worse than an error, so parsed rows are checked
    against the product the channel declares.
    """
    size=50 if n>20 else 20
    page,within=offset//size+1,offset%size
    params={'sfam':'','q':q,'pageSize':size,'sort':'relevance','page':page}
    params.update(cfg.get('facets') or {})
    params.update(cfg.get('extra_params') or {})
    headers={'User-Agent':cfg['user_agent']} if cfg.get('user_agent') else None
    try:
        soup,m=html(http,cfg['search_url'],params,headers)
    except AccessError:
        # A remembered handshake can go stale; forget it and retry once cold.
        if not http.forget_session_cookies(): raise
        soup,m=html(http,cfg['search_url'],params,headers)
    total_match=re.search(r'You are looking at\s+[\d,]+\s*[\u2013\u2014-]\s*[\d,]+\s+of\s+([\d,]+)\s+results',soup.get_text(' ',strip=True))
    blocks=soup.select('div.contentItem')
    if not blocks and not total_match:
        raise AccessError('OPIL search page carried neither results nor a result count; access challenge or schema change, not zero results')
    total=int(total_match.group(1).replace(',','')) if total_match else None
    rows,seen=[],set()
    for block in blocks:
        heading=block.select_one('h2.itemTitle a[href]')
        if not heading: raise AccessError('OPIL result block has no title link; schema change')
        url=urljoin(m['url'],heading['href'])
        if url in seen: continue
        seen.add(url)
        fields={}
        for d in block.select('dl.metadata'):
            label,value=d.select_one('dt'),d.select_one('dd')
            if label and value: fields.setdefault(clean(label.get_text()),clean(value.get_text()))
        author=block.select_one('div.itemAuthor');excerpt=block.select_one('div.component-content-summary, div.excerpt')
        classes=block.get('class') or []
        if 'hasAccess' in classes: access='entry page readable in this session'
        elif 'locked' in classes: access='no full-text entitlement in this session; the entry page may hold only the headnote'
        else: access='access not stated by the result row'
        core=fields.get('Core Issue(s)','')
        rows.append(result(heading.get_text(' ',strip=True),url,cfg.get('via','opil-search'),
            snippet(q,(excerpt.get_text(' ',strip=True) if excerpt else '') or core),
            author=clean(author.get_text()) if author else '',product=fields.get('Product',''),module=fields.get('Module',''),
            content_type=fields.get('Content type',''),date=fields.get('Date',''),jurisdiction=fields.get('Jurisdiction',''),
            subject_terms=fields.get('Subject(s)',''),core_issues=core,access=access,
            content_scope='search record with title, citation metadata, jurisdiction, subject terms and the editorial core issue(s); not the report text'))
    products=sorted({r['product'] for r in rows if r.get('product')})
    expected=cfg.get('expected_product')
    if expected and products and not any(expected.lower() in p.lower() for p in products):
        raise AccessError('Product filter not applied: expected '+expected+'; the page returned '+'; '.join(products))
    window=min(n,max(size-within,0));selected=rows[within:within+window];consumed=offset+len(selected)
    if total is None: nxt=consumed if selected and len(rows)==size else None
    else: nxt=consumed if selected and consumed<total else None
    return selected,{'total':total,'offset':offset,'limit':n,'next_offset':nxt,'page':page,'page_size':size}

def run_channel(cid,args):
    cfg=CHANNELS[cid]
    http=HTTP(args.cache,args.cache_ttl,args.offline,
        (Path(args.cache)/(cid+'.cookies.txt')) if cfg.get('session_cookies') else None)
    q,n,offset=args.query,args.limit,args.offset
    out={'channel':cid,'name':cfg['name'],'query':q,'scope':cfg['scope'],'status':'ok','warnings':[],'results':[],'pagination':{},'evidence':http.evidence}
    rows=[]
    def attempt(label,fn):
        try:return fn()
        except (AccessError,ValueError,KeyError,TypeError) as e:
            out['warnings'].append(label+': '+str(e));out['status']='partial';return None
    def add_ltd(where=None, query=None):
        v=attempt('Legal Tools',lambda:ltd(http,query or q,n,offset,where))
        if v:
            rows.extend(v[0])
            out['pagination']['legal-tools'+(':'+str(where['organisation']) if where and 'organisation' in where else '')]={'total':v[1],'offset':offset,'limit':n,'next_offset':offset+n if v[0] and (not isinstance(v[1],int) or offset+n<v[1]) else None}
    def add_crawl(config=cfg):
        v=attempt('HTTP crawl',lambda:crawl(http,config,q,n,offset,args.max_pages,args.depth))
        if v:
            rows.extend(v[0]);out['pagination']['crawl']=v[1];out['status']='partial'
            out['warnings']+=v[1]['errors'];out['warnings'].append('Bounded crawl: no hit does not establish absence from the site.')
    method=cfg['method']
    if method in ('crossref','cld'):
        v=attempt(method,lambda:(crossref if method=='crossref' else cld)(http,q,n,offset))
        if v:rows.extend(v[0]);out['pagination'][method]={'total':v[1],'offset':offset,'limit':n,'next_offset':offset+n if isinstance(v[1],int) and offset+n<v[1] else None}
    elif method=='opil':
        v=attempt('Oxford Public International Law',lambda:opil(http,cfg,q,n,offset))
        if v:
            rows.extend(v[0]);out['pagination'][cid]=v[1]
            out['products_observed']=sorted({r['product'] for r in v[0] if r.get('product')})
    # No standalone `legal-tools` channel here: the ICC Legal Tools Database is served by the
    # separate LegalToolsSearcher skill. `ltd()`/`add_ltd()` stay because other channels use
    # Legal Tools records as their labelled mirror fallback.
    elif method=='tribunal':
        add_crawl()
        if cid=='ictr':
            v=attempt('ICTR native search',lambda:html(http,'https://unictr.irmct.org/search',{'keys':q,'page':offset//15}))
            if v:
                for a in v[0].select('.search-results h3 a, .search-result h3 a')[:n]:rows.append(result(a.text,urljoin(v[1]['url'],a['href']),'ictr-http-search',access='search-result'))
        add_ltd({'organisation':cfg['organisation']})
    elif method=='ucr':
        out['status']='fallback';out['warnings'].append('UCR full search needs an authenticated account; no login attempted. Public recent filings are searched separately, and the following LTD results are not a complete UCR search.')
        v=attempt('UCR public recent filings',lambda:ucr_public(http,q,n,offset))
        if v:
            rows.extend(v[0]);out['pagination']['ucr-public-recent']=v[1];out['status']='partial'
        for org in ['International Criminal Tribunal for the former Yugoslavia (ICTY)','International Criminal Tribunal for Rwanda (ICTR)','International Residual Mechanism for Criminal Tribunals (IRMCT)']:
            add_ltd({'organisation':org})
    elif method in ('crawl','cmn','toaep'):
        add_crawl()
        if method=='toaep':add_ltd({'organisation':cfg['organisation']})
        if method=='cmn':
            # Lexsitus is a separate channel with its own skill; CMN here is
            # only its public site crawl.
            out['warnings'].append('Lexsitus/CLICC search moved to the standalone LexsitusSearcher skill; this channel covers casematrixnetwork.org pages only.')
    elif method=='icd':
        v=attempt('ICD search',lambda:icd(http,q,n,offset))
        if v:
            rows.extend(v[0]);out['pagination']['icd']=v[1]
        else:
            v=attempt('ICD term-by-term intersection',lambda:icd_token_fallback(http,q,n,offset))
            if v:
                rows.extend(v[0]);out['pagination']['icd-token-fallback']=v[1]
                out['warnings'].append('The site front door rejected this phrase (HTTP 403); these rows come from a bounded term-by-term intersection and are not the site\'s own phrase search.')
            else:add_crawl()
    elif method=='klamberg':
        out['status']='fallback';out['warnings'].append('Legacy iclklamberg.com returned origin DNS failure on 2026-09-15. Lexsitus/CLICC search now lives in the standalone LexsitusSearcher skill; this channel keeps the TOAEP book fallback only.')
        add_ltd({'organisation':'Torkel Opsahl Academic EPublisher (TOAEP)'}, 'Klamberg '+q)
    elif method=='icrc':
        v=attempt('ICRC native JSON:API',lambda:icrc(http,cfg,q,n,offset,args.lang))
        if v:rows.extend(v[0]);out['pagination']['icrc']=v[1]
        else:
            out['status']='fallback'
            if ' ' in q.strip():
                out['warnings'].append('ICRC native JSON:API may reject a multi-word phrase with a query-specific HTTP 403 or return a transient 503 even when the database is reachable; retry separate keywords, variants such as "superior responsibility", or a later run before treating the source as unavailable.')
            if cid=='icrc-customary':
                out['warnings'].append('Searches the English Rules and Practice book PDFs mirrored in Legal Tools, not the updated online practice database. Initial run downloads three volumes; subsequent searches reuse local page text.')
                v=attempt('Customary IHL books',lambda:customary_books(http,q,n,offset))
                if v:
                    rows.extend(v[0]);out['pagination']['customary-books']=v[1];out['warnings']+=v[1]['errors']
            else:
                out['warnings'].append('Only ICRC-authored holdings in Legal Tools are searched below; this is not a successful search of the full ICRC databases or current state practice.')
                add_ltd({'organisation':'International Committee of the Red Cross (ICRC)'})
    out['results']=dedupe(rows)
    if not rows and out['warnings']:out['status']='unavailable-or-incomplete'
    elif not rows:out['status']='no-results-in-queried-index'
    out['retrieved_at']=NOW()
    return out

def fetch(args):
    cfg=channel_for_url(args.url)
    headers={'User-Agent':cfg['user_agent']} if cfg and cfg.get('user_agent') else None
    http=HTTP(args.cache,args.cache_ttl,args.offline);b,m=http.get(args.url,headers=headers)
    if b.startswith(b'%PDF'):
        pages=pdf_pages(b)
        return {'url':m['url'],'sha256':m['sha256'],'pages':pages,'needs_ocr':not any(p['text'].strip() for p in pages),'evidence':http.evidence}
    if 'json' in m['content_type']:return {'url':m['url'],'data':json.loads(b),'evidence':http.evidence}
    s,m=html(http,args.url,headers=headers)
    text=content(s,cfg.get('content_selector') if cfg else None).get_text('\n',strip=True)
    out={'url':m['url'],'text':text,'text_characters':len(text),'sha256':m['sha256'],'evidence':http.evidence}
    if cfg and cfg.get('fetch_scope'): out['content_scope']=cfg['fetch_scope']
    return out

def safe_run_channel(cid,args):
    try:
        return run_channel(cid,args)
    except Exception as e:
        # A changed remote schema or bad PDF must not erase other channel reports.
        return {'channel':cid,'name':CHANNELS[cid]['name'],'query':args.query,'scope':CHANNELS[cid]['scope'],
                'status':'error','warnings':[type(e).__name__+': '+str(e)],'results':[],
                'pagination':{},'evidence':[],'retrieved_at':NOW()}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('list')
    s=sub.add_parser('search');s.add_argument('query');s.add_argument('--channels',default='all');s.add_argument('--limit',type=int,default=5);s.add_argument('--offset',type=int,default=0);s.add_argument('--max-pages',type=int,default=12);s.add_argument('--depth',type=int,default=1);s.add_argument('--lang',default='en');s.add_argument('--workers',type=int,default=3)
    f=sub.add_parser('fetch');f.add_argument('url')
    for x in (s,f):
        x.add_argument('--cache',default=str(Path.cwd()/'.icl-cache'));x.add_argument('--cache-ttl',type=int,default=86400);x.add_argument('--offline',action='store_true');x.add_argument('--out')
    args=p.parse_args()
    if args.command=='list':out={'channels':ACTIVE_CHANNELS,'legacy_channels':sorted(LEGACY_CHANNELS)}
    elif args.command=='fetch':
        try:out=fetch(args)
        except (AccessError,ValueError,ImportError) as e:out={'status':'unavailable','error':str(e)}
    else:
        if args.channels=='all':
            ids=list(ACTIVE_CHANNELS)
        else:
            ids=[x.strip() for x in args.channels.split(',')]
        unknown=set(ids)-set(ACTIVE_CHANNELS)
        if unknown:p.error('Unknown channels: '+', '.join(sorted(unknown)))
        if not args.query.strip() or not terms(args.query):p.error('Query must contain searchable text')
        if not 1<=args.limit<=50 or args.offset<0 or not 1<=args.max_pages<=2000 or not 0<=args.depth<=5 or not 1<=args.workers<=4:p.error('Bounds: limit 1..50, offset >=0, max-pages 1..2000, depth 0..5, workers 1..4')
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:reports=list(ex.map(lambda cid:safe_run_channel(cid,args),ids))
        out={'query':args.query,'timestamp':NOW(),'channels_requested':ids,'channels':reports,'note':'Coverage is per channel; native failure, bounded crawl and mirror fallback are not exhaustive searches.'}
    text=json.dumps(out,ensure_ascii=False,indent=2)
    if getattr(args,'out',None):
        path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8')
        if args.command=='search':
            print(json.dumps({'output':str(path.resolve()),'channels':[{'id':x['channel'],'status':x['status'],'hits':len(x['results'])} for x in out['channels']]},ensure_ascii=False))
        else:print(str(path.resolve()))
    else:print(text)

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    main()
