import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class EphemeralStorageTests(unittest.TestCase):
    def test_default_web_query_has_no_disk_state_expires_and_cannot_erase_active_tasks(self):
        root = Path(__file__).resolve().parents[1]
        code = r'''
import json, time, threading
from unittest.mock import patch
from fastapi.testclient import TestClient
from scholartrace import server, storage, computations
assert server.DB == storage.MEMORY_DB
works = [{'id':'https://openalex.org/W1','publication_year':2020,'authorships':[{'author':{'id':'https://openalex.org/A1'}}]}]
def upstream(path, params=None, key=None):
    if path.startswith('authors/'):return {'id':'https://openalex.org/A1','display_name':'Test'}
    return {'results':works,'meta':{'count':1,'next_cursor':None}}
with TestClient(server.app) as client, patch.object(server,'KEY','fixture-key'), patch.object(server,'upstream',side_effect=upstream):
    assert client.get('/api/settings').json()['storage'] == 'temporary_memory'
    assert client.post('/api/jobs',json={'author_id':'A1'}).status_code == 200
    for _ in range(200):
        if not server.LOCK.locked():break
        time.sleep(.01)
    assert client.get('/api/jobs/A1').json()['status'] == 'complete'
    with server.db() as conn:
        assert not conn.execute('PRAGMA database_list').fetchone()[2]
        assert conn.execute('PRAGMA max_page_count').fetchone()[0] * conn.execute('PRAGMA page_size').fetchone()[0] == storage.MAX_SOURCE_BYTES
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='computations'").fetchone() is None
    # Protect source data while a calculation holds a snapshot.
    entered=threading.Event();release=threading.Event()
    def calculate(*args,**kwargs):entered.set();release.wait(2);return {}
    with patch.object(server,'insights',side_effect=calculate):
        task=client.post('/api/compute/insights/A1',json={}).json();assert entered.wait(1)
        assert client.post('/api/session/reset',json={}).status_code == 409
        release.set()
        for _ in range(200):
            status=client.get('/api/computations/'+task['id']).json()['status']
            if status not in ['queued','running']:break
            time.sleep(.01)
        assert status == 'complete'
    assert storage.expire_idle(time.monotonic()+storage.IDLE_SECONDS+1)
    assert client.get('/api/jobs').json() == []
    assert client.get('/api/computations/'+task['id']).status_code == 404
    # Hard cap is enforced by SQLite, including a single oversized insert.
    import sqlite3
    with server.db() as conn:
        pages=conn.execute('PRAGMA page_count').fetchone()[0]
        conn.execute('PRAGMA max_page_count='+str(pages+2))
    failed=False
    try:
        with server.db() as conn:conn.execute('INSERT INTO author_metadata VALUES (?,?)',('huge','x'*200000))
    except sqlite3.OperationalError as e:failed='full' in str(e).lower()
    assert failed
    assert client.post('/api/session/reset',json={}).status_code == 200
'''
        env = dict(os.environ, PYTHONPATH=str(root), PYTHONDONTWRITEBYTECODE='1')
        env.pop('SCHOLARTRACE_DB', None); env.pop('OPENALEX_API_KEY', None)
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([str(root/'.venv/bin/python'), '-c', code], cwd=tmp, env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])
