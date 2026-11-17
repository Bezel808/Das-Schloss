import json,tempfile,time,threading,unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from scholartrace import server
from scholartrace import computations

class ComputationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.old=server.DB;server.DB=str(Path(self.temp.name)/'db.sqlite')
  self.client=TestClient(server.app);self.client.__enter__()
  with server.db() as c:c.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?)',('A1','complete',None,0,'{}',None,'2026-01-01'))
 def tearDown(self):
  with computations.SUBMIT_LOCK:
   pending=[t['id'] for t in computations.TASKS.values() if t['path']==server.DB and t['status'] in {'queued','running'}]
  for tid in pending:self.finish(tid)
  self.client.__exit__(None,None,None);server.DB=self.old;self.temp.cleanup()
 def finish(self,tid):
  for _ in range(300):
   r=self.client.get('/api/computations/'+tid).json()
   if r['status'] not in ['queued','running']:return r
   time.sleep(.01)
  self.fail('task did not finish')
 def test_single_flight_memory_only_and_invalidation(self):
  entered=threading.Event();release=threading.Event()
  def calculate(*a,**k):entered.set();release.wait(2);return {'panel':{'rows':[]},'corpus':{}}
  with patch.object(server,'insights',side_effect=calculate) as run:
   first=self.client.post('/api/compute/insights/A1',json={}).json();self.assertTrue(entered.wait(1))
   second=self.client.post('/api/compute/insights/A1',json={}).json()
   self.assertEqual(first['id'],second['id']);release.set()
   self.assertEqual(self.finish(first['id'])['status'],'complete')
   with server.db() as c:
    self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='computations'").fetchone())
   cached=self.client.post('/api/compute/insights/A1',json={}).json()
   self.assertTrue(cached['cache_hit']);self.assertEqual(run.call_count,1)
   with server.db() as c:c.execute("UPDATE jobs SET updated='2026-02-01' WHERE id='A1'")
   new=self.client.post('/api/compute/insights/A1',json={}).json();self.assertNotEqual(new['id'],first['id'])
   self.finish(new['id']);self.assertEqual(run.call_count,2)
 def test_snapshot_change_during_compute_cannot_publish_stale_result(self):
  entered=threading.Event();release=threading.Event()
  def calculate(*a,**k):entered.set();release.wait(2);return {}
  with patch.object(server,'insights',side_effect=calculate):
   task=self.client.post('/api/compute/insights/A1',json={}).json();entered.wait(1)
   with server.db() as c:c.execute("UPDATE jobs SET updated='2026-02-01' WHERE id='A1'")
   release.set();r=self.finish(task['id']);self.assertEqual(r['status'],'stale');self.assertNotIn('result',r)
 def test_failure_retries_and_validation(self):
  with patch.object(server,'insights',side_effect=RuntimeError('private internal detail')):
   task=self.client.post('/api/compute/insights/A1',json={}).json();r=self.finish(task['id'])
   self.assertEqual(r['status'],'error');self.assertNotIn('private',str(r))
  with patch.object(server,'insights',return_value={}):
   task=self.client.post('/api/compute/insights/A1',json={}).json();self.assertEqual(self.finish(task['id'])['status'],'complete')
  self.assertEqual(self.client.post('/api/compute/groups/A1',json={'start':2025,'end':2020}).status_code,422)
  self.assertEqual(self.client.post('/api/compute/groups/A2',json={}).status_code,409)
  with patch.object(server,'KEY',''):
   self.assertEqual(self.client.post('/api/jobs',json={'author_id':'A1'}).json()['reused'],True)
 def test_uncached_author_collect_then_compute(self):
  works=json.loads((Path(__file__).parents[1]/'examples/synthetic.json').read_text())
  def fetch(path,params=None,key=None):
   if path.startswith('authors/'):return {'id':'https://openalex.org/A2','display_name':'New scholar'}
   return {'results':works,'meta':{'count':len(works),'next_cursor':None}}
  with patch.object(server,'KEY','fixture-key'),patch.object(server,'upstream',side_effect=fetch):
   self.assertEqual(self.client.post('/api/jobs',json={'author_id':'A2'}).status_code,200)
   for _ in range(300):
    if not server.LOCK.locked():break
    time.sleep(.01)
  self.assertEqual(self.client.get('/api/jobs/A2').json()['status'],'complete')
  task=self.client.post('/api/compute/groups/A2',json={'start':2020,'end':2022}).json()
  result=self.finish(task['id'])
  self.assertEqual(result['status'],'complete')
  self.assertEqual(result['result']['focal'],'https://openalex.org/A2')
 def test_busy_collection_queues_another_author_and_reuses_same_request(self):
  works=json.loads((Path(__file__).parents[1]/'examples/synthetic.json').read_text())
  entered=threading.Event();release=threading.Event()
  def fetch(path,params=None,key=None):
   if path.startswith('authors/'):return {'display_name':path}
   if params['filter'].endswith('A2'):entered.set();release.wait(3)
   return {'results':works,'meta':{'count':len(works),'next_cursor':None}}
  with patch.object(server,'KEY','fixture-key'),patch.object(server,'upstream',side_effect=fetch):
   self.client.post('/api/jobs',json={'author_id':'A2'});self.assertTrue(entered.wait(1))
   response=self.client.post('/api/jobs',json={'author_id':'A3'});self.assertTrue(response.json()['queued'])
   self.assertTrue(self.client.post('/api/jobs',json={'author_id':'A3'}).json()['reused'])
   release.set()
   for _ in range(400):
    if not server.LOCK.locked() and not server.SCHEDULER_LOCK.locked():break
    time.sleep(.01)
   self.assertEqual(self.client.get('/api/jobs/A3').json()['status'],'complete')

 def test_expiry_capacity_and_no_restart_persistence(self):
  with patch.object(server,'insights',return_value={'large':'abc'*1000}):
   first=self.client.post('/api/compute/insights/A1',json={}).json();self.finish(first['id'])
   with computations.SUBMIT_LOCK:
    computations.TASKS[first['id']]['touched']-=computations.TTL_SECONDS+1
   self.assertEqual(self.client.get('/api/computations/'+first['id']).status_code,404)
   with patch.object(computations,'MAX_TASKS',2):
    for year in [2020,2021,2022]:
     task=self.client.post('/api/compute/insights/A1',json={'end':year}).json();self.finish(task['id'])
    self.assertLessEqual(len(computations.TASKS),2)
   with computations.SUBMIT_LOCK:computations.TASKS.clear() # process memory is lost on restart
   self.assertEqual(self.client.get('/api/computations/'+task['id']).status_code,404)

 def test_pending_limit_and_result_byte_budget(self):
  entered=threading.Event();release=threading.Event()
  def calculate(*a,**k):entered.set();release.wait(2);return {'value':'test'}
  with patch.object(server,'insights',side_effect=calculate),patch.object(computations,'MAX_PENDING',1):
   task=self.client.post('/api/compute/insights/A1',json={}).json();entered.wait(1)
   self.assertEqual(self.client.post('/api/compute/insights/A1',json={'end':2024}).status_code,429)
   release.set();self.finish(task['id'])
  with patch.object(server,'insights',return_value={'value':'test'}),patch.object(computations,'MAX_RESULT_BYTES',1):
   task=self.client.post('/api/compute/insights/A1',json={'end':2023}).json()
   self.assertEqual(self.finish(task['id'])['status'],'error')
