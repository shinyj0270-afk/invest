import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from investment.research_library import Library
from investment.research_library_view import view, recent_stories
from tests.test_research_library import source, thesis, card


class ViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root/'config').mkdir()
        (self.root/'config'/'local.json').write_text(json.dumps(dict(profile='work',project_root='.',data_dir='data',enabled_data_adapters=[],scheduled_jobs_enabled=False)),encoding='utf-8')

    def tearDown(self):self.temp.cleanup()

    def test_empty_does_not_create_any_db(self):
        result=view(self.root)
        self.assertEqual(result['status'],'empty')
        self.assertEqual(len(result['masters']),8)
        self.assertFalse((self.root/'.local').exists())
        self.assertEqual(result['stories'], [])

    def test_stories_rank_research_updates_and_keep_source_dates_distinct(self):
        def record(key, date):
            return dict(id=key, kind='thesis', recorded_at=date, revision=1,
                        value=dict(title=key, claim='Conditional claim, not a proven result',
                                   conditions=['First condition', 'Second condition'],
                                   invalidation=['Countercondition'], status='invalidated', as_of='2026-01-01'),
                        provenance=[dict(id='s', value=dict(title='Old source', url='https://example.invalid/source',
                                                          published_on='2000-01-01'))])
        rows=[record(str(i), f'2026-01-0{i+1}T00:00:00+00:00') for i in range(5)]
        rows[0]['catalog_history']=[dict(recorded_at='2026-02-01T00:00:00+00:00')]
        stories=recent_stories(dict(theses=rows))
        self.assertEqual([r['id'] for r in stories], ['0','4','3'])
        self.assertEqual(stories[0]['sources'][0]['published_on'], '2000-01-01')
        self.assertEqual(stories[0]['as_of'], '2026-01-01')
        self.assertEqual(len(stories[0]['lines']),5)
        self.assertIn('반증됨',stories[0]['lines'][-1]['text'])
        self.assertIn('Countercondition',[l['text'] for l in stories[0]['lines']])

    def test_bibliography_or_sparse_records_do_not_invent_three_stories(self):
        self.assertEqual(recent_stories(dict(sources=[dict(value=dict(title='Book title only'))])), [])
        self.assertEqual(recent_stories(dict(theses=[dict(id='t',value=dict(claim='Sparse claim'),provenance=[])])), [])

    def approved_session_note(self):
        from datetime import datetime,timezone,timedelta
        from investment.research_sessions import SessionRunner
        from investment.research_agents import approve
        today=datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        lib=Library(self.root/'.local/research-library','work')
        lib.source('s1',source())
        value=dict(question='Synthetic question',as_of=today,observations=[dict(source_id='s1',observation='Synthetic observation')],
                   external_model_allowed=True,independent_analysis=True,no_personal_data=True)
        runner=SessionRunner(lib,self.root/'session-runs')
        job=runner.create(value)
        draft=dict(title='Synthetic reviewed note',hypothesis='Conditional hypothesis',conditions=['Condition'],
                   invalidation=['Countercondition'],missing_evidence=['Comparison missing'],
                   claims=[dict(statement='Synthetic observation',stance='context',source_ids=['s1'])])
        job=runner.accept(job,'research',dict(agent='Claude',model='unknown',value=draft))
        self.assertEqual([],view(self.root)['notes'])
        job=runner.accept(job,'review',dict(agent='Codex',model='unknown',value=dict(verdict='pass',issues=[],summary='Synthetic model review')))
        self.assertEqual([],view(self.root)['notes'])
        approve(lib,job,dict(review_digest=job['review_digest'],reviewer='Synthetic human',reviewed_on=today,
                            human_reviewed=True,independent_analysis=True,no_personal_data=True))
        return lib,job

    def test_approved_note_readonly_projection_and_source_revocation(self):
        from investment.research_catalog import annotate
        from tests.test_research_catalog import metadata
        lib,job=self.approved_session_note()
        before=hashlib.sha256(lib.path.read_bytes()).hexdigest()
        result=view(self.root)
        self.assertEqual(1,len(result['notes']))
        self.assertEqual('Synthetic human',result['notes'][0]['value']['approval']['reviewer'])
        self.assertEqual('s1',result['notes'][0]['provenance'][0]['id'])
        self.assertEqual(before,hashlib.sha256(lib.path.read_bytes()).hexdigest())
        annotate(lib,'source','s1',metadata('excluded'))
        self.assertEqual([],view(self.root)['notes'])
        self.assertEqual([],view(self.root)['stories'])

    def test_changed_or_unreviewed_note_cannot_be_projected(self):
        lib,job=self.approved_session_note()
        value=lib.get('agent_note',job['id'])
        value['draft']['title']='Changed after approval'
        lib._put('agent_note',job['id'],value,1)
        self.assertEqual([],view(self.root)['notes'])

    def test_readonly_and_home_database_not_imported(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        before=hashlib.sha256(lib.path.read_bytes()).hexdigest()
        result=view(self.root)
        self.assertEqual(len(result['theses']),1)
        self.assertEqual(hashlib.sha256(lib.path.read_bytes()).hexdigest(),before)
        self.assertFalse((self.root/'.local'/'research-library'/'home').exists())

    def test_work_blocks_imported_telegram(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib._put('source','restricted',dict(origin='telegram'))
        with self.assertRaises(ValueError):view(self.root)

    def test_revision_provenance_and_catalog_history(self):
        from investment.research_catalog import annotate
        from tests.test_research_catalog import metadata
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        lib.thesis('t1',dict(thesis(),claim='Revised claim',change_reason='New evidence'),1)
        annotate(lib,'thesis','t1',metadata())
        annotate(lib,'thesis','t1',dict(metadata(),reason='Classification corrected'),1)
        row=view(self.root)['theses'][0]
        self.assertEqual(len(row['history']),2)
        self.assertEqual(len(row['catalog_history']),2)
        self.assertEqual(row['provenance'][0]['id'],'s1')
        self.assertEqual(row['metadata']['reason'],'Classification corrected')

    def test_historical_deleted_provenance_cannot_leak_via_revision(self):
        from investment.research_catalog import annotate
        from tests.test_research_catalog import metadata
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        lib.thesis('t1',dict(thesis(),master_ids=[],claim='New independent claim'),1)
        annotate(lib,'source','s1',metadata('deleted'))
        result=view(self.root)
        self.assertEqual(result['sources'],[])
        self.assertEqual(result['cards'],[])
        self.assertEqual(result['theses'],[])

    def test_home_revoked_channel_hides_historical_derivations(self):
        from investment.telegram_research import channels
        from tests.test_research_library import registry
        config=self.root/'config'/'local.json'
        value=json.loads(config.read_text());value['profile']='home';config.write_text(json.dumps(value))
        lib=Library(self.root/'.local'/'research-library','home')
        channels(lib,registry());lib.source('s1',source(origin='telegram'))
        lib.master('m1',card());lib.thesis('t1',thesis())
        revoked=registry();revoked['core'][0]['enabled']=False
        channels(lib,revoked,1)
        result=view(self.root)
        self.assertEqual(result['sources']+result['cards']+result['theses'],[])

    def test_refutation_is_visible_with_source_and_target_revision(self):
        from tests.test_research_library import evidence
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        lib.source('s2',dict(source(),title='Refutation source',url='https://example.invalid/refute'))
        lib.evidence('e1',dict(evidence('refute'),source_ids=['s2']))
        lib.thesis('t1',dict(thesis(),status='invalidated',as_of='2026-01-04',change_reason='Refuted'),1)
        row=view(self.root)['theses'][0]
        self.assertEqual(row['value']['status'],'invalidated')
        self.assertEqual(row['evidence'][0]['value']['stance'],'refute')
        self.assertEqual(row['evidence'][0]['value']['thesis_revision'],1)
        self.assertEqual({r['id'] for r in row['provenance']},{'s1','s2'})

    def test_evidence_or_its_source_exclusion_hides_dependent_thesis(self):
        from tests.test_research_library import evidence
        from investment.research_catalog import annotate
        from tests.test_research_catalog import metadata
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        lib.source('s2',dict(source(),url='https://example.invalid/evidence'))
        lib.evidence('e1',dict(evidence(),source_ids=['s2']))
        annotate(lib,'evidence','e1',metadata('excluded'))
        self.assertEqual(view(self.root)['theses'],[])
        annotate(lib,'evidence','e1',metadata(),1)
        self.assertEqual(len(view(self.root)['theses']),1)
        annotate(lib,'source','s2',metadata('deleted'))
        result=view(self.root)
        self.assertEqual(result['theses'],[])
        self.assertEqual(len(result['cards']),1)  # Independent seed provenance remains visible.

    def test_historical_master_sources_remain_in_provenance(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card());lib.thesis('t1',thesis())
        lib.source('s2',dict(source(),url='https://example.invalid/new-source'))
        # Imported historical DB: normal writer keeps cards immutable.
        lib._put('master','m1',dict(card(),source_ids=['s2']),1)
        self.assertEqual({r['id'] for r in view(self.root)['theses'][0]['provenance']},{'s1','s2'})

    def test_seed_id_format_and_historical_source_display(self):
        lib=Library(self.root/'.local'/'research-library','work')
        lib.source('s1',source());lib.master('m1',card())
        initial=thesis();initial['seed_source_ids']=[{}]
        with self.assertRaises(ValueError):lib.thesis('t1',initial)
        initial['seed_source_ids']=['s1'];initial['master_ids']=[]
        lib.thesis('t1',initial)
        revised=dict(initial,seed_source_ids=[])
        lib.thesis('t1',revised,1)
        self.assertIn('s1:',lib.draft('t1'))
        self.assertIn('이전 revision 출처',lib.draft('t1'))

    def test_readonly_server_never_initializes_services(self):
        from investment.live_dashboard import serve
        with patch('investment.live_dashboard.ThreadingHTTPServer') as server, patch('investment.live_dashboard.load_service') as sync, patch('investment.live_dashboard.DailyMarketRefresh') as refresh:
            serve(self.root,port=8768,read_only=True)
            sync.assert_not_called();refresh.assert_not_called()
            server.return_value.__enter__.return_value.serve_forever.assert_called_once()

    def test_authenticated_route_and_readonly_mutation_rejection(self):
        import threading
        from http.server import HTTPServer
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        from investment.live_dashboard import handler_for
        with HTTPServer(('127.0.0.1',0),handler_for(self.root,token='fixture',read_only=True)) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                with self.assertRaises(HTTPError) as error:urlopen(base+'/research-library')
                self.assertEqual(error.exception.code,403)
                with urlopen(Request(base+'/research-library',headers={'X-Dashboard-Token':'fixture'})) as response:
                    self.assertEqual(json.load(response)['status'],'empty')
                with self.assertRaises(HTTPError) as error:urlopen(Request(base+'/refresh',data=b'',headers={'X-Dashboard-Token':'fixture','Origin':base}))
                self.assertEqual(error.exception.code,403)
                self.assertFalse((self.root/'.local').exists())
            finally:server.shutdown();thread.join()
