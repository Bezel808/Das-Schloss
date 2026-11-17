import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from scholartrace import server


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        server.DB = str(Path(self.tmp.name) / 'test.sqlite')
        server.KEY = ''
        self.client = TestClient(server.app)
        self.client.__enter__()
        self.works = json.loads((Path(__file__).parents[1] / 'examples/synthetic.json').read_text())

    def tearDown(self):
        for _ in range(100):
            if not server.LOCK.locked():
                break
            time.sleep(.01)
        self.client.__exit__(None, None, None)
        self.tmp.cleanup()

    def test_key_not_exposed_and_origin_protected(self):
        self.assertEqual(self.client.post('/api/settings', json={'api_key':'secret'}).status_code, 200)
        self.assertNotIn('secret', self.client.get('/api/settings').text)
        self.assertEqual(self.client.post('/api/settings', json={'api_key':'bad'}, headers={'Origin':'https://evil.test'}).status_code, 403)
        self.assertEqual(self.client.get('/', headers={'Host':'evil.test'}).status_code, 403)

    def test_requires_key(self):
        self.assertEqual(self.client.post('/api/jobs', json={'author_id':'A1'}).status_code, 400)

    def test_relationship_inference_routes_removed(self):
        self.assertEqual(self.client.get('/api/mining/A1').status_code,404)
        self.assertEqual(self.client.get('/api/mining/A1/plan').status_code,404)
        self.assertEqual(self.client.post('/api/mining/A1',json={'limit':2}).status_code,404)

    def test_cached_annual_statistics_without_key(self):
        with server.db() as conn:
            for aid in ['A1', 'A2', 'A3']:
                conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',
                             (aid, 'complete', '', 3, json.dumps({'display_name': aid}), '', '2026-01-01'))
                for work in self.works:
                    conn.execute('INSERT INTO papers VALUES (?,?,?)', (aid, work['id'], json.dumps(work)))
        panel = self.client.get('/api/insights/A1?start=2020&end=2022&window=2')
        self.assertEqual(panel.status_code, 200)
        self.assertEqual([r['year'] for r in panel.json()['panel']['rows']], [2020,2021,2022])
        self.assertIn('scope', panel.json()['corpus'])
        self.assertEqual(self.client.get('/api/insights/A1?start=2022&end=2020').status_code,422)
        self.assertEqual(self.client.get('/api/insights/A1?fields=not-an-observed-field').status_code,422)

    def test_collection_resume_and_report(self):
        server.KEY = 'test-key'
        calls = []
        def fake(path, params=None, key=None):
            calls.append((path, params))
            if path == 'authors/A1':
                return {'id':'https://openalex.org/A1','display_name':'Test'}
            if params['cursor'] == '*':
                return {'results':self.works[:1], 'meta':{'count':3,'next_cursor':'second'}}
            raise ValueError('temporary failure')
        with patch.object(server, 'upstream', side_effect=fake):
            self.client.post('/api/jobs', json={'author_id':'A1'})
            while server.LOCK.locked(): time.sleep(.01)
        job = self.client.get('/api/jobs').json()[0]
        self.assertEqual((job['status'],job['received']), ('error',1))
        with patch.object(server, 'upstream', return_value={'results':self.works[1:], 'meta':{'count':3,'next_cursor':None}}) as fetch:
            self.client.post('/api/jobs', json={'author_id':'A1'})
            while server.LOCK.locked(): time.sleep(.01)
            self.assertEqual(fetch.call_args.args[1]['cursor'], 'second')
        report = self.client.get('/api/report/A1').json()
        self.assertEqual(report['status'], 'complete')
        self.assertEqual(len(report['papers']), 3)
        self.assertEqual(report['time_axis']['available_years'], [2020,2021,2022])
        window = self.client.get('/api/report/A1?start=2021&end=2021').json()
        self.assertEqual(window['time_axis']['minimum_year'],2020)
        self.assertEqual(window['graph']['window'],{'start_year':2021,'end_year':2021,'inclusive':True})
        self.assertEqual(window['graph']['edges'][0]['weight_raw'],1)
        self.assertEqual(window['graph']['edges'][0]['events'][0]['year'],2021)
        self.assertNotIn('https://openalex.org/A3', [n['id'] for n in window['graph']['nodes']])
        empty = self.client.get('/api/report/A1?start=1900&end=1901').json()
        self.assertEqual(empty['graph']['edges'],[])
        self.assertEqual(empty['time_axis']['maximum_year'],2022)
        self.assertEqual(len(self.client.get('/api/report/A1?start=2021&end=2021').json()['timeline']),1)
        self.assertEqual(self.client.get('/api/report/A1?start=2022&end=2021').status_code,422)

    def test_truncated_work_is_refetched(self):
        server.KEY='test'
        truncated=dict(self.works[0], authorships=self.works[0]['authorships'][:1])
        def fake(path, params=None, key=None):
            if path=='authors/A1':return {'display_name':'Test'}
            if path=='works/W1':return self.works[0]
            return {'results':[truncated], 'meta':{'count':1,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=fake) as fetch:
            self.client.post('/api/jobs',json={'author_id':'A1'})
            while server.LOCK.locked():time.sleep(.01)
            self.assertTrue(any(c.args[0]=='works/W1' for c in fetch.call_args_list))
        self.assertEqual(len(self.client.get('/api/report/A1').json()['graph']['edges']),3)

    def test_page_and_search(self):
        self.assertEqual(self.client.get('/').status_code,200)
        with patch.object(server,'upstream',return_value={'results':[]}):
            self.assertEqual(self.client.get('/api/authors?q=Test').json(),{'results':[]})

    def test_selected_field_truncation_flag_refetches_and_normalizes_count(self):
        server.KEY='fixture'
        truncated=dict(self.works[0],authorships=self.works[0]['authorships'][:1],is_authors_truncated=True)
        truncated.pop('authors_count',None)
        full=dict(self.works[0],is_authors_truncated=False);full.pop('authors_count',None)
        def fetch(path,params=None,key=None):
            if path.startswith('authors/'):return {'display_name':'Test'}
            if path=='works/W1':return full
            return {'results':[truncated],'meta':{'count':1,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=fetch):
            self.client.post('/api/jobs',json={'author_id':'A1'})
            while server.LOCK.locked():time.sleep(.01)
        result=self.client.get('/api/report/A1').json()
        self.assertEqual(result['papers'][0]['authors_count'],len(full['authorships']))
        self.assertEqual(len(result['graph']['edges']),3)

    def test_still_truncated_singleton_cannot_complete_author_history(self):
        server.KEY='fixture'
        truncated=dict(self.works[0],is_authors_truncated=True)
        def fetch(path,params=None,key=None):
            if path.startswith('authors/'):return {'display_name':'Test'}
            if path=='works/W1':return truncated
            return {'results':[truncated],'meta':{'count':1,'next_cursor':None}}
        with patch.object(server,'upstream',side_effect=fetch):
            self.client.post('/api/jobs',json={'author_id':'A1'})
            while server.LOCK.locked():time.sleep(.01)
        result=self.client.get('/api/jobs/A1').json()
        self.assertEqual(result['status'],'error');self.assertEqual(result['received'],0)
