"""Single-process, bounded ephemeral tasks. No calculation results are written to disk."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import threading
import time
import uuid
import zlib

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from .group_api import Parameters

router = APIRouter()
POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix='scholar-compute')
SUBMIT_LOCK = threading.RLock()
TASKS = {}
TTL_SECONDS = 600
MAX_TASKS = 64
MAX_PENDING = 16
MAX_RESULT_BYTES = 64 * 1024 * 1024


def initialize(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS source_revision (id INTEGER PRIMARY KEY, value INTEGER NOT NULL)')
    conn.execute('INSERT OR IGNORE INTO source_revision VALUES (1,0)')
    for table in ['papers', 'jobs', 'author_metadata']:
        for action in ['INSERT', 'UPDATE', 'DELETE']:
            conn.execute(f'CREATE TRIGGER IF NOT EXISTS revision_{table}_{action} AFTER {action} ON {table} BEGIN UPDATE source_revision SET value=value+1 WHERE id=1; END')
    # Migration: remove only the rejected derived-result cache, never source data.
    conn.execute('DROP TABLE IF EXISTS computations')


def revision(conn):
    return conn.execute('SELECT value FROM source_revision WHERE id=1').fetchone()[0]


def prune(now=None, reserve=0):
    """Called with SUBMIT_LOCK. Active tasks are never evicted."""
    now = time.monotonic() if now is None else now
    for tid, task in list(TASKS.items()):
        if task['status'] not in {'queued', 'running'} and now - task['touched'] >= TTL_SECONDS:
            del TASKS[tid]
    done = sorted((t for t in TASKS.values() if t['status'] not in {'queued', 'running'}), key=lambda t:t['touched'])
    size = sum(len(t.get('blob', b'')) for t in TASKS.values())
    while done and (len(TASKS) + reserve > MAX_TASKS or size > MAX_RESULT_BYTES):
        task = done.pop(0); size -= len(task.get('blob', b'')); del TASKS[task['id']]


def read(path, task_id, cached=False):
    with SUBMIT_LOCK:
        prune()
        task = TASKS.get(task_id)
        if not task or task['path'] != str(path):
            raise HTTPException(404, '计算任务不存在或已过期，请重新计算')
        task['touched'] = time.monotonic()
        out = {k:task[k] for k in ['id', 'status', 'created_at', 'finished_at']}
        blob = task.get('blob'); error = task.get('error')
    out['cache_hit'] = cached
    if blob is not None: out['result'] = json.loads(zlib.decompress(blob))
    if error: out['error'] = error
    return out


def run(path, task_id, kind, aid, params, source_revision):
    from . import server
    from .group_api import calculate
    with SUBMIT_LOCK: TASKS[task_id]['status'] = 'running'
    try:
        result = calculate(aid, Parameters(**params))[0] if kind == 'groups' else server.insights(aid, **params)
        blob = zlib.compress(json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode())
        with server.db() as conn:
            changed = revision(conn) != source_revision
        with SUBMIT_LOCK:
            task = TASKS[task_id]
            if changed:
                task.update(status='stale', error='数据已更新，请重新计算。')
            elif len(blob) > MAX_RESULT_BYTES:
                task.update(status='error', error='结果超过临时内存容量，请缩小观察范围。')
            else: task.update(status='complete', blob=blob)
            task.update(finished_at=datetime.now(timezone.utc).isoformat(), touched=time.monotonic())
            prune()
    except Exception as error:
        message = error.detail if isinstance(error, HTTPException) else '计算未完成，请稍后重试。'
        with SUBMIT_LOCK:
            TASKS[task_id].update(status='error', error=str(message), finished_at=datetime.now(timezone.utc).isoformat(), touched=time.monotonic())


def submit(kind, aid, params):
    from . import server
    aid = server.short_id(aid); path = str(server.DB)
    with server.db() as conn:
        rev = revision(conn)
        job = conn.execute('SELECT status FROM jobs WHERE id=?', (aid,)).fetchone()
    if not job or job[0] != 'complete': raise HTTPException(409, '请先完成该学者的论文采集')
    key = hashlib.sha256(json.dumps([path, kind, aid, params, rev], sort_keys=True).encode()).hexdigest()
    with SUBMIT_LOCK:
        prune()
        for task in TASKS.values():
            if task['key'] == key and task['status'] in {'queued', 'running', 'complete'}:
                return read(path, task['id'], cached=task['status'] == 'complete')
        if sum(t['status'] in {'queued', 'running'} for t in TASKS.values()) >= MAX_PENDING:
            raise HTTPException(429, '计算队列暂满，请稍后重试')
        prune(reserve=1)
        task_id = uuid.uuid4().hex
        TASKS[task_id] = dict(id=task_id, key=key, path=path, status='queued',
                             created_at=datetime.now(timezone.utc).isoformat(), finished_at=None, touched=time.monotonic())
        POOL.submit(run, path, task_id, kind, aid, params, rev)
    return {'id':task_id, 'status':'queued', 'cache_hit':False}


class AnnualParameters(BaseModel):
    start: int = Field(2016, ge=1000, le=9999)
    end: int = Field(2025, ge=1000, le=9999)
    window: int = Field(5, ge=1, le=20)


@router.post('/api/compute/groups/{aid}')
def groups(aid: str, body: Parameters):
    if body.start > body.end or body.end-body.start > 30: raise HTTPException(422, '请选择最多31年的范围')
    return submit('groups', aid, body.model_dump())


@router.post('/api/compute/insights/{aid}')
def insights(aid: str, body: AnnualParameters):
    if body.start > body.end or body.end-body.start > 50: raise HTTPException(422, '请选择最多51年的范围')
    return submit('insights', aid, body.model_dump())


@router.get('/api/computations/{task_id}')
def status(task_id: str):
    from . import server
    return read(server.DB, task_id)
