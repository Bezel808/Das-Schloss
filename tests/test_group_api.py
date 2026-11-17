import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from scholartrace import server
from scholartrace.group_api import state


def paper(wid, year, authors):
    return {'id':'https://openalex.org/W'+str(wid),'publication_year':year,'title':'Paper '+str(wid),
            'authorships':[{'author':{'id':'https://openalex.org/'+a,'display_name':a},
                            'institutions':[{'id':'https://openalex.org/I1'}]} for a in authors]}


class GroupApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.old_db=server.DB;self.old_key=server.KEY
        server.DB=str(Path(self.tmp.name)/'test.sqlite');server.KEY=''
        self.client=TestClient(server.app);self.client.__enter__()
        self.initial=[paper(1,2014,['A1','A2']),paper(2,2015,['A1','A2']),
                      paper(3,2018,['A1','A2','A3']),paper(4,2028,['A1','A99'])]
        with server.db() as conn:
            conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',('A1','complete',None,4,'{}',None,'2026-11-15'))
            for w in self.initial:conn.execute('INSERT INTO papers VALUES (?,?,?)',('A1',w['id'],json.dumps(w)))
        self.params={'start':2016,'end':2020,'scope':'shared_institution'}

    def tearDown(self):
        for _ in range(400):
            if not server.LOCK.locked():break
            time.sleep(.01)
        self.assertFalse(server.LOCK.locked())
        self.client.__exit__(None,None,None);server.DB=self.old_db;server.KEY=self.old_key;self.tmp.cleanup()

    def wait(self):
        for _ in range(400):
            if not server.LOCK.locked():return
            time.sleep(.01)
        self.fail('Collection did not finish')

    def plan(self,limit=1):
        response=self.client.get('/api/groups/A1/plan',params={**self.params,'limit':limit})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def submit(self,p):
        return self.client.post('/api/groups/A1/collect',json={**p['parameters'],'limit':p['limit'],'plan_sha256':p['plan_sha256']})

    def test_snapshot_cutoff_unknowns_and_validation(self):
        result=self.client.get('/api/groups/A1',params=self.params).json()
        self.assertEqual(result['summary']['unknown'],1)
        self.assertEqual(result['coverage']['source_histories']['https://openalex.org/A1']['through'],2025)
        self.assertEqual(result['summary']['assessment_counts'],{'unknown_career_history':1})
        p=self.plan()
        self.assertEqual(p['authors'][0]['id'],'https://openalex.org/A3')
        self.assertEqual(p['missing_histories'],2)
        self.assertNotIn('A99',json.dumps(p))
        self.assertEqual(self.client.get('/api/groups/A999').status_code,409)
        self.assertEqual(self.client.get('/api/groups/A1?start=2025&end=2020').status_code,422)
        self.assertEqual(self.client.get('/api/groups/A1?window=0').status_code,422)
        self.assertEqual(self.client.get('/api/groups/A1/plan?limit=100').status_code,422)
        self.assertEqual(self.submit(p).status_code,400)

    def test_completed_collection_uses_non_focal_history_and_stores_no_key(self):
        server.KEY='test-secret-key';p=self.plan()
        def fetch(path,params=None,key=None):
            if path=='authors/A3':return {'display_name':'Novice'}
            return {'results':[self.initial[2],paper(5,2019,['A2','A3']),paper(6,2020,['A2','A3'])],
                    'meta':{'count':3,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=fetch):
            self.assertEqual(self.submit(p).status_code,200);self.wait()
        value=self.client.get('/api/groups/A1',params=self.params).json()
        self.assertEqual(value['summary']['assessed'],1)
        self.assertAlmostEqual(value['summary']['focal_mean_share'],1/3)
        self.assertEqual(value['summary']['persistent_peer_rate'],1)
        self.assertEqual(state('A1')['status'],'complete')
        self.assertEqual(self.submit(p).status_code,409) # reviewed candidate list changed
        with server.db() as conn:
            dump='\n'.join(conn.iterdump())
        self.assertNotIn(server.KEY,dump)
        self.assertNotIn(server.KEY,self.client.get('/api/groups/A1/collection').text)

    def test_page_failure_resumes_cursor_and_stops_batch(self):
        server.KEY='test';p=self.plan(limit=2)
        def fail(path,params=None,key=None):
            if path.startswith('authors/'):return {'display_name':path}
            if params['cursor']=='*':return {'results':[self.initial[2]],'meta':{'count':2,'next_cursor':'second'}}
            raise ValueError('temporary upstream error')
        with patch.object(server,'upstream',side_effect=fail):
            self.assertEqual(self.submit(p).status_code,200);self.wait()
        self.assertEqual(state('A1')['status'],'error')
        with server.db() as conn:
            self.assertEqual(conn.execute('SELECT cursor FROM jobs WHERE id=?',('A3',)).fetchone()[0],'second')
            self.assertIsNone(conn.execute('SELECT status FROM jobs WHERE id=?',('A2',)).fetchone())
        p=self.plan(limit=1)
        with patch.object(server,'upstream',return_value={'results':[paper(5,2019,['A3'])],'meta':{'count':2,'next_cursor':None}}) as fetch:
            self.assertEqual(self.submit(p).status_code,200);self.wait()
            self.assertEqual(fetch.call_args.args[1]['cursor'],'second')
        self.assertEqual(state('A1')['status'],'complete')

    def test_pause_saves_page_and_does_not_start_next_member(self):
        server.KEY='test';p=self.plan(limit=2);entered=threading.Event();release=threading.Event()
        def fetch(path,params=None,key=None):
            if path.startswith('authors/'):return {'display_name':path}
            entered.set();release.wait(3)
            return {'results':[self.initial[2]],'meta':{'count':2,'next_cursor':'second'}}
        with patch.object(server,'upstream',side_effect=fetch):
            self.assertEqual(self.submit(p).status_code,200)
            self.assertTrue(entered.wait(2))
            self.assertEqual(self.client.post('/api/groups/A1/pause',json={}).status_code,200)
            release.set();self.wait()
        self.assertEqual(state('A1')['status'],'paused')
        with server.db() as conn:
            self.assertEqual(conn.execute('SELECT cursor FROM jobs WHERE id=?',('A3',)).fetchone()[0],'second')
            self.assertIsNone(conn.execute('SELECT status FROM jobs WHERE id=?',('A2',)).fetchone())

    def test_restart_and_mutual_exclusion(self):
        with server.db() as conn:
            conn.execute('INSERT INTO group_collections VALUES (?,?)',('A1',json.dumps({'status':'running','completed':1})))
        server.initialize()
        self.assertEqual(state('A1')['status'],'interrupted')
        p=self.plan();server.LOCK.acquire()
        try:self.assertEqual(self.submit(p).status_code,409)
        finally:server.LOCK.release()

    def test_auto_collects_entire_queue_and_recomputes_without_repeated_clicks(self):
        server.KEY='test'
        def fetch(path,params=None,key=None):
            if path.startswith('authors/'):return {'display_name':path}
            target=params['filter'].split(':')[-1]
            return {'results':[w for w in self.initial if 'https://openalex.org/'+target in [a['author']['id'] for a in w['authorships']]],'meta':{'count':3,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=fetch):
            self.assertEqual(self.client.post('/api/groups/A1/auto',json=self.params).status_code,200)
            self.wait()
        s=state('A1')
        self.assertEqual((s['status'],s['completed'],s['total']),('complete',2,2))
        self.assertIsNotNone(s['result_summary'])
        server.KEY=''
        with patch.object(server,'upstream',side_effect=AssertionError('must reuse cache')):
            self.assertEqual(self.client.post('/api/groups/A1/auto',json=self.params).status_code,200)
            self.wait()
        self.assertEqual(state('A1')['total'],0)

    def test_auto_requires_key_and_preserves_parameters(self):
        self.assertEqual(self.client.post('/api/groups/A1/auto',json=self.params).status_code,400)
        self.assertFalse(server.LOCK.locked())
        self.assertEqual(self.client.post('/api/groups/A1/auto',json={'start':2025,'end':2020}).status_code,422)

    def test_unrelated_searches_cannot_change_results_or_paper_scan(self):
        from scholartrace.group_api import snapshot, Parameters
        first=self.client.get('/api/groups/A1',params=self.params).json()
        annual=self.client.get('/api/insights/A1?start=2016&end=2020').json()
        with server.db() as conn:
            conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',('A999','complete',None,1,'{}',None,'2026-11-15'))
            # Intentionally invalid JSON: must never be read for this focal author.
            conn.execute('INSERT INTO papers VALUES (?,?,?)',('A999','irrelevant','not-json'))
        second=self.client.get('/api/groups/A1',params=self.params).json()
        self.assertEqual(first,second)
        self.assertEqual(annual,self.client.get('/api/insights/A1?start=2016&end=2020').json())
        corpora,_,_,_=snapshot('A1',Parameters(**self.params))
        self.assertEqual(list(corpora),['https://openalex.org/A1'])
