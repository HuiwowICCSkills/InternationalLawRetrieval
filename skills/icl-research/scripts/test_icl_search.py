"""Behavior checks that do not contact external services."""
import contextlib, io, json, os, sys, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import icl_search as s

def mpil_block(i,access=True,product='Max Planck Encyclopedias of International Law [MPIL]'):
    return ('<div class="contentItem standardResult%s">'
            '<h2 class="itemTitle"><a href="/display/10.1093/law:epil/9780199231690/law-9780199231690-e%d">Entry %d \u00bb </a></h2>'
            '<div class="itemAuthor">Author %d</div>'
            '<div class="bibliography searchBibliography">'
            '<dl class="metadata"><dt class="metadataLabel">Content type</dt><dd class="metadataValue">Encyclopedia entries</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Product</dt><dd class="metadataValue">%s</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Module</dt><dd class="metadataValue">Max Planck Encyclopedia of Public International Law [MPEPIL]</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Subject(s)</dt><dd class="metadataValue">War crimes \u2014 Superior orders</dd></dl>'
            '</div>'
            '<div class="component component-content-summary excerpt"><p>1 Entry text %d</p></div>'
            '</div>') % (' hasAccess' if access else '',i,i,i,product,i)

def mpil_page(count,total=411):
    return ('<html><body>'+''.join(mpil_block(i+1) for i in range(count))
            +'<div>You are looking at 1 \u2013 %d of %d results for :</div></body></html>') % (count,total)

def oril_block(i,product='Oxford Reports on International Law [ORIL]',locked=True):
    return ('<div class="contentItem case-whole%s standardResult">'
            '<h2 class="itemTitle"><a href="/display/10.1093/law:icl/%d.case.1/law-icl-%d">Report %d \u00bb </a></h2>'
            '<div class="bibliography searchBibliography">'
            '<dl class="metadata"><dt class="metadataLabel">Date</dt><dd class="metadataValue">04 April 1997</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Product</dt><dd class="metadataValue">%s</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Module</dt><dd class="metadataValue">International Criminal Law [ICL]</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Jurisdiction</dt><dd class="metadataValue">International Criminal Tribunal for the Former Yugoslavia [ICTY]</dd></dl>'
            '<dl class="metadata"><dt class="metadataLabel">Core Issue(s)</dt><dd class="metadataValue">Whether command responsibility applied in internal armed conflict.</dd></dl>'
            '</div></div>') % (' locked' if locked else '',i,i,i,product)

def oril_page(count,total=365):
    return ('<html><body>'+''.join(oril_block(i+1) for i in range(count))
            +'<div>You are looking at 1 \u2013 %d of %d results for :</div></body></html>') % (count,total)

class MPILHTTP:
    """Minimal stand-in for HTTP.get that records request shape."""
    def __init__(self,page): self.page,self.calls,self.evidence=page,[],[]
    def get(self,url,params=None,method='GET',data=None,headers=None):
        self.calls.append((url,params,headers))
        self.evidence.append({'url':url,'status':200})
        return self.page.encode(),{'url':url,'status':200,'content_type':'text/html','retrieved_at':'test','sha256':'a'*64}

def mpil_args(tmp,query='command responsibility',limit=2,offset=0):
    return SimpleNamespace(query=query,limit=limit,offset=offset,cache=tmp,cache_ttl=10,offline=False,
        lang='en',max_pages=1,depth=0)

def icd_entry(case_id,name,subtitle,doctype,date,court,summary):
    return ('<strong><a href="/Case/%d"><strong>%s</strong>: %s</a></strong>\n'
            '<p><strong>%s</strong>, %s, %s</p>\n'
            '<div class="search-summary"><p>%s</p></div>\n') % (case_id,name,subtitle,doctype,date,court,summary)

def icd_page(entries,total,pages,page=1):
    label = '%d results (ordered by relevance)' % total if total else 'no results'
    paging = ('<p class="paging-controls">page <strong>%d</strong> of %d</p>\n' % (page,pages)) if pages else ''
    return ('<html><head><title>ICD - Search results - Asser Institute</title></head><body>'
            '<div class="search-results"><a name="results"></a><h2>%s</h2>\n%s%s</div>'
            '</body></html>') % (label,paging,''.join(entries))

AKAYESU_ENTRY = icd_entry(51,'Akayesu','The Prosecutor v. Jean-Paul Akayesu','Judgement / Sentence',
    '2 September 1998','International Criminal Tribunal for Rwanda (Trial Chamber I), Tanzania',
    'The present judgment constitutes the first-ever judgment by an international court for the crime of genocide.')
NAHIMANA_ENTRY = icd_entry(152,'Nahimana et al.','The Prosecutor v. Ferdinand Mahimana, Jean-Bosco Barayagwiza and Hassan Ngeze',
    'Judgement and Sentence','3 December 2003','International Criminal Tribunal for Rwanda (Trial Chamber I), Tanzania',
    'The three Accused were tried jointly for their role in the Rwandan genocide.')

class ICDHTTP:
    """Stand-in for HTTP.get that keys stub pages by query and page number."""
    def __init__(self,pages): self.pages,self.calls,self.evidence=pages,[],[]
    def get(self,url,params=None,method='GET',data=None,headers=None):
        query=(params or {}).get('q');page=int((params or {}).get('p') or 1)
        self.calls.append((query,page))
        stub=self.pages.get(query)
        body=stub.get(page) if isinstance(stub,dict) else stub
        if body is None: raise s.AccessError('HTTP 403: '+url)
        self.evidence.append({'url':url,'status':200})
        return body.encode(),{'url':url,'status':200,'content_type':'text/html','retrieved_at':'test','sha256':'a'*64}

class ResearchBehavior(unittest.TestCase):
    def test_active_channels_exclude_moved_sources(self):
        self.assertEqual(
            set(s.ACTIVE_CHANNELS),
            {'jicj', 'cmn', 'toaep', 'klamberg'},
        )
        self.assertNotIn('mpil', s.ACTIVE_CHANNELS)
        self.assertIn('mpil', s.LEGACY_CHANNELS)
        self.assertNotIn('cilrap', s.ACTIVE_CHANNELS)
        self.assertIn('cilrap', s.LEGACY_CHANNELS)

    def test_diacritics_and_distinct_judgment_extracts(self):
        class H:
            def json(self,url,params=None):
                if url.endswith('homedata.json'):
                    return {'data':[[1,'Effective control','Hadžihasanović','Judgment','2006-01-01',None,None,None,None,None,None,None,'assets/j.pdf'],[2,'Effective control','Hadžihasanović','Judgment','2006-01-01',None,None,None,None,None,None,None,'assets/j.pdf']]},{}
                return {'extract':'<p>42. The material ability to prevent or punish.</p>'},{}
        rows,total=s.cld(H(),'Hadzihasanovic effective control',5,0)
        self.assertEqual(total,2)
        self.assertEqual(len(s.dedupe(rows)),2)
        self.assertIn('42.',rows[0]['extract_text'])
        self.assertEqual(s.cld(H(),'unrelated immunity',5,0)[1],0)

    def test_blocked_native_route_stays_visible_with_mirror_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(query='immunity',limit=2,offset=0,cache=tmp,cache_ttl=10,offline=False,lang='en',max_pages=1,depth=0)
            hit=s.result('Guidelines','https://www.legal-tools.org/doc/example/','legal-tools-api')
            with patch.object(s,'icrc',side_effect=s.AccessError('HTTP 403')),patch.object(s,'ltd',return_value=([hit],1)):
                report=s.run_channel('icrc-ihl',args)
            self.assertEqual(report['status'],'fallback')
            self.assertTrue(any('403' in w for w in report['warnings']))
            self.assertTrue(any('not a successful search' in w for w in report['warnings']))
            self.assertEqual(report['results'][0]['via'],'legal-tools-api')

    def test_icrc_multiword_failure_suggests_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=SimpleNamespace(query='command responsibility',limit=2,offset=0,cache=tmp,cache_ttl=10,offline=False,lang='en',max_pages=1,depth=0)
            hit=s.result('Guidelines','https://www.legal-tools.org/doc/example/','legal-tools-api')
            with patch.object(s,'icrc',side_effect=s.AccessError('HTTP 403')),patch.object(s,'ltd',return_value=([hit],1)):
                report=s.run_channel('icrc-ihl',args)
            self.assertTrue(any('retry separate keywords' in w.lower() for w in report['warnings']))

    def test_ucr_public_recent_filings_are_labelled_partial(self):
        class H:
            def json(self,url,params=None):
                return [
                    {'documentTitle':'Order on command responsibility','caseNumber':'MICT-22-124','caseDescription':'Nzuwonemeye','docTypeDesc':'Order','docFilingDate':'12/10/2026','recordID':1,'documentID':2},
                    {'documentTitle':'Unrelated procedural order','caseNumber':'MICT-21-001','caseDescription':'Other','docTypeDesc':'Order','docFilingDate':'11/10/2026','recordID':3,'documentID':4},
                ],{}
        rows,info=s.ucr_public(H(),'command responsibility',10,0)
        self.assertEqual(info['total'],1)
        self.assertEqual(rows[0]['via'],'ucr-public-recent')
        self.assertEqual(rows[0]['case_number'],'MICT-22-124')
        self.assertIn('full UCR search requires',rows[0]['access'])

    def test_book_search_checks_pages_not_just_catalogue_title(self):
        class H:
            def __init__(self,cache):self.cache=cache
            def get(self,url):return b'%PDF fixture',{'sha256':'sample','retrieved_at':'test'}
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            cache=Path(tmp)
            (cache/'sample.pages.json').write_text(json.dumps([{'page':1,'text':'Contents'},{'page':2,'text':'Command responsibility requires effective control.'}]),encoding='utf-8')
            rows,p=s.customary_books(H(cache),'command responsibility',2,1)
            self.assertEqual(p['matched_pages'],3)
            self.assertEqual(len(rows),2)
            self.assertTrue(all(r['page']==2 for r in rows))
            self.assertEqual(rows[0]['volume'],'Volume II: Practice, Part I')
            self.assertFalse(s.customary_books(H(cache),'unrelated immunity',2,0)[0])

    def test_offline_cache_miss_does_not_use_network(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(s.requests.Session,'request',side_effect=AssertionError('network used')):
            with self.assertRaisesRegex(s.AccessError,'offline cache miss'):
                s.HTTP(tmp,offline=True).get('https://example.org/legal')

    def test_unexpected_source_failure_is_not_a_zero_hit_success(self):
        with patch.object(s,'run_channel',side_effect=RuntimeError('remote schema changed')):
            report=s.safe_run_channel('icd',SimpleNamespace(query='Akayesu'))
        self.assertEqual(report['status'],'error')
        self.assertEqual(report['channel'],'icd')
        self.assertIn('remote schema changed',report['warnings'][0])

    def test_mpil_returns_product_scoped_rows(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(s,'HTTP',lambda *a,**k: MPILHTTP(mpil_page(2))):
            report=s.run_channel('mpil',mpil_args(tmp))
        self.assertEqual(report['status'],'ok')
        self.assertEqual(report['pagination']['mpil']['total'],411)
        self.assertEqual(report['pagination']['mpil']['next_offset'],2)
        row=report['results'][0]
        self.assertEqual(row['title'],'Entry 1 \u00bb')
        self.assertEqual(row['via'],'mpil-search')
        self.assertEqual(row['author'],'Author 1')
        self.assertEqual(row['product'],'Max Planck Encyclopedias of International Law [MPIL]')
        self.assertEqual(row['module'],'Max Planck Encyclopedia of Public International Law [MPEPIL]')
        self.assertEqual(row['subject_terms'],'War crimes \u2014 Superior orders')
        self.assertEqual(row['access'],'entry page readable in this session')
        self.assertIn('/display/10.1093/law:epil/',row['url'])

    def test_mpil_requests_the_configured_product_and_browser_user_agent(self):
        page=mpil_page(1)
        http=MPILHTTP(page)
        rows,info=s.opil(http,s.CHANNELS['mpil'],'command responsibility',1,0)
        url,params,headers=http.calls[0]
        self.assertEqual(url,'https://opil.ouplaw.com/search')
        self.assertEqual(params['prd'],'MPEIPRO')
        self.assertEqual(params['pageSize'],20)
        self.assertEqual(params['page'],1)
        self.assertIn('Mozilla/5.0',headers['User-Agent'])
        self.assertEqual(len(rows),1)

    def test_mpil_missing_results_and_count_is_a_failure_not_zero_hits(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(s,'HTTP',lambda *a,**k: MPILHTTP('<html><body><h1>403 ERROR</h1></body></html>')):
            failed=s.run_channel('mpil',mpil_args(tmp))
        self.assertEqual(failed['status'],'unavailable-or-incomplete')
        self.assertTrue(any('neither results nor a result count' in w for w in failed['warnings']))

    def test_mpil_offset_stays_within_the_fetched_page(self):
        rows,info=s.opil(MPILHTTP(mpil_page(20)),s.CHANNELS['mpil'],'genocide',5,18)
        self.assertEqual([r['title'] for r in rows],['Entry 19 \u00bb','Entry 20 \u00bb'])
        self.assertEqual(info['next_offset'],20)
        self.assertEqual(info['page'],1)

    def test_mpil_advances_to_the_next_result_page(self):
        rows,info=s.opil(MPILHTTP(mpil_page(20)),s.CHANNELS['mpil'],'genocide',5,25)
        self.assertEqual(info['page'],2)
        self.assertEqual([r['title'] for r in rows],
            ['Entry 6 \u00bb','Entry 7 \u00bb','Entry 8 \u00bb','Entry 9 \u00bb','Entry 10 \u00bb'])
        self.assertEqual(info['next_offset'],30)

    def test_mpil_forgets_a_stale_handshake_and_retries_once(self):
        class Stale(MPILHTTP):
            def __init__(self,page): super().__init__(page); self.forgot=0
            def get(self,url,params=None,method='GET',data=None,headers=None):
                self.calls.append(('soup',url,params,headers))
                if not self.forgot: raise s.AccessError('HTTP 403: challenge')
                return self.page.encode(),{'url':url,'status':200,'content_type':'text/html','retrieved_at':'test','sha256':'a'*64}
            def forget_session_cookies(self): self.forgot+=1; return True
        http=Stale(mpil_page(1))
        rows,_=s.opil(http,s.CHANNELS['mpil'],'immunity',1,0)
        self.assertEqual(http.forgot,1)
        self.assertEqual(len(http.calls),2)
        self.assertEqual(len(rows),1)

    def test_mpil_channel_is_not_gated_behind_the_browser_preference(self):
        self.assertNotIn('requires_browser',s.CHANNELS['mpil'])
        self.assertTrue(s.CHANNELS['mpil']['session_cookies'])

    def test_channel_for_url_matches_only_configured_hosts(self):
        self.assertEqual(s.channel_for_url('https://opil.ouplaw.com/display/10.1093/x')['method'],'opil')
        self.assertIsNone(s.channel_for_url('https://example.org/page'))

    def test_http_cookie_jar_persists_and_forgets(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            jar=Path(tmp)/'mpil.cookies.txt'
            http=s.HTTP(tmp,offline=False,cookie_jar=jar)
            self.assertFalse(http.had_session_cookies)
            self.assertFalse(http.forget_session_cookies())
            http.session.cookies.set_cookie(
                s.requests.cookies.create_cookie(name='JSESSIONID',value='abc',domain='opil.ouplaw.com',path='/'))
            http.session.cookies.save(ignore_discard=True)
            self.assertTrue(jar.is_file())
            reloaded=s.HTTP(tmp,offline=False,cookie_jar=jar)
            self.assertTrue(reloaded.had_session_cookies)
            self.assertTrue(reloaded.forget_session_cookies())
            self.assertFalse(jar.exists())
            self.assertFalse(reloaded.forget_session_cookies())

    def test_fetch_uses_the_channel_user_agent_and_content_selector(self):
        page=('<html><head><title>Oxford Public International Law: Command Responsibility</title></head>'
              '<body><div id="utilityNav">'+'navigation link '*40+'</div>'
              '<div id="mainContent"><p>'+'Entry paragraph text. '*12+'</p></div></body></html>')
        seen=[]
        class H:
            def __init__(self,*a,**k): self.evidence=[]
            def get(self,url,params=None,method='GET',data=None,headers=None):
                seen.append(headers)
                return page.encode(),{'url':url,'status':200,'content_type':'text/html','retrieved_at':'test','sha256':'a'*64}
        with tempfile.TemporaryDirectory() as tmp, patch.object(s,'HTTP',H):
            out=s.fetch(SimpleNamespace(cache=tmp,cache_ttl=10,offline=False,
                url='https://opil.ouplaw.com/display/10.1093/law:epil/9780199231690/law-9780199231690-e273'))
        self.assertIn('Mozilla/5.0',seen[0]['User-Agent'])
        self.assertIn('Entry paragraph text',out['text'])
        self.assertNotIn('navigation link',out['text'])
        self.assertEqual(out['content_scope'],s.CHANNELS['mpil']['fetch_scope'])

    def test_mpil_keeps_the_search_state_its_product_facet_needs(self):
        http=MPILHTTP(mpil_page(1))
        s.opil(http,s.CHANNELS['mpil'],'genocide',1,0)
        params=http.calls[0][1]
        self.assertEqual(params['prd'],'MPEIPRO')
        self.assertEqual(params['access'],'all')
        self.assertEqual(params['level'],'all')

    def test_oril_icl_uses_the_uuid_facet_and_no_access_state(self):
        http=MPILHTTP(oril_page(1))
        s.opil(http,s.CHANNELS['oril-icl'],'command responsibility',1,0)
        url,params,headers=http.calls[0]
        self.assertEqual(url,'https://opil.ouplaw.com/search')
        self.assertEqual(params['pc_32'],'68306099-6983-4cb7-a931-60f851434432')
        self.assertEqual(params['sfam'],'')
        self.assertNotIn('access',params)
        self.assertNotIn('level',params)
        self.assertIn('Mozilla/5.0',headers['User-Agent'])

    def test_oril_icl_rows_carry_citation_core_issue_and_locked_access(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(s,'HTTP',lambda *a,**k: MPILHTTP(oril_page(2))):
            report=s.run_channel('oril-icl',mpil_args(tmp))
        self.assertEqual(report['status'],'ok')
        self.assertEqual(report['pagination']['oril-icl']['total'],365)
        row=report['results'][0]
        self.assertEqual(row['via'],'oril-icl-search')
        self.assertEqual(row['date'],'04 April 1997')
        self.assertEqual(row['module'],'International Criminal Law [ICL]')
        self.assertEqual(row['core_issues'],'Whether command responsibility applied in internal armed conflict.')
        self.assertIn('headnote',row['access'])
        self.assertEqual(report['products_observed'],['Oxford Reports on International Law [ORIL]'])

    def test_opil_rejects_a_page_whose_products_do_not_match(self):
        wrong=oril_page(2).replace('Oxford Reports on International Law [ORIL]',
                                   'Oxford Scholarly Authorities on International Law [OSAIL]')
        with self.assertRaisesRegex(s.AccessError,'Product filter not applied'):
            s.opil(MPILHTTP(wrong),s.CHANNELS['oril-icl'],'genocide',1,0)

    def test_oril_icl_is_not_gated_behind_the_browser_preference(self):
        self.assertNotIn('requires_browser',s.CHANNELS['oril-icl'])
        self.assertTrue(s.CHANNELS['oril-icl']['session_cookies'])

    def test_icd_reads_the_public_result_list(self):
        filler=[icd_entry(900+i,'Case %d' % i,'The Prosecutor v. Defendant %d' % i,'Judgement',
            '%d January 200%d' % (i,i),'Some Court, Somewhere','Summary text %d.' % i) for i in range(1,4)]
        http=ICDHTTP({'genocide':icd_page([AKAYESU_ENTRY,NAHIMANA_ENTRY]+filler,224,45)})
        rows,info=s.icd(http,'genocide',5,0)
        self.assertEqual(info['total'],224)
        self.assertEqual(info['pages'],45)
        self.assertEqual(info['page_size'],5)
        self.assertEqual(info['next_offset'],5)
        self.assertEqual(len(rows),5)
        row=rows[0]
        self.assertEqual(row['via'],'icd-search')
        self.assertEqual(row['case_name'],'Akayesu')
        self.assertEqual(row['subtitle'],'The Prosecutor v. Jean-Paul Akayesu')
        self.assertEqual(row['date'],'2 September 1998')
        self.assertIn('Judgement / Sentence',row['citation'])
        self.assertIn('genocide',row['snippet'])
        self.assertEqual(row['url'],'https://www.internationalcrimesdatabase.org/Case/51')
        self.assertEqual(http.calls,[('genocide',1)])

    def test_icd_advances_to_the_requested_server_page(self):
        pages={1:icd_page([AKAYESU_ENTRY],12,3,1),2:icd_page([NAHIMANA_ENTRY],12,3,2)}
        http=ICDHTTP({'genocide':pages})
        rows,info=s.icd(http,'genocide',5,5)
        self.assertEqual([r['case_name'] for r in rows],['Nahimana et al.'])
        self.assertEqual(info['page'],2)
        self.assertEqual(http.calls,[('genocide',2)])

    def test_icd_no_results_is_a_confirmed_zero_not_a_failure(self):
        rows,info=s.icd(ICDHTTP({'zzzxnonexistent785132904':icd_page([],0,0)}),'zzzxnonexistent785132904',5,0)
        self.assertEqual(rows,[])
        self.assertEqual(info['total'],0)
        self.assertIsNone(info['next_offset'])

    def test_icd_missing_results_container_is_a_failure_not_zero_hits(self):
        http=ICDHTTP({'genocide':'<html><body><h1>404 Not Found</h1></body></html>'})
        with self.assertRaisesRegex(s.AccessError,'results container missing'):
            s.icd(http,'genocide',5,0)

    def test_icd_blocked_phrase_uses_a_labelled_token_intersection(self):
        http=ICDHTTP({'command':icd_page([AKAYESU_ENTRY,NAHIMANA_ENTRY],116,24),
                      'responsibility':icd_page([NAHIMANA_ENTRY],253,51)})
        rows,info=s.icd_token_fallback(http,'command responsibility',5,0)
        self.assertEqual([r['case_name'] for r in rows],['Nahimana et al.'])
        self.assertEqual(rows[0]['via'],'icd-token-intersection')
        self.assertEqual(rows[0]['matched_terms'],['command','responsibility'])
        self.assertIn('bounded',rows[0]['access'])
        self.assertEqual(info['candidates_per_term'],{'command':2,'responsibility':1})

    def test_icd_channel_falls_back_when_the_phrase_is_filtered(self):
        hit=s.result('Nahimana et al.','https://www.internationalcrimesdatabase.org/Case/152','icd-token-intersection')
        with (tempfile.TemporaryDirectory() as tmp,
              patch.object(s,'icd',side_effect=s.AccessError('HTTP 403: filtered')),
              patch.object(s,'icd_token_fallback',return_value=([hit],{'total':1}))):
            report=s.run_channel('icd',mpil_args(tmp,query='command responsibility'))
        self.assertEqual(report['status'],'partial')
        self.assertEqual(report['results'][0]['via'],'icd-token-intersection')
        self.assertIn('icd-token-fallback',report['pagination'])
        self.assertTrue(any('front door rejected' in w for w in report['warnings']))

if __name__=='__main__':unittest.main()
