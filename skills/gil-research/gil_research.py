#!/usr/bin/env python3
"""Direct HTTP research with per-source coverage and reproducible evidence."""
from __future__ import annotations
import argparse
import concurrent.futures
import datetime as dt
import hashlib
import http.cookiejar
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from urllib.parse import quote, urlencode, urljoin, urlparse, urldefrag
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
RESOURCES = json.loads((ROOT / 'resources.json').read_text(encoding='utf-8'))['sources']
ACTIVE_RESOURCES = [source for source in RESOURCES if source.get('active', True)]
ACTIVE_BY_ID = {source['id']: source for source in ACTIVE_RESOURCES}
BY_ID = {s['id']: s for s in RESOURCES}
UA = 'GILResearch/2.0 (public legal research; direct HTTP)'
CROSSREF_LOCK = threading.Lock()
CROSSREF_LAST = 0.0
MAX_BYTES = 40 * 1024 * 1024
ICJ_HOSTS = {'icj-cij.org', 'www.icj-cij.org'}
SSRN_HOSTS = {'papers.ssrn.com'}
HUDOC_HOSTS = {'hudoc.echr.coe.int'}
CLOUDFLARE_BYPASS_HELPER = ROOT / 'cloudflare_bypass.py'
# opil.ouplaw.com answers a burst of requests with an HTTP 405 human-verification
# page for a few minutes. A per-host gap keeps the adapter under that threshold.
HOST_INTERVALS = {'opil.ouplaw.com': 2.0}
HOST_LOCK = threading.Lock()
HOST_LAST = {}


def now():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def clean(value):
    if isinstance(value, list):
        return ' '.join(clean(v) for v in value)
    return BeautifulSoup(str(value or ''), 'html.parser').get_text(' ', strip=True)


def tokens(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.casefold()) if not unicodedata.combining(c))
    words = re.findall(r'\w+', value)
    return [w[:-3] + 'y' if len(w) > 4 and w.endswith('ies') else w[:-1] if len(w) > 3 and w.endswith('s') and not w.endswith('ss') else w for w in words]


def matches(query, text):
    haystack = set(tokens(text))
    return all(w in haystack for w in tokens(query))


def _host_matches(host, candidate):
    candidate = (candidate or '').strip().lower().lstrip('.')
    return bool(candidate) and (host == candidate or host.endswith('.' + candidate))


def browser_source(url):
    """Return the resources.json entry that governs requests to this host.

    Only sources declaring a ``user_agent`` take part. Some publisher platforms
    answer the generic research User-Agent with an access challenge while
    serving the same page to a browser-like agent.
    """
    host = (urlparse(url).hostname or '').lower()
    if not host:
        return None
    for source in RESOURCES:
        if not source.get('user_agent'):
            continue
        hosts = source.get('user_agent_hosts') or [urlparse(source.get('url', '')).hostname]
        if any(_host_matches(host, h) for h in hosts):
            return source
    return None


def atomic_write(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_bytes(body)
    temp.replace(path)


class RetrievalError(RuntimeError):
    pass


class HTTP:
    def __init__(self, cache, offline=False, ttl=86400, timeout=30, cookie_jar=None):
        self.cache = Path(cache)
        self.offline, self.ttl, self.timeout = offline, ttl, timeout
        self.session = requests.Session()
        self.session.headers['User-Agent'] = UA
        self.evidence = []
        self.cookie_jar = Path(cookie_jar) if cookie_jar else None
        self.had_session_cookies = False
        if self.cookie_jar:
            # Some publisher platforms only serve a filtered result page to a
            # session that has completed their redirect handshake. Keeping that
            # session in the cache directory removes three redirects per run.
            self.session.cookies = http.cookiejar.LWPCookieJar(str(self.cookie_jar))
            try:
                self.session.cookies.load(ignore_discard=True)
            except (OSError, http.cookiejar.LoadError):
                pass
            self.had_session_cookies = len(self.session.cookies) > 0

    def forget_session_cookies(self):
        """Drop a remembered browser session; True when there was one to drop."""
        if not self.had_session_cookies:
            return False
        self.had_session_cookies = False
        self.session.cookies.clear()
        if self.cookie_jar:
            try:
                self.cookie_jar.unlink()
            except OSError:
                pass
        return True

    @staticmethod
    def cache_paths(cache, url, params=None, headers=None):
        prepared = requests.Request('GET', url, params=params).prepare().url
        key_material = prepared
        if headers:
            key_material += '\n' + json.dumps(headers, sort_keys=True, ensure_ascii=True)
        key = hashlib.sha256(key_material.encode()).hexdigest()
        cache = Path(cache)
        return prepared, cache / (key + '.bin'), cache / (key + '.json')

    def store(self, url, body, meta, params=None, headers=None):
        prepared, bp, mp = self.cache_paths(self.cache, url, params, headers)
        stored = {
            **meta,
            'request_url': prepared,
            'source_url': meta.get('source_url') or prepared,
            'retrieved_at': meta.get('retrieved_at') or now(),
            'cached': False,
            'sha256': hashlib.sha256(body).hexdigest(),
            'bytes': len(body),
        }
        atomic_write(bp, body)
        atomic_write(mp, json.dumps(stored, ensure_ascii=False).encode('utf-8'))
        self.evidence.append(stored)
        return stored

    def get(self, url, params=None, headers=None):
        global CROSSREF_LAST
        if urlparse(url).scheme not in ('http', 'https'):
            raise RetrievalError('Only HTTP(S) URLs are supported')
        prepared, bp, mp = self.cache_paths(self.cache, url, params, headers)
        if bp.exists() and mp.exists() and (self.offline or time.time() - mp.stat().st_mtime < self.ttl):
            body = bp.read_bytes()
            meta = json.loads(mp.read_text(encoding='utf-8'))
            if hashlib.sha256(body).hexdigest() != meta['sha256']:
                raise RetrievalError('Cache hash mismatch: ' + prepared)
            meta = {**meta, 'cached': True}
            self.evidence.append(meta)
            return body, meta
        if self.offline:
            raise RetrievalError('Offline cache miss: ' + prepared)
        is_crossref = urlparse(prepared).hostname == 'api.crossref.org'
        if is_crossref:
            CROSSREF_LOCK.acquire()
            time.sleep(max(0, 1.05 - (time.monotonic() - CROSSREF_LAST)))
        host = urlparse(prepared).hostname or ''
        interval = HOST_INTERVALS.get(host)
        if interval:
            with HOST_LOCK:
                pause = interval - (time.monotonic() - HOST_LAST.get(host, 0.0))
                if pause > 0:
                    time.sleep(pause)
                HOST_LAST[host] = time.monotonic()
        try:
            for attempt in range(2):
                try:
                    with self.session.get(prepared, timeout=(12, self.timeout), stream=True, headers=headers) as response:
                        meta = {'request_url': prepared, 'source_url': response.url, 'http_status': response.status_code,
                                'content_type': response.headers.get('Content-Type', ''), 'retrieved_at': now(), 'cached': False,
                                'total': response.headers.get('X-WP-Total'), 'total_pages': response.headers.get('X-WP-TotalPages')}
                        if headers:
                            meta['request_headers'] = dict(headers)
                        self.evidence.append(meta)
                        if response.status_code != 200:
                            raise RetrievalError(f'HTTP {response.status_code}: {response.url}')
                        parts, size = [], 0
                        for part in response.iter_content(65536):
                            size += len(part)
                            if size > MAX_BYTES:
                                raise RetrievalError('Response exceeds 40 MiB limit: ' + prepared)
                            parts.append(part)
                        body = b''.join(parts)
                        if not body.strip():
                            raise RetrievalError('Empty HTTP response: ' + prepared)
                        head = body[:30000].lower()
                        if any(t in head for t in (b'<title>just a moment', b'<title>access denied', b'<title>human verification', b'403 - forbidden', b'our systems have detected unusual traffic', b'you need to enable javascript to run this app')):
                            raise RetrievalError('Access challenge or JavaScript shell: ' + prepared)
                        if re.search(r'/(login|sign-in)(\.|/|\?|$)', response.url, re.I):
                            raise RetrievalError('Redirected to login: ' + response.url)
                        meta.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
                        atomic_write(bp, body)
                        atomic_write(mp, json.dumps(meta, ensure_ascii=False).encode('utf-8'))
                        if self.cookie_jar and not self.offline:
                            try:
                                self.session.cookies.save(ignore_discard=True)
                            except (OSError, ValueError):
                                pass
                        return body, meta
                except (requests.Timeout, requests.ConnectionError) as exc:
                    if attempt == 0:
                        continue
                    raise RetrievalError(f'{type(exc).__name__}: {prepared}') from exc
                except requests.RequestException as exc:
                    raise RetrievalError(f'{type(exc).__name__}: {prepared}') from exc
        finally:
            if is_crossref:
                CROSSREF_LAST = time.monotonic()
                CROSSREF_LOCK.release()

    def json(self, url, params=None, headers=None):
        body, meta = self.get(url, params, headers)
        try:
            return json.loads(body), meta
        except (ValueError, UnicodeError) as exc:
            raise RetrievalError('Expected JSON: ' + meta['source_url']) from exc

    def soup(self, url, params=None, headers=None):
        body, meta = self.get(url, params, headers)
        if 'html' not in meta['content_type'].lower():
            raise RetrievalError('Expected HTML: ' + meta['source_url'])
        return BeautifulSoup(body, 'html.parser'), meta


def record(source, title, url, meta, kind='retrieved_metadata', **fields):
    return {'source': source['id'], 'title': clean(title), 'url': url, 'result_type': kind,
            'source_url': meta['source_url'], 'retrieved_at': meta['retrieved_at'], 'sha256': meta['sha256'], **fields}


def crossref(http, source, args):
    endpoint = 'https://api.crossref.org/' + ('prefixes/10.2139/works' if source['id'] == 'ssrn' else 'journals/' + source['issn'] + '/works')
    data, meta = http.json(endpoint, {'query': args.keyword, 'rows': args.limit, 'offset': args.offset})
    message = data.get('message', {})
    if not isinstance(message.get('items'), list):
        raise RetrievalError('Crossref schema changed: missing items')
    rows = []
    for work in message['items']:
        if source.get('container') and source['container'].casefold() not in [v.casefold() for v in work.get('container-title', [])]:
            raise RetrievalError('Crossref returned a record outside the requested journal')
        rows.append(record(source, '; '.join(work.get('title', [])), work.get('URL') or 'https://doi.org/' + work['DOI'], meta,
                           doi=work['DOI'], abstract=clean(work.get('abstract')), authors=[' '.join(filter(None, [a.get('given'), a.get('family')])) for a in work.get('author', [])],
                           published=work.get('published'), journal=work.get('container-title'), volume=work.get('volume'), issue=work.get('issue'), pages=work.get('page'),
                           fulltext_candidates=work.get('link', []), provider='Crossref', content_scope='metadata and available abstract; full text not yet acquired'))
    return rows, {'total': message.get('total-results'), 'scope': 'Crossref DOI registrations; relevance-ranked, not exact phrase search',
                  'status': 'fallback' if source['id'] == 'ssrn' else 'ok'}


def wordpress(http, source, args):
    headers = {'User-Agent': source['user_agent']} if source.get('user_agent') else None
    data, meta = http.json(source['api'], {'search': args.keyword, 'per_page': args.limit, 'offset': args.offset}, headers)
    if not isinstance(data, list):
        raise RetrievalError('WordPress schema changed: expected post array')
    rows = []
    for post in data:
        body = post.get('content', {}).get('rendered', '')
        text = clean(body)
        rows.append(record(source, post.get('title', {}).get('rendered', ''), post['link'], meta,
                           'retrieved_text' if text else 'retrieved_metadata', id=post['id'], published=post.get('date_gmt'),
                           modified=post.get('modified_gmt'), body_html=body, text=text,
                           content_scope='public rendered post body; protected posts may omit content', provider='WordPress REST posts API'))
    return rows, {'total': int(meta['total']) if meta.get('total') else None, 'scope': 'Native WordPress post search', 'status': 'ok'}


def scholar(http, source, args):
    page_start = args.offset // 10 * 10
    within = args.offset % 10
    soup, meta = http.soup('https://scholar.google.com/scholar', {'q': args.keyword, 'hl': 'en', 'start': page_start, 'num': 10})
    cards = soup.select('.gs_r.gs_or.gs_scl')
    if not cards and not soup.select_one('#gs_res_ccl_mid'):
        raise RetrievalError('Scholar did not return its result container; challenge or schema change')
    rows = []
    selected = cards[within:within + args.limit]
    for card in selected:
        heading = card.select_one('h3.gs_rt')
        anchor = heading.select_one('a[href]') if heading else None
        if not anchor:
            continue
        authors, excerpt, pdf = card.select_one('.gs_a'), card.select_one('.gs_rs'), card.select_one('.gs_or_ggsm a[href]')
        rows.append(record(source, heading.get_text(' ', strip=True), urljoin(meta['source_url'], anchor['href']), meta,
                           authors=authors.get_text(' ', strip=True) if authors else '', snippet=excerpt.get_text(' ', strip=True) if excerpt else '',
                           fulltext_url=urljoin(meta['source_url'], pdf['href']) if pdf else None, provider='Google Scholar HTML', content_scope='search record and snippet, not full text'))
    next_link = soup.select_one('a[aria-label="Next"], a[aria-label="Next page"]')
    return rows, {'status': 'ok', 'scope': 'One public Google Scholar result page; may be rate-limited on later runs',
                  'next_offset': args.offset + len(selected) if selected and (within + len(selected) < len(cards) or next_link) else None, 'total': None}


def hudoc(http, source, args):
    browser_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }
    api_headers = {
        **browser_headers,
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://hudoc.echr.coe.int/eng',
        'X-Requested-With': 'XMLHttpRequest',
    }
    query = 'contentsitename:ECHR AND "' + args.keyword.replace('"', '\\"') + '"'
    api_url = 'https://hudoc.echr.coe.int/app/query/results'
    params = {
        'query': query, 'select': 'itemid,docname,appno,doctype,judgementdate,respondent',
        'sort': '', 'start': args.offset, 'length': args.limit,
    }
    fallback_used = False
    if getattr(http, 'offline', False):
        data, meta = http.json(api_url, params, headers=api_headers)
    else:
        try:
            http.get('https://hudoc.echr.coe.int/eng', headers=browser_headers)
            data, meta = http.json(api_url, params, headers=api_headers)
        except RetrievalError as exc:
            last_status = http.evidence[-1].get('http_status') if http.evidence else None
            if last_status != 403 and not re.search(r'challenge|just a moment|human verification', str(exc), re.I):
                raise
            prepared = requests.Request('GET', api_url, params=params).prepare().url
            body, meta = fetch_via_cloudflare_bypass(
                http, prepared, exc, headers=api_headers, expected='json'
            )
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError) as parse_exc:
                raise RetrievalError('HUDOC browser fallback returned invalid JSON') from parse_exc
            fallback_used = True
    docs = data.get('results')
    if isinstance(docs, dict):
        docs = docs.get('docs')
    if not isinstance(docs, list):
        raise RetrievalError('HUDOC response schema not recognized; cannot infer zero results')
    rows = []
    for doc in docs:
        columns = doc.get('columns', doc)
        if isinstance(columns, list):
            columns = {c['name']: c.get('value') for c in columns}
        itemid = doc.get('itemid') or columns.get('itemid')
        if not itemid or not columns.get('docname'):
            raise RetrievalError('HUDOC record lacks itemid/docname')
        rows.append(record(source, columns['docname'], 'https://hudoc.echr.coe.int/eng?i=' + quote(str(itemid)), meta, fields=columns, provider='HUDOC'))
    scope = 'HUDOC search metadata'
    if fallback_used:
        scope += '; direct HTTPS was challenged and the JSON query was recovered through headless Chrome'
    return rows, {'status': 'ok', 'total': data.get('resultcount'), 'scope': scope}


def un_search(http, source, args):
    data, meta = http.json('https://search.un.org/api/search', {'collection': args.un_collection, 'q': args.keyword,
                          'row': 10, 'sort': 'relevance', 'currentPageNumber': args.offset // 10 + 1})
    if not isinstance(data.get('docs'), list):
        raise RetrievalError('UN API omitted docs even though a count was supplied; cannot infer zero results')
    rows = []
    for doc in data['docs'][args.offset % 10:args.offset % 10 + args.limit]:
        url = doc.get('url')
        if not url and doc.get('symbol'):
            url = 'https://documents.un.org/api/symbol/access?' + urlencode({'s': doc['symbol'], 'l': 'E'})
        if not url:
            raise RetrievalError('UN result has no document URL or symbol')
        rows.append(record(source, doc.get('title') or doc.get('symbol'), url, meta, snippet=clean(doc.get('highlightedText') or doc.get('body')),
                           symbol=doc.get('symbol'), language=doc.get('language'), provider='UN Unite Search', collection=args.un_collection,
                           content_scope='UN website index snippet; may include news, not only legal documents' if args.un_collection == 'un' else 'ODS document metadata'))
    return rows, {'status': 'fallback' if args.un_collection == 'un' else 'ok', 'total': data.get('numberDocsFound'),
                  'scope': 'UN Unite Search collection=' + args.un_collection + '; not UN Digital Library search',
                  'next_offset': args.offset + len(rows) if rows and data.get('numberDocsFound', 0) > args.offset + len(rows) else None}


def catalogue(http, source, args):
    rows, errors, inventories = [], [], []
    kind = source['id']
    if kind == 'icj':
        pages = ['https://www.icj-cij.org/list-of-all-cases']
    elif kind == 'avalon':
        seed = 'https://avalon.law.yale.edu/subject_menus/major.asp'
        root, _ = http.soup(seed)
        pages = list(dict.fromkeys(urljoin(seed, a['href']) for a in root.select('a[href]') if re.search(r'/(ancient|medieval|1[5-9]th|20th|21st)\.asp$', a['href'])))
    else:
        seed = 'https://treaties.un.org/Pages/ParticipationStatus.aspx?clang=_en'
        root, _ = http.soup(seed)
        pages = list(dict.fromkeys(urljoin(seed, a['href']) for a in root.select('a[href]') if re.search(r'Treaties\.aspx\?', a['href'], re.I)))
    if not pages:
        raise RetrievalError('Expected catalogue links not found')
    discovered = len(pages)
    pages = pages[:args.max_pages]

    def scan(url):
        client = HTTP(http.cache, http.offline, http.ttl, http.timeout)
        try:
            soup, meta = client.soup(url)
            links, valid_count = [], 0
            for anchor in soup.select('a[href]'):
                target = urldefrag(urljoin(url, anchor['href']))[0]
                path = urlparse(target).path
                valid = (kind == 'icj' and re.fullmatch(r'/(?:en/)?case/\d+', path)) or (kind == 'avalon' and re.match(r'/(?:\w+_century|ancient|medieval)/[^/]+\.asp$', path)) or (kind == 'unts' and 'viewdetails' in path.lower())
                title = anchor.get_text(' ', strip=True)
                if valid:
                    valid_count += 1
                if valid and matches(args.keyword, title):
                    links.append(record(source, title, target, meta, provider='official title catalogue', content_scope='catalogue title match; body not yet fetched'))
            if not valid_count:
                raise RetrievalError('Catalogue has no recognized document links: ' + url)
            return links, client.evidence, None
        except RetrievalError as exc:
            return [], client.evidence, str(exc)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for hits, evidence, error in pool.map(scan, pages):
            rows.extend(hits)
            http.evidence.extend(evidence)
            inventories.extend(e['source_url'] for e in evidence if e.get('sha256'))
            if error:
                errors.append(error)
    rows = list({row['url']: row for row in rows}.values())
    scope = {'icj': 'Official all-cases title catalogue; not judgment full-text search',
             'avalon': 'Century-index title catalogue; not corpus-wide full-text search',
             'unts': 'UNTC Secretary-General depositary (MTDSG) title catalogue ONLY; a subset and alternative to full UNTS registration search'}[kind]
    return rows[args.offset:args.offset + args.limit], {'status': 'partial' if errors or len(pages) < discovered else 'fallback' if kind == 'unts' else 'ok',
            'scope': scope, 'matched_in_scanned_catalogues': len(rows), 'total': None, 'catalogues_discovered': discovered, 'catalogues_requested': len(pages),
            'catalogues_retrieved': len(inventories), 'warnings': errors, 'next_offset': args.offset + args.limit if len(rows) > args.offset + args.limit else None}


def icj_search(http, source, args):
    """Search official ICJ case-document PDFs through Document Search."""
    page_size = max(10, min(args.limit, 100))
    page = args.offset // page_size + 1
    within = args.offset % page_size
    headers = {'User-Agent': source['user_agent']} if source.get('user_agent') else None
    params = {
        'search_api_fulltext': args.keyword,
        'items_per_page': page_size,
        'page': page - 1,
    }
    soup, meta = http.soup(source['url'], params, headers)
    view = soup.select_one('.view-document-search')
    if not view:
        raise RetrievalError('ICJ Document Search returned no result container; challenge or schema change')
    header = view.select_one('.view-header')
    total_match = re.search(r'About\s+([\d,]+)\s+results?', clean(header.get_text(' ')) if header else '', re.I)
    total = int(total_match.group(1).replace(',', '')) if total_match else None
    cards = view.select('.view-content .views-row')
    if total and not cards:
        raise RetrievalError('ICJ Document Search reported results but returned no rows; schema change')

    rows = []
    for card in cards:
        heading = card.select_one('h4 a[href]')
        if not heading:
            continue
        target = urljoin(meta['source_url'], heading['href'])
        case_link = card.select_one('p a[href*="/case/"]')
        paragraphs = card.select('p')
        details = clean(paragraphs[1].get_text(' ')) if len(paragraphs) > 1 else ''
        type_match = re.search(r'Type:\s*(.*?)(?:\s*\|\s*Date:|$)', details, re.I)
        date_match = re.search(r'Date:\s*(\d{4}-\d{2}-\d{2})', details, re.I)
        rows.append(record(
            source,
            heading.get_text(' ', strip=True),
            target,
            meta,
            case_title=clean(case_link.get_text(' ')) if case_link else '',
            case_url=urljoin(meta['source_url'], case_link['href']) if case_link else None,
            document_type=clean(type_match.group(1)) if type_match else '',
            date=date_match.group(1) if date_match else '',
            fulltext_url=target,
            provider='ICJ Document Search',
            content_scope='official document-search metadata; PDF text is acquired separately with --fetch',
        ))

    selected = rows[within:within + args.limit]
    page_start = (page - 1) * page_size
    consumed = page_start + within + len(selected)
    next_offset = consumed if selected and ((total is not None and consumed < total) or
                                                (total is None and len(cards) == page_size)) else None
    return selected, {
        'status': 'ok',
        'total': total,
        'scope': 'Official ICJ Document Search across case-related PDFs; rows are metadata, not judgment text',
        'next_offset': next_offset,
        'page': page,
        'page_size': page_size,
    }


def opil(http, source, args):
    """Search one Oxford Public International Law product.

    The platform answers the generic research agent with HTTP 403, so a
    browser-like User-Agent is required, and the session that carries the
    publisher's redirect handshake is cached on disk. Plain HTTP is enough; no
    browser automation is involved.

    The two facet families need opposite search state, measured separately:

    * the ``prd`` product facet (MPIL) needs ``access=all`` and ``level=all``.
      Without them the server drops the product filter silently and returns
      mixed products (genocide: 411 filtered rows become 3,814 MPIL+OSAIL rows).
    * the ``pc_*`` UUID facets (ORIL sub-series) must not receive ``access=all``,
      which silently narrows them (ORIL 1,011 rows become 4; the ICL sub-series
      365 become 3). ``level`` alone has no measured effect on either family.

    Because a silently wrong filter is worse than an error, the parsed rows are
    checked against the product the source declares.
    """
    page_size = 50 if args.limit > 20 else 20
    page = args.offset // page_size + 1
    within = args.offset % page_size
    headers = {'User-Agent': source['user_agent']} if source.get('user_agent') else None
    params = {'sfam': '', 'q': args.keyword, 'pageSize': page_size, 'sort': 'relevance', 'page': page}
    params.update(source.get('facets') or {})
    params.update(source.get('extra_params') or {})
    try:
        soup, meta = http.soup(source['search_url'], params, headers)
    except RetrievalError:
        # A remembered session can go stale; forget it and handshake again.
        if not http.forget_session_cookies():
            raise
        soup, meta = http.soup(source['search_url'], params, headers)
    total_match = re.search(r'You are looking at\s+[\d,]+\s*[\u2013\u2014-]\s*[\d,]+\s+of\s+([\d,]+)\s+results',
                            soup.get_text(' ', strip=True))
    blocks = soup.select('div.contentItem')
    if not blocks and not total_match:
        raise RetrievalError('OPIL search page carried neither results nor a result count; '
                             'access challenge or schema change, not zero results')
    total = int(total_match.group(1).replace(',', '')) if total_match else None
    rows, seen = [], set()
    for block in blocks:
        heading = block.select_one('h2.itemTitle a[href]')
        if not heading:
            raise RetrievalError('OPIL result block has no title link; schema change')
        target = urljoin(meta['source_url'], heading['href'])
        if target in seen:
            continue
        seen.add(target)
        fields = {}
        for definition in block.select('dl.metadata'):
            label, value = definition.select_one('dt'), definition.select_one('dd')
            if label and value:
                fields.setdefault(clean(label.get_text()), clean(value.get_text()))
        author = block.select_one('div.itemAuthor')
        excerpt = block.select_one('div.component-content-summary, div.excerpt')
        classes = block.get('class') or []
        if 'hasAccess' in classes:
            access = 'entry page readable in this session'
        elif 'locked' in classes:
            access = 'no full-text entitlement in this session; the entry page may hold only the headnote'
        else:
            access = 'access not stated by the result row'
        snippet_text = clean(excerpt.get_text()) if excerpt else fields.get('Core Issue(s)', '')
        rows.append(record(source, heading.get_text(' ', strip=True), target, meta,
                           author=clean(author.get_text()) if author else '',
                           product=fields.get('Product', ''), module=fields.get('Module', ''),
                           content_type=fields.get('Content type', ''), date=fields.get('Date', ''),
                           jurisdiction=fields.get('Jurisdiction', ''), subjects=fields.get('Subject(s)', ''),
                           core_issues=fields.get('Core Issue(s)', ''), snippet=snippet_text,
                           access=access,
                           provider='Oxford Public International Law product search',
                           content_scope='search record: title, citation metadata, jurisdiction, subject terms '
                                         'and the editorial core issue(s); not the report text'))
    products = sorted({row['product'] for row in rows if row.get('product')})
    expected = source.get('expected_product')
    if expected and products and not any(expected.lower() in p.lower() for p in products):
        raise RetrievalError('Product filter not applied: expected ' + expected +
                             '; the page returned ' + '; '.join(products))
    window = min(args.limit, max(page_size - within, 0))
    selected = rows[within:within + window]
    consumed = args.offset + len(selected)
    if total is not None:
        next_offset = consumed if selected and consumed < total else None
    else:
        next_offset = consumed if selected and len(rows) == page_size else None
    scope = ('OPIL product search limited to ' + source['name'] +
             '; rows are retrieval metadata (title, citation, jurisdiction, subject terms and any editorial '
             'core issue(s)), not report text')
    if total is not None:
        scope += '; the platform reported ' + str(total) + ' product-scoped matches'
    return selected, {
        'status': 'ok',
        'total': total,
        'scope': scope,
        'next_offset': next_offset,
        'page': page,
        'page_size': page_size,
        'products_observed': products,
    }


def document_links(soup, url):
    links, seen = [], set()
    for anchor in soup.select('a[href]'):
        target = urldefrag(urljoin(url, anchor['href']))[0]
        if target in seen or urlparse(target).scheme not in ('http', 'https'):
            continue
        if re.search(r'\.pdf(?:$|\?)', target, re.I) or '/api/symbol/access?' in target:
            seen.add(target)
            links.append({'title': anchor.get_text(' ', strip=True), 'url': target})
    return links


def is_icj_pdf_url(url):
    parsed = urlparse(url)
    return ((parsed.hostname or '').lower() in ICJ_HOSTS and parsed.scheme == 'https'
            and parsed.path.lower().endswith('.pdf'))


def is_ssrn_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if host in SSRN_HOSTS:
        return parsed.scheme == 'https' and parsed.path == '/sol3/papers.cfm'
    return (host == 'doi.org' and parsed.scheme == 'https'
            and re.match(r'^/10\.2139/ssrn\.\d+$', parsed.path, re.I) is not None)


def is_hudoc_document_url(url):
    parsed = urlparse(url)
    return ((parsed.hostname or '').lower() in HUDOC_HOSTS and parsed.scheme == 'https'
            and parsed.path == '/eng' and re.search(r'(?:^|&)i=', parsed.query) is not None)


def fetch_via_cloudflare_bypass(http, url, direct_error, headers=None, expected='auto'):
    if http.offline:
        raise RetrievalError('Offline cache miss for Cloudflare-protected URL: ' + url)
    if not CLOUDFLARE_BYPASS_HELPER.is_file():
        raise RetrievalError('Cloudflare bypass helper is missing: ' + str(CLOUDFLARE_BYPASS_HELPER))

    with tempfile.TemporaryDirectory(prefix='gil-cf-') as folder:
        output = Path(folder) / 'response.body'
        try:
            result = subprocess.run(
                [sys.executable, '-X', 'utf8', str(CLOUDFLARE_BYPASS_HELPER), url,
                 '--out', str(output), '--expect', expected],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=220,
            )
        except subprocess.TimeoutExpired as exc:
            raise RetrievalError('Cloudflare headless bypass timed out after 220 seconds') from exc
        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()
        if result.returncode != 0 or not output.is_file():
            detail = (stderr or stdout).splitlines()[-1] if (stderr or stdout) else 'no diagnostic output'
            raise RetrievalError('Cloudflare headless bypass failed: ' + detail)
        try:
            payload = json.loads(stdout.splitlines()[-1])
        except (IndexError, ValueError) as exc:
            raise RetrievalError('Cloudflare headless bypass returned invalid helper output') from exc
        body = output.read_bytes()
        kind = payload.get('kind')
        if kind == 'pdf' and not body.startswith(b'%PDF'):
            raise RetrievalError('Cloudflare headless bypass did not return a PDF')
        if kind == 'json':
            try:
                json.loads(body)
            except (ValueError, UnicodeError) as exc:
                raise RetrievalError('Cloudflare headless bypass did not return valid JSON') from exc
        meta = http.store(url, body, {
            'source_url': payload.get('url') or url,
            'http_status': payload.get('status_code', 200),
            'content_type': payload.get('content_type') or '',
            'retrieved_at': now(),
            'transport': 'cloudflare-bypass-headless',
            'browser_headless': bool(payload.get('browser_headless')),
            'bypass_kind': kind,
            'cloudflare_detected': bool(payload.get('cf_detected')),
            'browser_user_agent': payload.get('user_agent') or '',
            'bypass_elapsed_seconds': payload.get('elapsed_seconds'),
            'cloudflare_cookie_names': payload.get('cookie_names') or [],
            'direct_failure': str(direct_error),
        }, headers=headers)
        return body, meta


def fetch_icj_pdf_via_bypass(http, url, direct_error, headers=None):
    return fetch_via_cloudflare_bypass(http, url, direct_error, headers=headers, expected='pdf')


def fetch_ssrn_page_via_bypass(http, url, direct_error, headers=None):
    return fetch_via_cloudflare_bypass(http, url, direct_error, headers=headers, expected='html')


def fetch_hudoc_page_via_bypass(http, url, direct_error, headers=None):
    return fetch_via_cloudflare_bypass(
        http, url, direct_error, headers=headers, expected='rendered_html'
    )


def fetch(http, url):
    source = browser_source(url)
    headers = {'User-Agent': source['user_agent']} if source else None
    try:
        body, meta = http.get(url, headers=headers)
    except RetrievalError as exc:
        last_status = http.evidence[-1].get('http_status') if http.evidence else None
        challenge = re.search(r'challenge|just a moment|human verification|access denied', str(exc), re.I)
        if last_status != 403 and not challenge:
            raise
        if is_icj_pdf_url(url):
            body, meta = fetch_icj_pdf_via_bypass(http, url, exc, headers=headers)
        elif is_hudoc_document_url(url):
            body, meta = fetch_hudoc_page_via_bypass(http, url, exc, headers=headers)
        elif is_ssrn_url(url):
            body, meta = fetch_ssrn_page_via_bypass(http, url, exc, headers=headers)
        else:
            raise
        source = browser_source(meta.get('source_url', url)) or source
        if source and source.get('user_agent'):
            headers = {'User-Agent': source['user_agent']}
    if body.startswith(b'%PDF'):
        from pypdf import PdfReader
        try:
            reader = PdfReader(io.BytesIO(body))
            pages = [{'page': i + 1, 'text': page.extract_text() or ''} for i, page in enumerate(reader.pages)]
        except Exception as exc:
            raise RetrievalError('PDF extraction failed: ' + type(exc).__name__) from exc
        return {'result_type': 'retrieved_text' if any(p['text'].strip() for p in pages) else 'retrieved_binary',
                'content_scope': 'PDF page text; page numbers are PDF positions, not printed pages', 'pages': pages,
                'page_count': len(pages), 'ocr_needed': [p['page'] for p in pages if not p['text'].strip()], **meta}
    if 'html' in meta['content_type'].lower():
        soup = BeautifulSoup(body, 'html.parser')
        title = clean(soup.title.get_text()) if soup.title else ''
        if re.search(r'^(sign in|log in|access denied|just a moment)', title, re.I):
            raise RetrievalError('Login/access page, not document text')
        selectors = ['main', 'article', '[role="main"]', '.document', '#content']
        if source and source.get('content_selector'):
            selectors.insert(0, source['content_selector'])
        main = soup.select_one(', '.join(selectors)) or soup.body or soup
        links = document_links(main, meta['source_url'])
        for node in main.select('script, style, nav, header, footer, input, select, button, textarea, noscript, .breadcrumb, .breadcrumbs'):
            node.decompose()
        text = main.get_text('\n', strip=True)
        if len(text) < 100 or 'enable javascript' in text.lower()[:500]:
            raise RetrievalError('Insufficient document text or JavaScript shell')
        scope = (source or {}).get('fetch_scope') or 'HTML page text; a landing page is not the linked judgment/article full text'
        return {'result_type': 'retrieved_text', 'title': title, 'text': text, 'text_characters': len(text),
                'document_links': links, 'content_scope': scope, **meta}
    raise RetrievalError('Unsupported document type: ' + meta['content_type'])


def search_one(source, args):
    cookie_jar = Path(args.cache) / (source['id'] + '.cookies.txt') if source.get('session_cookies') else None
    http = HTTP(args.cache, args.offline, args.cache_ttl, args.timeout, cookie_jar)
    report = {'source': source['id'], 'source_name': source['name'], 'status': 'unavailable', 'results': [], 'warnings': []}
    try:
        kind = source['kind']
        if kind == 'manual':
            report.update(status='manual', scope=source['limitation'], manual_url=source['url'])
        else:
            adapter = {'crossref': crossref, 'wordpress': wordpress, 'scholar': scholar, 'hudoc': hudoc,
                       'icj': icj_search,
                       'un_api': un_search, 'catalogue': catalogue, 'opil': opil}[kind]
            rows, details = adapter(http, source, args)
            report.update(details)
            report['results'] = rows
            if args.fetch:
                for row in rows:
                    if row['result_type'] == 'retrieved_text':
                        continue
                    target = row.get('fulltext_url') or row['url']
                    try:
                        row['document'] = fetch(http, target)
                        row['text_characters'] = row['document'].get('text_characters')
                    except RetrievalError as exc:
                        row['fetch_error'] = str(exc)
                        report['warnings'].append('Document not acquired: ' + target)
                        report['status'] = 'partial'
    except RetrievalError as exc:
        report['warnings'].append(str(exc))
    except (KeyError, TypeError, ValueError) as exc:
        report['warnings'].append('Response schema/parse error: ' + str(exc))
    report['evidence'] = http.evidence
    report['returned'] = len(report['results'])
    if source['id'] not in ('opinio_juris', 'intl_law_observer', 'avalon') or report['warnings']:
        report['manual_handoff'] = {
            'skill': 'international-law-manual-research',
            'source': 'gil:' + source['id'],
            'required': False,
            'reason': '按全文、原站访问或完整覆盖需求评估；详见独立人工补检技能。'
        }
    report['pagination'] = {'offset': args.offset, 'limit': args.limit, 'next_offset': report.pop('next_offset', None)}
    if report['pagination']['next_offset'] is None and isinstance(report.get('total'), int) and report['total'] > args.offset + args.limit and report['results']:
        report['pagination']['next_offset'] = args.offset + args.limit
    return report


def markdown(report):
    if 'channels' not in report:
        return json.dumps(report, ensure_ascii=False, indent=2)
    lines = ['# ' + report['query'], '']
    for channel in report['channels']:
        lines.extend(['## ' + channel['source_name'] + ' — ' + channel['status'], '', channel.get('scope', ''), ''])
        lines.extend('Warning: ' + w for w in channel['warnings'])
        if channel.get('manual_url'):
            lines.append('Manual entry: ' + channel['manual_url'])
        for row in channel['results']:
            lines.extend(['', '### ' + row['title'], '', row['url'], '', 'Type: ' + row['result_type'], 'Retrieved: ' + row['retrieved_at']])
            text = row.get('text') or row.get('abstract') or row.get('snippet')
            if text:
                lines.extend(['', text])
            if row.get('document'):
                doc = row['document']
                lines.extend(['', 'Fetched document (' + doc['content_scope'] + '):', doc.get('text', '')])
                for page in doc.get('pages', []):
                    lines.extend(['', 'PDF page ' + str(page['page']), page['text']])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sp = sub.add_parser('search')
    sp.add_argument('keyword')
    sp.add_argument('--sources', default='all')
    sp.add_argument('--limit', type=int, default=5)
    sp.add_argument('--offset', type=int, default=0)
    sp.add_argument('--max-pages', type=int, default=35)
    sp.add_argument('--fetch', action='store_true', help='Fetch returned article/landing pages or PDF candidates')
    sp.add_argument('--un-collection', choices=['un', 'ods'], default='un')
    fp = sub.add_parser('fetch')
    fp.add_argument('url')
    for cmd in [sp, fp]:
        cmd.add_argument('--cache', default='.gil-cache')
        cmd.add_argument('--cache-ttl', type=int, default=86400)
        cmd.add_argument('--offline', action='store_true')
        cmd.add_argument('--timeout', type=int, default=30)
        cmd.add_argument('--out')
        cmd.add_argument('--format', choices=['json', 'markdown'], default='json')
    sub.add_parser('list')
    ip = sub.add_parser('info')
    ip.add_argument('source', choices=list(BY_ID))
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    exitcode = 0
    if args.command == 'list':
        report = ACTIVE_RESOURCES
    elif args.command == 'info':
        report = BY_ID[args.source]
    elif args.command == 'fetch':
        http = HTTP(args.cache, args.offline, args.cache_ttl, args.timeout)
        try:
            report = fetch(http, args.url)
        except RetrievalError as exc:
            report = {'result_type': 'fetch_error', 'error': str(exc)}
            exitcode = 1
        report['evidence'] = http.evidence
    else:
        if not args.keyword.strip() or not tokens(args.keyword):
            parser.error('keyword must contain searchable text')
        if not 1 <= args.limit <= 100 or args.offset < 0 or args.max_pages < 1:
            parser.error('limit must be 1..100; offset >= 0; max-pages >= 1')
        if args.sources == 'all':
            ids = [source['id'] for source in ACTIVE_RESOURCES]
        else:
            ids = list(dict.fromkeys(s.strip() for s in args.sources.split(',') if s.strip()))
        if not ids or any(s not in ACTIVE_BY_ID for s in ids):
            parser.error('sources must be all or comma-separated valid source IDs; see list')
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            channels = list(pool.map(lambda sid: search_one(BY_ID[sid], args), ids))
        report = {'schema_version': 2, 'query': args.keyword, 'generated_at': now(), 'offline': args.offline, 'channels': channels}
    output = markdown(report) if getattr(args, 'format', 'json') == 'markdown' else json.dumps(report, ensure_ascii=False, indent=2)
    if getattr(args, 'out', None):
        atomic_write(Path(args.out), output.encode('utf-8'))
        print(json.dumps({'out': str(Path(args.out).resolve()), 'bytes': len(output.encode('utf-8'))}, ensure_ascii=False))
    else:
        print(output)
    return exitcode


if __name__ == '__main__':
    raise SystemExit(main())
