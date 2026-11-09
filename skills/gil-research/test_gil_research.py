import argparse
import contextlib
import io
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from pypdf import PdfWriter

spec = importlib.util.spec_from_file_location('gil', Path(__file__).with_name('gil_research.py'))
gil = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gil)
bypass_spec = importlib.util.spec_from_file_location(
    'cloudflare_bypass', Path(__file__).with_name('cloudflare_bypass.py')
)
cloudflare_bypass = importlib.util.module_from_spec(bypass_spec)
bypass_spec.loader.exec_module(cloudflare_bypass)
META = {'source_url':'https://example.org/search','retrieved_at':'2026-09-22T00:00:00Z','sha256':'a'*64,'content_type':'text/html'}


def opil_block(index, title=None, access=True, product='Max Planck Encyclopedias of International Law [MPIL]'):
    return (
        '<div class="contentItem standardResult%s">'
        '<h2 class="itemTitle"><a href="/display/10.1093/law:epil/9780199231690/law-9780199231690-e%d">%s \u00bb </a></h2>'
        '<div class="itemAuthor">Author %d</div>'
        '<div class="bibliography searchBibliography">'
        '<dl class="metadata"><dt class="metadataLabel">Content type</dt><dd class="metadataValue">Encyclopedia entries</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Product</dt><dd class="metadataValue">%s</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Module</dt><dd class="metadataValue">Max Planck Encyclopedia of Public International Law [MPEPIL]</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Subject(s)</dt><dd class="metadataValue">War crimes \u2014 Superior orders</dd></dl>'
        '</div>'
        '<div class="component component-content-summary excerpt"><p>1 Entry text %d</p></div>'
        '</div>'
    ) % (' hasAccess' if access else '', index, title or 'Entry %d' % index, index, product, index)


def opil_page(count, total=411):
    body = ''.join(opil_block(i + 1) for i in range(count))
    return ('<html><body>' + body + '<div>You are looking at 1 \u2013 %d of %d results for :</div>'
            '</body></html>') % (count, total)


def oril_block(index, product='Oxford Reports on International Law [ORIL]', locked=True):
    """An ORIL row: no excerpt div, citation metadata plus editorial core issues."""
    return (
        '<div class="contentItem case-whole%s standardResult">'
        '<h2 class="itemTitle"><a href="/display/10.1093/law:icl/%d.case.1/law-icl-%d">Report %d \u00bb </a></h2>'
        '<div class="bibliography searchBibliography">'
        '<dl class="metadata"><dt class="metadataLabel">Date</dt><dd class="metadataValue">04 April 1997</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Content type</dt><dd class="metadataValue">International court decisions</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Product</dt><dd class="metadataValue">%s</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Module</dt><dd class="metadataValue">International Criminal Law [ICL]</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Jurisdiction</dt><dd class="metadataValue">International Criminal Tribunal for the Former Yugoslavia [ICTY]</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Subject(s)</dt><dd class="metadataValue">Command responsibility</dd></dl>'
        '<dl class="metadata"><dt class="metadataLabel">Core Issue(s)</dt><dd class="metadataValue">Whether command responsibility applied in internal armed conflict.</dd></dl>'
        '</div></div>') % (' locked' if locked else '', index, index, index, product)


def oril_page(count, total=1011):
    body = ''.join(oril_block(i + 1) for i in range(count))
    return ('<html><body>' + body + '<div>You are looking at 1 \u2013 %d of %d results for :</div>'
            '</body></html>') % (count, total)


def icj_page(count=20, total=4380):
    cards = []
    for index in range(count):
        number = index + 1
        cards.append(
            '<div class="views-row">'
            '<h4><a href="/sites/default/files/case-related/70/doc-%d.pdf">ICJ Document %d</a></h4>'
            '<p><b>Case:</b> <a href="/case/70">Case %d v. Case %d</a></p>'
            '<p><b>Type:&nbsp;</b>Judgment<span class="opacity-6"> | </span>'
            '<b>Date:</b> 1986-06-27</p>'
            '</div>' % (number, number, number, number)
        )
    return (
        '<html><body><div class="view view-document-search">'
        '<div class="view-header"><h2>Results</h2>About %d results</div>'
        '<div class="view-content row">%s</div></div></body></html>'
    ) % (total, ''.join(cards))


class FakeHTTP:
    def __init__(self, payload): self.payload = payload
    def json(self, *args, **kwargs): return self.payload, META
    def soup(self, *args, **kwargs): return BeautifulSoup(self.payload, 'html.parser'), META
    def get(self, *args, **kwargs): return self.payload, META


class RecordingHTTP:
    def __init__(self, payload): self.payload, self.calls = payload, []
    def json(self, *args, **kwargs):
        self.calls.append(('json', args, kwargs))
        return self.payload, META
    def get(self, *args, **kwargs):
        self.calls.append(('get', args, kwargs))
        return self.payload, META
    def soup(self, *args, **kwargs):
        self.calls.append(('soup', args, kwargs))
        return BeautifulSoup(self.payload, 'html.parser'), META


class RetrievalTests(unittest.TestCase):
    def test_active_sources_exclude_moved_sources(self):
        active = {source['id'] for source in gil.ACTIVE_RESOURCES}
        self.assertNotIn('icj', active)
        self.assertNotIn('echr', active)
        self.assertNotIn('mpil', active)
        self.assertNotIn('oril', active)
        self.assertNotIn('unts', active)
        self.assertNotIn('un_documents', active)
        self.assertNotIn('opinio_juris', active)
        self.assertNotIn('intl_law_observer', active)
        self.assertIn('cjil', active)
        self.assertIn('avalon', active)
        self.assertIn('icj', {source['id'] for source in gil.RESOURCES})

    def test_offline_never_uses_network(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(gil.requests.Session, 'get', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(gil.RetrievalError, 'Offline cache miss'):
                gil.HTTP(folder, offline=True).get('https://example.org/')

    def test_schema_failure_is_not_zero_results(self):
        args = argparse.Namespace(keyword='immunity', offset=0, limit=2, un_collection='ods')
        with self.assertRaisesRegex(gil.RetrievalError, 'omitted docs'):
            gil.un_search(FakeHTTP({'numberDocsFound':1000}), gil.BY_ID['un_documents'], args)

    def test_scholar_pagination_has_no_gap_with_small_limit(self):
        html = '<div id="gs_res_ccl_mid">' + ''.join(f'<div class="gs_r gs_or gs_scl"><h3 class="gs_rt"><a href="https://example.org/{i}">Doc {i}</a></h3></div>' for i in range(10)) + '</div>'
        args = argparse.Namespace(keyword='immunity', offset=2, limit=2)
        rows, info = gil.scholar(FakeHTTP(html), gil.BY_ID['google_scholar'], args)
        self.assertEqual([r['title'] for r in rows], ['Doc 2','Doc 3'])
        self.assertEqual(info['next_offset'], 4)

    def test_aspnet_form_does_not_erase_document(self):
        body = ('<html><title>Treaty</title><body><form><input name="token" value="abc"><div>' + 'Article 1. State immunity. ' * 10 + '</div><a href="text.pdf">Treaty PDF</a></form></body></html>').encode()
        data = gil.fetch(FakeHTTP(body), 'https://example.org/')
        self.assertIn('Article 1', data['text'])
        self.assertEqual(data['document_links'][0]['url'], 'https://example.org/text.pdf')

    def test_journal_boundary_enforced(self):
        data = {'message':{'items':[{'container-title':['Unrelated Journal'],'title':['Title'],'DOI':'10.1/x'}]}}
        args = argparse.Namespace(keyword='immunity',limit=2,offset=0)
        with self.assertRaisesRegex(gil.RetrievalError, 'outside the requested journal'):
            gil.crossref(FakeHTTP(data), gil.BY_ID['ejil'], args)

    def test_wordpress_returns_body_not_only_link(self):
        data = [{'id':1,'link':'https://example.org/post','title':{'rendered':'State &amp; immunity'},'content':{'rendered':'<p>Actual article text</p>'}}]
        args = argparse.Namespace(keyword='immunity',limit=2,offset=0)
        rows, _ = gil.wordpress(FakeHTTP(data),gil.BY_ID['opinio_juris'],args)
        self.assertEqual(rows[0]['result_type'],'retrieved_text')
        self.assertEqual(rows[0]['text'],'Actual article text')

    def test_hudoc_warms_session_before_json_query(self):
        args = argparse.Namespace(keyword='state immunity',limit=1,offset=0)
        http = RecordingHTTP({'resultcount':0,'results':[]})
        rows, info = gil.hudoc(http,gil.BY_ID['echr'],args)
        self.assertEqual(rows,[])
        self.assertEqual(info['total'],0)
        self.assertEqual(http.calls[0][0],'get')
        self.assertTrue(http.calls[0][1][0].endswith('/eng'))
        self.assertEqual(http.calls[1][0],'json')
        self.assertIn('Referer',http.calls[1][2]['headers'])

    def test_hudoc_uses_headless_json_after_direct_cloudflare_403(self):
        class ChallengedHUDOC:
            def __init__(self):
                self.evidence = [{'http_status': 403}]

            def get(self, *args, **kwargs):
                raise gil.RetrievalError('HTTP 403: Just a moment')

        payload = {
            'resultcount': 1,
            'results': {'docs': [{
                'columns': [
                    {'name': 'itemid', 'value': '001-123456'},
                    {'name': 'docname', 'value': 'Example v. State'},
                    {'name': 'appno', 'value': '12345/20'},
                ]
            }]},
        }
        args = argparse.Namespace(keyword='state immunity', limit=1, offset=0)
        meta = {**META, 'transport': 'cloudflare-bypass-headless'}
        with patch.object(gil, 'fetch_via_cloudflare_bypass',
                          return_value=(json.dumps(payload).encode(), meta)) as fallback:
            rows, info = gil.hudoc(ChallengedHUDOC(), gil.BY_ID['echr'], args)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Example v. State')
        self.assertEqual(info['total'], 1)
        self.assertIn('headless Chrome', info['scope'])
        self.assertEqual(fallback.call_args.kwargs['expected'], 'json')

    def test_un_pagination_and_snippet_arrays(self):
        data = {'docs':[{'title':str(i),'url':'https://example.org/'+str(i),'highlightedText':['<b>State</b>','immunity']} for i in range(10)],'numberDocsFound':50}
        args = argparse.Namespace(keyword='immunity',offset=2,limit=2,un_collection='un')
        rows, info = gil.un_search(FakeHTTP(data),gil.BY_ID['un_documents'],args)
        self.assertEqual([r['title'] for r in rows],['2','3'])
        self.assertEqual(info['next_offset'],4)
        self.assertEqual(rows[0]['snippet'],'State immunity')


    def test_opil_returns_product_scoped_rows(self):
        args = argparse.Namespace(keyword='command responsibility', limit=2, offset=0)
        rows, info = gil.opil(FakeHTTP(opil_page(2)), gil.BY_ID['mpil'], args)
        self.assertEqual(info['total'], 411)
        self.assertEqual(info['next_offset'], 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]['title'], 'Entry 1 \u00bb')
        self.assertTrue(rows[0]['url'].endswith('/display/10.1093/law:epil/9780199231690/law-9780199231690-e1'))
        self.assertEqual(rows[0]['product'], 'Max Planck Encyclopedias of International Law [MPIL]')
        self.assertEqual(rows[0]['module'], 'Max Planck Encyclopedia of Public International Law [MPEPIL]')
        self.assertEqual(rows[0]['subjects'], 'War crimes \u2014 Superior orders')
        self.assertEqual(rows[0]['snippet'], '1 Entry text 1')
        self.assertEqual(rows[0]['result_type'], 'retrieved_metadata')
        self.assertEqual(rows[0]['access'], 'entry page readable in this session')

    def test_icj_document_search_parses_fulltext_rows_and_pagination(self):
        args = argparse.Namespace(keyword='war crime', limit=2, offset=2)
        rows, info = gil.icj_search(FakeHTTP(icj_page()), gil.BY_ID['icj'], args)
        self.assertEqual([row['title'] for row in rows], ['ICJ Document 3', 'ICJ Document 4'])
        self.assertEqual(rows[0]['case_title'], 'Case 3 v. Case 3')
        self.assertEqual(rows[0]['document_type'], 'Judgment')
        self.assertEqual(rows[0]['date'], '1986-06-27')
        self.assertTrue(rows[0]['fulltext_url'].endswith('/doc-3.pdf'))
        self.assertEqual(info['total'], 4380)
        self.assertEqual(info['page'], 1)
        self.assertEqual(info['next_offset'], 4)

    def test_icj_schema_failure_is_not_zero_results(self):
        args = argparse.Namespace(keyword='war crime', limit=2, offset=0)
        with self.assertRaisesRegex(gil.RetrievalError, 'no result container'):
            gil.icj_search(FakeHTTP('<html><body><h1>Cloudflare challenge</h1></body></html>'),
                           gil.BY_ID['icj'], args)

    def test_icj_browser_fallback_is_limited_to_official_pdfs(self):
        self.assertTrue(gil.is_icj_pdf_url(
            'https://www.icj-cij.org/sites/default/files/case-related/70/070-19860627-JUD-01-00-EN.pdf'))
        self.assertFalse(gil.is_icj_pdf_url('https://www.icj-cij.org/case/70'))
        self.assertFalse(gil.is_icj_pdf_url('https://example.org/document.pdf'))
        self.assertFalse(gil.is_icj_pdf_url('http://www.icj-cij.org/document.pdf'))

    def test_ssrn_fallback_recognizes_paper_pages_and_doi(self):
        self.assertTrue(gil.is_ssrn_url('https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4819620'))
        self.assertTrue(gil.is_ssrn_url('https://doi.org/10.2139/ssrn.4819620'))
        self.assertFalse(gil.is_ssrn_url('https://papers.ssrn.com/sol3/results.cfm'))
        self.assertFalse(gil.is_ssrn_url('https://example.org/10.2139/ssrn.4819620'))

    def test_hudoc_document_fallback_recognizes_item_urls_only(self):
        self.assertTrue(gil.is_hudoc_document_url(
            'https://hudoc.echr.coe.int/eng?i=003-7235632-9843605'))
        self.assertFalse(gil.is_hudoc_document_url('https://hudoc.echr.coe.int/app/query/results'))
        self.assertFalse(gil.is_hudoc_document_url('https://example.org/eng?i=003-7235632-9843605'))

    def test_cloudflare_helper_normalizes_ssrn_doi_and_rejects_unknown_hosts(self):
        normalized, kind = cloudflare_bypass.normalize_target('https://doi.org/10.2139/ssrn.4819620')
        self.assertEqual(normalized, 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4819620')
        self.assertEqual(kind, 'html')
        with self.assertRaisesRegex(ValueError, 'approved'):
            cloudflare_bypass.normalize_target('https://example.org/test')
        hudoc, kind = cloudflare_bypass.normalize_target(
            'https://hudoc.echr.coe.int/eng?i=003-7235632-9843605'
        )
        self.assertEqual(hudoc, 'https://hudoc.echr.coe.int/eng?i=003-7235632-9843605')
        self.assertEqual(kind, 'rendered_html')

    def test_fetch_uses_headless_bypass_after_icj_pdf_403(self):
        buffer = io.BytesIO()
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.write(buffer)
        pdf = buffer.getvalue()

        class ChallengedICJHTTP:
            def __init__(self):
                self.evidence = [{'http_status': 403}]

            def get(self, *args, **kwargs):
                raise gil.RetrievalError('HTTP 403: Cloudflare challenge')

        http = ChallengedICJHTTP()
        bypass_meta = {**META, 'content_type': 'application/pdf', 'transport': 'cloudflare-bypass-headless'}
        with patch.object(gil, 'fetch_icj_pdf_via_bypass', return_value=(pdf, bypass_meta)) as fallback:
            data = gil.fetch(
                http,
                'https://www.icj-cij.org/sites/default/files/case-related/70/070-19860627-JUD-01-00-EN.pdf',
            )
        self.assertEqual(data['page_count'], 1)
        self.assertEqual(data['transport'], 'cloudflare-bypass-headless')
        fallback.assert_called_once()
        self.assertIn('Mozilla/5.0', fallback.call_args.kwargs['headers']['User-Agent'])

    def test_fetch_uses_cloudflare_page_fallback_for_ssrn_doi(self):
        page = ('<html><head><title>State Immunity by Example :: SSRN</title></head>'
                '<body><main><h1>State Immunity</h1><p>' + 'Article abstract text. ' * 12 +
                '</p><a href="paper.pdf">Download PDF</a></main></body></html>').encode()

        class ChallengedSSRN:
            def __init__(self):
                self.evidence = [{'http_status': 403}]

            def get(self, *args, **kwargs):
                raise gil.RetrievalError('HTTP 403: Just a moment')

        meta = {
            **META,
            'source_url': 'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4819620',
            'content_type': 'text/html;charset=UTF-8',
            'transport': 'cloudflare-bypass-headless',
        }
        with patch.object(gil, 'fetch_ssrn_page_via_bypass', return_value=(page, meta)) as fallback:
            data = gil.fetch(ChallengedSSRN(), 'https://doi.org/10.2139/ssrn.4819620')
        self.assertIn('Article abstract text', data['text'])
        self.assertEqual(data['transport'], 'cloudflare-bypass-headless')
        self.assertEqual(data['document_links'][0]['url'],
                         'https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4819620'.rsplit('/', 1)[0] + '/paper.pdf')
        fallback.assert_called_once()

    def test_fetch_uses_rendered_cloudflare_fallback_for_hudoc_document(self):
        page = ('<html><head><title>Example v. State - HUDOC</title></head><body><main>'
                '<h1>Example v. State</h1><p>' + 'Judgment body text. ' * 12 +
                '</p></main></body></html>').encode()

        class ChallengedHUDOCDocument:
            def __init__(self):
                self.evidence = [{'http_status': 403}]

            def get(self, *args, **kwargs):
                raise gil.RetrievalError('HTTP 403: Just a moment')

        meta = {
            **META,
            'source_url': 'https://hudoc.echr.coe.int/eng?i=003-7235632-9843605',
            'content_type': 'text/html; charset=utf-8',
            'transport': 'cloudflare-bypass-headless',
        }
        with patch.object(gil, 'fetch_hudoc_page_via_bypass', return_value=(page, meta)) as fallback:
            data = gil.fetch(
                ChallengedHUDOCDocument(),
                'https://hudoc.echr.coe.int/eng?i=003-7235632-9843605',
            )
        self.assertIn('Judgment body text', data['text'])
        self.assertEqual(data['transport'], 'cloudflare-bypass-headless')
        fallback.assert_called_once()
        self.assertEqual(fallback.call_args.kwargs['headers'], None)

    def test_opil_schema_failure_is_not_zero_results(self):
        args = argparse.Namespace(keyword='immunity', limit=2, offset=0)
        with self.assertRaisesRegex(gil.RetrievalError, 'neither results nor a result count'):
            gil.opil(FakeHTTP('<html><body><h1>403 ERROR</h1></body></html>'), gil.BY_ID['mpil'], args)

    def test_opil_offset_stays_within_the_fetched_page(self):
        args = argparse.Namespace(keyword='genocide', limit=5, offset=18)
        rows, info = gil.opil(FakeHTTP(opil_page(20)), gil.BY_ID['mpil'], args)
        self.assertEqual([r['title'] for r in rows], ['Entry 19 \u00bb', 'Entry 20 \u00bb'])
        self.assertEqual(info['next_offset'], 20)
        self.assertEqual(info['page'], 1)

    def test_opil_advances_to_the_next_result_page(self):
        args = argparse.Namespace(keyword='genocide', limit=5, offset=25)
        rows, info = gil.opil(FakeHTTP(opil_page(20)), gil.BY_ID['mpil'], args)
        self.assertEqual(info['page'], 2)
        self.assertEqual([r['title'] for r in rows],
                         ['Entry 6 \u00bb', 'Entry 7 \u00bb', 'Entry 8 \u00bb', 'Entry 9 \u00bb', 'Entry 10 \u00bb'])
        self.assertEqual(info['next_offset'], 30)

    def test_opil_sends_the_configured_browser_user_agent_and_product(self):
        args = argparse.Namespace(keyword='immunity', limit=1, offset=0)
        http = RecordingHTTP(opil_page(1))
        gil.opil(http, gil.BY_ID['mpil'], args)
        method, positionals, keywords = http.calls[0]
        self.assertEqual(method, 'soup')
        self.assertEqual(positionals[0], 'https://opil.ouplaw.com/search')
        self.assertEqual(positionals[1]['prd'], 'MPEIPRO')
        self.assertEqual(positionals[1]['pageSize'], 20)
        self.assertIn('Mozilla/5.0', positionals[2]['User-Agent'])

    def test_opil_forgets_a_stale_session_and_retries_once(self):
        class StaleSessionHTTP(RecordingHTTP):
            def soup(self, *args, **kwargs):
                self.calls.append(('soup', args, kwargs))
                if len(self.calls) == 1:
                    raise gil.RetrievalError('HTTP 403: challenge')
                return BeautifulSoup(self.payload, 'html.parser'), META
            def forget_session_cookies(self):
                self.calls.append(('forget', (), {}))
                return True
        args = argparse.Namespace(keyword='immunity', limit=1, offset=0)
        http = StaleSessionHTTP(opil_page(1))
        rows, _ = gil.opil(http, gil.BY_ID['mpil'], args)
        self.assertEqual([c[0] for c in http.calls], ['soup', 'forget', 'soup'])
        self.assertEqual(len(rows), 1)

    def test_fetch_uses_the_source_user_agent_and_content_selector(self):
        page = ('<html><head><title>Oxford Public International Law: Command Responsibility</title></head><body>'
                '<div id="utilityNav">' + 'navigation link ' * 40 + '</div>'
                '<div id="mainContent"><p>' + 'Entry paragraph text. ' * 12 + '</p></div>'
                '</body></html>').encode()
        http = RecordingHTTP(page)
        data = gil.fetch(http, 'https://opil.ouplaw.com/display/10.1093/law:epil/9780199231690/law-9780199231690-e273')
        self.assertIn('Mozilla/5.0', http.calls[0][2]['headers']['User-Agent'])
        self.assertIn('Entry paragraph text', data['text'])
        self.assertNotIn('navigation link', data['text'])
        self.assertEqual(data['content_scope'], gil.BY_ID['mpil']['fetch_scope'])

    def test_browser_source_matches_only_configured_hosts(self):
        self.assertEqual(gil.browser_source('https://opil.ouplaw.com/display/10.1093/x')['id'], 'mpil')
        self.assertEqual(gil.browser_source('https://www.icj-cij.org/case/70')['id'], 'icj')
        self.assertIsNone(gil.browser_source('https://example.org/page'))

    def test_http_cookie_jar_persists_and_forgets(self):
        with tempfile.TemporaryDirectory() as folder:
            jar = Path(folder) / 'mpil.cookies.txt'
            http = gil.HTTP(folder, cookie_jar=jar)
            self.assertFalse(http.had_session_cookies)
            self.assertFalse(http.forget_session_cookies())
            http.session.cookies.set_cookie(
                gil.requests.cookies.create_cookie(name='JSESSIONID', value='abc', domain='opil.ouplaw.com', path='/'))
            http.session.cookies.save(ignore_discard=True)
            self.assertTrue(jar.is_file())
            self.assertTrue(gil.HTTP(folder, cookie_jar=jar).had_session_cookies)
            reloaded = gil.HTTP(folder, cookie_jar=jar)
            self.assertTrue(reloaded.forget_session_cookies())
            self.assertFalse(jar.exists())
            self.assertFalse(reloaded.forget_session_cookies())

    def test_http_store_reuses_the_get_cache_key_with_headers(self):
        with tempfile.TemporaryDirectory() as folder:
            url = 'https://www.icj-cij.org/sites/default/files/case-related/70/test.pdf'
            headers = {'User-Agent': 'Mozilla/5.0 test'}
            body = b'%PDF-1.4\nfixture'
            writer = gil.HTTP(folder)
            writer.store(url, body, {'content_type': 'application/pdf', 'http_status': 200}, headers=headers)
            with patch.object(gil.requests.Session, 'get', side_effect=AssertionError('network')):
                cached, meta = gil.HTTP(folder, offline=True).get(url, headers=headers)
            self.assertEqual(cached, body)
            self.assertTrue(meta['cached'])

    def test_mpil_is_not_gated_behind_the_browser_preference(self):
        self.assertNotIn('requires_browser', gil.BY_ID['mpil'])
        self.assertTrue(gil.BY_ID['mpil']['session_cookies'])


    def test_mpil_keeps_the_search_state_its_product_facet_needs(self):
        args = argparse.Namespace(keyword='genocide', limit=1, offset=0)
        http = RecordingHTTP(opil_page(1, total=411))
        gil.opil(http, gil.BY_ID['mpil'], args)
        params = http.calls[0][1][1]
        self.assertEqual(params['prd'], 'MPEIPRO')
        self.assertEqual(params['access'], 'all')
        self.assertEqual(params['level'], 'all')

    def test_oril_uses_the_uuid_facet_and_no_access_state(self):
        args = argparse.Namespace(keyword='command responsibility', limit=1, offset=0)
        http = RecordingHTTP(oril_page(1))
        gil.opil(http, gil.BY_ID['oril'], args)
        url, params, headers = http.calls[0][1][0], http.calls[0][1][1], http.calls[0][1][2]
        self.assertEqual(url, 'https://opil.ouplaw.com/search')
        self.assertEqual(params['pc_17'], 'bdcb8d33-0914-4cd9-bd2b-c84ac21665f7')
        self.assertEqual(params['sfam'], '')
        self.assertNotIn('access', params)
        self.assertNotIn('level', params)
        self.assertIn('Mozilla/5.0', headers['User-Agent'])

    def test_oril_rows_carry_citation_core_issue_and_locked_access(self):
        args = argparse.Namespace(keyword='command responsibility', limit=2, offset=0)
        rows, info = gil.opil(FakeHTTP(oril_page(2)), gil.BY_ID['oril'], args)
        self.assertEqual(info['total'], 1011)
        self.assertEqual(info['products_observed'], ['Oxford Reports on International Law [ORIL]'])
        row = rows[0]
        self.assertEqual(row['title'], 'Report 1 \u00bb')
        self.assertEqual(row['date'], '04 April 1997')
        self.assertEqual(row['module'], 'International Criminal Law [ICL]')
        self.assertEqual(row['core_issues'], 'Whether command responsibility applied in internal armed conflict.')
        self.assertEqual(row['snippet'], 'Whether command responsibility applied in internal armed conflict.')
        self.assertIn('headnote', row['access'])
        self.assertEqual(row['result_type'], 'retrieved_metadata')
        self.assertTrue(row['url'].endswith('/display/10.1093/law:icl/1.case.1/law-icl-1'))

    def test_opil_rejects_a_page_whose_products_do_not_match(self):
        args = argparse.Namespace(keyword='genocide', limit=2, offset=0)
        wrong = oril_page(2).replace('Oxford Reports on International Law [ORIL]',
                                     'Oxford Scholarly Authorities on International Law [OSAIL]')
        with self.assertRaisesRegex(gil.RetrievalError, 'Product filter not applied'):
            gil.opil(FakeHTTP(wrong), gil.BY_ID['oril'], args)

    def test_oxford_reports_stays_a_manual_entry_for_whole_corpus_access(self):
        entry = gil.BY_ID['oxford_reports']
        self.assertEqual(entry['kind'], 'manual')
        self.assertIn('oril', entry['limitation'])
        self.assertNotIn('403 observed', entry['limitation'])


if __name__ == '__main__': unittest.main()
