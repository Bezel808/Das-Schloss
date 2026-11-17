import json,threading,time,unittest
from unittest.mock import patch
from tests import test_group_api as fixtures
paper=fixtures.paper
from scholartrace import server
from scholartrace.group_api import state
from scholartrace.source_control import RequestGate,retry_delay,WORK_FIELDS

class ParallelCollectionTests(unittest.TestCase):
    setUp=fixtures.GroupApiTests.setUp
    tearDown=fixtures.GroupApiTests.tearDown
    wait=fixtures.GroupApiTests.wait

    def test_parallel_overlap_batched_metadata_and_complete_coverage(self):
        server.KEY='fixture';barrier=threading.Barrier(2);calls=[]
        def upstream(path,params=None,key=None):
            calls.append((path,params))
            if path=='authors':return {'results':[{'id':'https://openalex.org/'+a,'display_name':a} for a in ['A2','A3']]}
            self.assertEqual(path,'works');self.assertEqual(params['select'],WORK_FIELDS)
            barrier.wait(timeout=2) # serialization would deadlock and fail
            aid=params['filter'].split(':')[-1]
            return {'results':[w for w in self.initial if any(x['author']['id'].endswith('/'+aid) for x in w['authorships'])],'meta':{'count':2,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=upstream):
            self.assertEqual(self.client.post('/api/groups/A1/auto',json=self.params).status_code,200);self.wait()
        self.assertEqual((state('A1')['status'],state('A1')['completed']),('complete',2))
        self.assertEqual([p for p,_ in calls].count('authors'),1)
        self.assertFalse(any(p.startswith('authors/') for p,_ in calls))

    def test_pause_limits_concurrency_and_resumes_individual_cursors(self):
        server.KEY='fixture';entered=threading.Event();release=threading.Event();lock=threading.Lock();started=[]
        own=paper(10,2018,['A1']+['A'+str(i) for i in range(2,12)])
        with server.db() as c:c.execute('INSERT INTO papers VALUES (?,?,?)',('A1',own['id'],json.dumps(own)))
        def upstream(path,params=None,key=None):
            if path=='authors':return {'results':[{'id':'https://openalex.org/'+a,'display_name':a} for a in params['filter'].split(':')[1].split('|')]}
            aid=params['filter'].split(':')[-1]
            with lock:
                started.append(aid)
                if len(started)==8:entered.set()
            release.wait(3)
            return {'results':[own],'meta':{'count':2,'next_cursor':'second'}}
        with patch.object(server,'upstream',side_effect=upstream):
            self.client.post('/api/groups/A1/auto',json=self.params);self.assertTrue(entered.wait(2))
            self.client.post('/api/groups/A1/pause',json={});release.set();self.wait()
        self.assertEqual(len(started),8);self.assertEqual(state('A1')['status'],'paused')
        with server.db() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE status='running'").fetchone()[0],0)
            for aid in started:self.assertEqual(c.execute('SELECT cursor FROM jobs WHERE id=?',(aid,)).fetchone()[0],'second')
        cursors={}
        def resume(path,params=None,key=None):
            if path=='authors':return {'results':[]}
            if path.startswith('authors/'):return {'display_name':path}
            cursors[params['filter'].split(':')[-1]]=params['cursor']
            return {'results':[],'meta':{'count':1,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=resume):
            self.client.post('/api/groups/A1/auto',json=self.params);self.wait()
        self.assertEqual(state('A1')['status'],'complete')
        self.assertTrue(all(cursors[a]=='second' for a in started))
        self.assertEqual(len(cursors),10)

    def test_long_history_starts_before_short_jobs_can_leave_an_idle_tail(self):
        from scholartrace import parallel_collection
        server.KEY='fixture';entered=threading.Event();release=threading.Event();started=[];lock=threading.Lock()
        own=paper(10,2018,['A1','A2','A3','A4','A5'])
        with server.db() as c:c.execute('INSERT INTO papers VALUES (?,?,?)',('A1',own['id'],json.dumps(own)))
        def fetch(path,params=None,key=None):
            if path=='authors':return {'results':[{'id':'https://openalex.org/'+a,'works_count':1000 if a=='A5' else 1} for a in ['A2','A3','A4','A5']]}
            aid=params['filter'].split(':')[-1]
            with lock:
                started.append(aid)
                if len(started)==2:entered.set()
            release.wait(2)
            return {'results':[own],'meta':{'count':1,'next_cursor':None}}
        with patch.object(parallel_collection,'WORKERS',2),patch.object(server,'upstream',side_effect=fetch):
            self.client.post('/api/groups/A1/auto',json=self.params)
            self.assertTrue(entered.wait(1));self.assertIn('A5',started[:2]);release.set();self.wait()
        self.assertEqual(state('A1')['status'],'complete')

    def test_failed_history_is_not_marked_complete_and_all_workers_finish(self):
        server.KEY='fixture';entered=threading.Barrier(2)
        def upstream(path,params=None,key=None):
            if path=='authors':return {'results':[{'id':'https://openalex.org/'+a} for a in ['A2','A3']]}
            entered.wait(2)
            if params['filter'].endswith('A2'):raise ValueError('temporary failure')
            return {'results':[self.initial[2]],'meta':{'count':1,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=upstream):
            self.client.post('/api/groups/A1/auto',json=self.params);self.wait()
        self.assertEqual(state('A1')['status'],'error')
        with server.db() as c:
            self.assertEqual(c.execute("SELECT status FROM jobs WHERE id='A2'").fetchone()[0],'error')
            self.assertEqual(c.execute("SELECT count(*) FROM jobs WHERE status='running'").fetchone()[0],0)

class FullAuthorshipTests(unittest.TestCase):
    setUp=fixtures.GroupApiTests.setUp
    tearDown=fixtures.GroupApiTests.tearDown

    def test_full_authorship_requests_overlap_and_keep_source_order(self):
        from scholartrace.source_control import complete_authorships
        barrier=threading.Barrier(2)
        raw=[dict(paper(i,2018,['A1']),is_authors_truncated=True) for i in [1,2]]
        def fetch(path,params=None,key=None):
            barrier.wait(1)
            return dict(paper(int(path.rsplit('W',1)[-1]),2018,['A1','A2']),is_authors_truncated=False)
        with patch.object(server,'upstream',side_effect=fetch):
            full=complete_authorships(raw,'A1','fixture')
        self.assertEqual([w['id'] for w in full],['https://openalex.org/W1','https://openalex.org/W2'])
        self.assertTrue(all(w['authors_count']==2 for w in full))

    def test_paused_author_dispatches_no_more_full_work_requests(self):
        from scholartrace.source_control import complete_authorships,CollectionPaused
        with server.db() as c:c.execute("UPDATE jobs SET status='paused' WHERE id='A1'")
        with patch.object(server,'upstream',side_effect=AssertionError('must not fetch')):
            with self.assertRaises(CollectionPaused):complete_authorships([dict(paper(1,2018,['A1']),is_authors_truncated=True)],'A1','fixture')

class SourceGateTests(unittest.TestCase):
    def test_pacing_shared_backoff_and_excessive_wait(self):
        now=[0.];sleep=[]
        def advance(dt):sleep.append(dt);now[0]+=dt
        gate=RequestGate(per_second=8,clock=lambda:now[0],sleeper=advance)
        gate.wait();gate.wait();self.assertEqual(sleep,[.125])
        gate.defer(2);gate.wait();self.assertEqual(now[0],2.125)
        gate.defer(3600)
        with self.assertRaises(ValueError):gate.wait()
        self.assertEqual(retry_delay('3',0),3)
        self.assertEqual(retry_delay('Thu, 01 Jan 1970 00:00:10 GMT',0,wall_time=lambda:5),5)
        self.assertEqual(retry_delay('invalid',2),4)
