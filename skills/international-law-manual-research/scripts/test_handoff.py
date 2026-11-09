import unittest
from handoff import build


class HandoffTests(unittest.TestCase):
    def test_successful_blog_does_not_create_manual_task(self):
        report={'query':'immunity','channels':[{'source':'opinio_juris','status':'ok','results':[{'text':'body'}]}]}
        self.assertEqual(build(report)['manual_tasks'],[])

    def test_timeout_has_automatic_first_action(self):
        report={'query':'immunity','channels':[{'source':'ejil_talk','status':'unavailable','warnings':['ReadTimeout'],'results':[]}]}
        out=build(report)
        self.assertEqual(out['manual_tasks'][0]['priority'],'after_automatic_retry')
        self.assertTrue(out['automatic_followups'])

    def test_icl_mirror_keeps_ucr_gap(self):
        report={'query':'Lubanga','channels':[{'channel':'ucr','status':'fallback','results':[{'url':'https://www.legal-tools.org/doc/x/'}]}]}
        out=build(report)
        self.assertEqual(out['manual_tasks'][0]['source'],'icl:ucr')
        self.assertFalse(out['manual_tasks'][0]['required'])

    def test_existing_journal_text_not_requested_again(self):
        report={'channels':[{'source':'ejil','status':'ok','results':[{'full_text':'Actual article body'}]}]}
        self.assertEqual(build(report)['manual_tasks'],[])

    def test_landing_page_is_not_article_fulltext(self):
        report={'channels':[{'source':'ejil','status':'ok','results':[{'document':{'result_type':'retrieved_text','text':'Publisher landing page'}}]}]}
        self.assertEqual(len(build(report)['manual_tasks']),1)

    def test_unknown_report_is_rejected(self):
        with self.assertRaises(ValueError): build({'channels':[{'name':'unknown'}]})


if __name__=='__main__': unittest.main()
