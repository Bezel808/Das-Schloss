"""Local, single-user application. Keys stay in process memory only."""
import json
import atexit
import hashlib
import os
import re
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import analyze
from .identifiers import orcid_id
from .network import decorate_graph
from . import storage
from .source_control import GATE, TRACKING, WORK_FIELDS, retry_delay, complete_authorships, CollectionPaused

DB = os.environ.get('SCHOLARTRACE_DB', storage.MEMORY_DB)
KEY = os.environ.get('OPENALEX_API_KEY', '')
LOCK = threading.Lock()
SCHEDULER_LOCK = threading.Lock()
STATIC = Path(__file__).parent / 'static'
SOURCE_CLIENT = httpx.Client(timeout=40, limits=httpx.Limits(max_connections=8, max_keepalive_connections=8))
atexit.register(SOURCE_CLIENT.close)


def db():
    return storage.connect(DB)


def initialize():
    with db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS author_metadata (id TEXT PRIMARY KEY, raw TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, raw TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, cursor TEXT, total INTEGER, author TEXT, error TEXT, updated TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS papers (job TEXT, id TEXT, raw TEXT, PRIMARY KEY(job,id))')
        conn.execute('CREATE TABLE IF NOT EXISTS group_collections (id TEXT PRIMARY KEY, raw TEXT)')
        for row in conn.execute('SELECT id,raw FROM group_collections').fetchall():
            state = json.loads(row['raw'])
            if state.get('status') == 'running':
                state.update(status='interrupted', message='服务已重启，请重新预览后继续补采。')
                conn.execute('UPDATE group_collections SET raw=? WHERE id=?', (json.dumps(state), row['id']))
        from .computations import initialize as initialize_computations
        initialize_computations(conn)
        conn.execute("UPDATE jobs SET status='interrupted', error='服务已重启，点击继续采集恢复。' WHERE status='running'")


@asynccontextmanager
async def lifespan(app):
    initialize()
    ensure_collection_scheduler()
    stop = threading.Event()
    cleaner = threading.Thread(target=storage.maintenance, args=(stop,), daemon=True)
    cleaner.start()
    try:
        yield
    finally:
        stop.set()
        cleaner.join(timeout=2)


app = FastAPI(title='Das Schloss', lifespan=lifespan)


@app.middleware('http')
async def local_only(request: Request, call_next):
    host = request.headers.get('host', '').split(':')[0]
    origin = request.headers.get('origin')
    if host not in {'127.0.0.1', 'localhost', 'testserver'}:
        return __import__('starlette.responses', fromlist=['JSONResponse']).JSONResponse({'detail': 'Local access only'}, status_code=403)
    if origin and origin != str(request.base_url).rstrip('/'):
        return __import__('starlette.responses', fromlist=['JSONResponse']).JSONResponse({'detail': 'Origin rejected'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Cache-Control'] = 'no-store'
    return response


def upstream(path, params=None, key=None):
    headers = {'Authorization': 'Bearer ' + key} if key else {}
    for attempt in range(4):
        GATE.wait()
        began = time.monotonic()
        try:
            response = SOURCE_CLIENT.get('https://api.openalex.org/' + path, params=params, headers=headers)
        except httpx.RequestError:
            observer = getattr(TRACKING, 'observer', None)
            if observer: observer(time.monotonic()-began, 0, -1)
            if attempt == 3:
                raise ValueError('OpenAlex 连接失败，请检查网络后继续。')
            time.sleep(2 ** attempt)
            continue
        observer = getattr(TRACKING, 'observer', None)
        if observer: observer(time.monotonic()-began, response.num_bytes_downloaded or len(response.content), response.status_code)
        if response.status_code == 429 or response.status_code >= 500:
            delay = retry_delay(response.headers.get('Retry-After', ''), attempt)
            GATE.defer(delay)
            if attempt == 3:
                raise ValueError('OpenAlex 限额或服务暂不可用，本次进度可继续，请稍后重试。')
            if delay > 30:
                raise ValueError('OpenAlex 要求稍后重试，本次进度可继续。')
            continue
        if response.status_code in (401, 403):
            raise ValueError('API Key 无效、未激活或缺少访问权限，请在设置中更新。')
        if response.status_code == 404 and path.startswith('authors/orcid:'):
            return None
        if response.status_code != 200:
            raise ValueError('OpenAlex 请求失败（HTTP %s）。' % response.status_code)
        return response.json()


def short_id(value):
    value = value.removeprefix('https://openalex.org/')
    if not re.fullmatch(r'A\d+', value):
        raise HTTPException(422, '请输入有效的 OpenAlex 作者 ID')
    return value


class Settings(BaseModel):
    api_key: str = Field(max_length=512)


@app.get('/api/settings')
def settings():
    return {'key_configured': bool(KEY), 'storage': 'temporary_memory' if storage.ephemeral(DB) else 'explicit_file', 'idle_expiry_seconds': storage.IDLE_SECONDS if storage.ephemeral(DB) else None}


@app.post('/api/settings')
def set_settings(body: Settings):
    global KEY
    KEY = body.api_key.strip()
    ensure_collection_scheduler()
    return {'key_configured': bool(KEY), 'storage': 'temporary_memory' if storage.ephemeral(DB) else 'explicit_file', 'idle_expiry_seconds': storage.IDLE_SECONDS if storage.ephemeral(DB) else None}


@app.post('/api/session/reset')
def reset_session():
    if not storage.ephemeral(DB):
        raise HTTPException(409, '当前使用研究数据文件，不能从此处清空')
    if not storage.expire_idle(force=True):
        raise HTTPException(409, '仍有采集或计算正在运行，请暂停采集并等待当前计算完成')
    return {'ok': True}


@app.get('/api/authors')
def authors(q: str = '', cursor: str = '*'):
    if len(q.strip()) < 2 or len(q) > 200:
        raise HTTPException(422, '请输入 2–200 个字符的姓名或作者 ID')
    if not cursor or len(cursor) > 4096:
        raise HTTPException(422, '无效的搜索页，请重新搜索')
    try:
        identifier = orcid_id(q)
    except ValueError as error:
        raise HTTPException(422, str(error))
    try:
        if identifier:
            author = upstream('authors/orcid:' + identifier, key=KEY)
            return {'results': [author] if author else [], 'lookup': 'orcid',
                    'meta': {'count': int(bool(author)), 'next_cursor': None}}
        if re.fullmatch(r'(https://openalex.org/)?A\d+', q.strip()):
            author = upstream('authors/' + short_id(q.strip()), key=KEY)
            return {'results': [author] if author else [], 'lookup': 'openalex',
                    'meta': {'count': int(bool(author)), 'next_cursor': None}}
        return upstream('authors', {'search': q.strip(), 'per_page': 12, 'cursor': cursor}, KEY)
    except ValueError as error:
        raise HTTPException(502, str(error))


class Start(BaseModel):
    author_id: str


def collect(aid, key, release_lock=True):
    try:
        with db() as conn:
            job = dict(conn.execute('SELECT * FROM jobs WHERE id=?', (aid,)).fetchone())
        if not job['author']:
            author = upstream('authors/' + aid, key=key)
            with db() as conn:
                conn.execute('UPDATE jobs SET author=? WHERE id=?', (json.dumps(author), aid))
        cursor = job['cursor']
        while cursor:
            with db() as conn:
                status = conn.execute('SELECT status FROM jobs WHERE id=?', (aid,)).fetchone()[0]
            if status == 'paused':
                return
            page = upstream('works', {'filter': 'authorships.author.id:' + aid, 'per_page': 100, 'cursor': cursor, 'select': WORK_FIELDS}, key)
            works = complete_authorships(page['results'], aid, key)
            next_cursor = page['meta'].get('next_cursor') if works else None
            if next_cursor == cursor:
                raise ValueError('数据源游标没有前进，请稍后重试。')
            encoded = [(aid, work['id'], json.dumps(work, ensure_ascii=False, separators=(',', ':'))) for work in works]
            with db() as conn:
                if storage.ephemeral(DB):
                    pages = conn.execute('PRAGMA page_count').fetchone()[0] - conn.execute('PRAGMA freelist_count').fetchone()[0]
                    used = pages * conn.execute('PRAGMA page_size').fetchone()[0]
                    incoming = sum(len(raw.encode()) + 8192 for _, _, raw in encoded)
                    if used + incoming > storage.MAX_SOURCE_BYTES - 1024*1024:
                        raise ValueError('当前查询达到临时数据容量，请清空临时查询后缩小采集范围；未完成的历史不会视作完整数据。')
                conn.executemany('INSERT OR REPLACE INTO papers VALUES (?,?,?)', encoded)
                conn.execute('UPDATE jobs SET cursor=?, total=?, updated=? WHERE id=?',
                             (next_cursor, page['meta']['count'], datetime.now(timezone.utc).isoformat(), aid))
            cursor = next_cursor
        with db() as conn:
            conn.execute("UPDATE jobs SET status='complete',error=NULL WHERE id=?", (aid,))
    except CollectionPaused:
        with db() as conn:conn.execute("UPDATE jobs SET status='paused',error=NULL WHERE id=?", (aid,))
    except Exception as error:
        message = ('当前查询超过临时数据容量，请缩小采集范围。' if isinstance(error, sqlite3.OperationalError) and 'full' in str(error).lower() else
                   str(error) if isinstance(error, ValueError) else '采集失败，本次进度暂存在内存，请重试。')
        with db() as conn:
            conn.execute("UPDATE jobs SET status='error',error=? WHERE id=?", (message, aid))
    finally:
        if release_lock:
            LOCK.release()


@app.post('/api/jobs')
def start(body: Start):
    aid = short_id(body.author_id)
    with db() as conn:
        existing = conn.execute('SELECT status FROM jobs WHERE id=?',(aid,)).fetchone()
    if existing and existing['status'] in {'complete','running','queued'}:
        return {'id':aid,'reused':True}
    if not KEY:
        raise HTTPException(400, '请先在设置中填写 OpenAlex API Key')
    if not LOCK.acquire(blocking=False):
        with db() as conn:
            conn.execute("INSERT OR IGNORE INTO jobs VALUES (?, 'queued', '*', 0, NULL, NULL, NULL)",(aid,))
            conn.execute("UPDATE jobs SET status='queued',error=NULL WHERE id=? AND status NOT IN ('complete','running')",(aid,))
        ensure_collection_scheduler()
        return {'id':aid,'queued':True}
    with db() as conn:
        existing = conn.execute('SELECT * FROM jobs WHERE id=?', (aid,)).fetchone()
        if existing and existing['status'] == 'complete':
            LOCK.release()
            return {'id': aid}
        conn.execute("INSERT OR IGNORE INTO jobs VALUES (?, 'running', '*', 0, NULL, NULL, NULL)", (aid,))
        conn.execute("UPDATE jobs SET status='running',error=NULL WHERE id=?", (aid,))
    threading.Thread(target=collect, args=(aid, KEY), daemon=True).start()
    return {'id': aid}


@app.get('/api/jobs')
def jobs():
    with db() as conn:
        records = conn.execute('SELECT jobs.*, (SELECT count(*) FROM papers WHERE job=jobs.id) AS received FROM jobs ORDER BY updated DESC').fetchall()
    result = []
    for record in records:
        item = dict(record)
        item.pop('cursor')
        item['author'] = json.loads(item['author']) if item['author'] else None
        result.append(item)
    return result


@app.post('/api/jobs/{aid}/pause')
def pause(aid: str):
    with db() as conn:
        conn.execute("UPDATE jobs SET status='paused' WHERE id=? AND status IN ('running','queued')", (short_id(aid),))
    return {'ok': True}


@app.get('/api/report/{aid}')
def report(aid: str, start: int = 0, end: int = 9999, work_type: str = '', institution: str = '', resolution: float = 1.0):
    aid = short_id(aid)
    if not 0.1 <= resolution <= 3:
        raise HTTPException(422, '社区分辨率范围为 0.1–3')
    if start > end:
        raise HTTPException(422, '起始年份不能晚于结束年份')
    with db() as conn:
        job = conn.execute('SELECT * FROM jobs WHERE id=?', (aid,)).fetchone()
        if not job:
            raise HTTPException(404, '尚未采集该作者')
        works = [json.loads(row[0]) for row in conn.execute('SELECT raw FROM papers WHERE job=? ORDER BY id', (aid,))]
    selected = [w for w in works if start <= (w.get('publication_year') or 0) <= end]
    if work_type:
        selected = [w for w in selected if w.get('type') == work_type]
    if institution:
        selected = [w for w in selected if any(i.get('id') == institution for a in w.get('authorships', [])
                    if a.get('author', {}).get('id') == 'https://openalex.org/' + aid for i in a.get('institutions', []))]
    valid, omitted = [], []
    for work in selected:
        a = work.get('authorships', [])
        ids = [x.get('author', {}).get('id') for x in a]
        # Bound quadratic projection cost, while preserving these works in the evidence list.
        reason = None
        if len(a) > 200:
            reason = '超过 200 位作者：保留论文，暂不纳入统计与图谱'
        elif work.get('authors_count', 0) > len(a) or None in ids or len(set(ids)) != len(ids):
            reason = '作者列表不完整或身份异常'
        elif not work.get('publication_year'):
            reason = '缺少发表年份'
        if reason:
            omitted.append({'id': work['id'], 'reason': reason})
        else:
            valid.append(work)
    result = analyze('https://openalex.org/' + aid, valid)
    with db() as conn:
        metadata = {row[0]: json.loads(row[1]) for row in conn.execute('SELECT id,raw FROM author_metadata')}
    decorate_graph(result['graph'], valid, 'https://openalex.org/' + aid, metadata, resolution)
    available_years = sorted({w['publication_year'] for w in works if isinstance(w.get('publication_year'), int) and w['publication_year'] > 0})
    result['time_axis'] = {'available_years': available_years,
                           'minimum_year': min(available_years) if available_years else None,
                           'maximum_year': max(available_years) if available_years else None}
    result['graph']['window'] = {'start_year': start, 'end_year': end, 'inclusive': True}
    result['graph']['snapshot'] = {'computed_at': datetime.now(timezone.utc).isoformat(),
                                   'last_page_retrieved_at': job['updated'],
                                   'historical_reconstruction': True,
                                   'note': 'Publication-window reconstruction using current cached metadata; not a historical database snapshot.'}
    result.update(author=json.loads(job['author']) if job['author'] else {}, papers=selected, omitted=omitted,
                  status=job['status'], retrieved_at=job['updated'], received=len(works), expected=job['total'],
                  missing_year_count=sum(not w.get('publication_year') for w in works))
    return result


app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.get('/')
def home():
    return FileResponse(STATIC / 'index.html')


@app.get('/api/retrieve/{aid}')
def retrieve_evidence(aid: str, q: str):
    from .retrieval import retrieve
    aid = short_id(aid)
    if not 2 <= len(q.strip()) <= 500:
        raise HTTPException(422, '请输入 2–500 个字符')
    with db() as conn:
        works = [json.loads(row[0]) for row in conn.execute('SELECT raw FROM papers WHERE job=?', (aid,))]
    return {'method': 'BM25', 'scope': 'cached scholar papers', 'corpus_size': len(works),
            'results': retrieve(works, q), 'generated_answer': None}


@app.post('/api/enrich/{aid}')
def enrich_authors(aid: str):
    aid = short_id(aid)
    current = report(aid)
    nodes = sorted(current['graph']['nodes'], key=lambda n: -n['shared_count'])[:101]
    with db() as conn:
        cached = {row[0] for row in conn.execute('SELECT id FROM author_metadata')}
    missing = [n['id'] for n in nodes if n['id'] not in cached]
    try:
        for offset in range(0, len(missing), 50):
            ids = '|'.join(short_id(i) for i in missing[offset:offset + 50])
            response = upstream('authors', {'filter': 'openalex_id:' + ids, 'per_page': 100}, KEY)
            with db() as conn:
                for author in response['results']:
                    conn.execute('INSERT OR REPLACE INTO author_metadata VALUES (?,?)', (author['id'], json.dumps(author)))
    except ValueError as error:
        raise HTTPException(502, str(error))
    return {'enriched': len(missing), 'scope': 'top 100 collaborators and focal'}



@app.get('/api/insights/{aid}')
def insights(aid: str, start: int = 2016, end: int = 2025, window: int = 5,
             fields: str = '', sources: str = '', include_rankings: bool = False):
    from .analytics import annual_panel
    from .ranking import compare_rankings
    aid = short_id(aid)
    if not 1000 <= start <= end <= 9999 or end-start > 50 or not 1 <= window <= 20:
        raise HTTPException(422, '请选择最多 51 年的范围，以及 1–20 年的网络窗口')
    from .group_api import snapshot, Parameters
    corpora, coverage, _, _ = snapshot(aid, Parameters(end=end, scope='all_collaborators', max_team=200), bibliometrics=True)
    focal = 'https://openalex.org/' + aid
    if not coverage.get(focal, {}).get('complete'):
        raise HTTPException(409, '请先完成该学者的论文采集')
    selected = sorted(a for a in corpora if coverage[a]['complete'])
    works = [work for author in selected for work in corpora[author]]
    panel = annual_panel(works, focal, start, end, window)
    panel['scope'] = 'focal and directly collaborating author histories; observed subgraph, not global network'
    digest = panel['input_sha256']
    jobs = [{'id':a.rsplit('/', 1)[-1], 'updated':coverage[a]['retrieved_at']} for a in selected]
    if (fields or sources) and not include_rankings:
        raise HTTPException(422, '年度统计不使用机构排名筛选参数')
    result = {'panel':panel,
              'corpus':{'author_corpora':[dict(j) for j in jobs], 'snapshot_sha256':digest,
                        'scope':'当前学者与直接合作者已完成的论文历史；指标限于这个观察范围。',
                        'historical_mode':'按发表年份回溯，使用当前元数据；并非当年数据库快照。'}}
    if include_rankings:
        try:
            result['rankings'] = compare_rankings(works, start, end,
                                     selected_fields=fields.split(',') if fields else None,
                                     selected_sources=sources.split(',') if sources else None)
        except ValueError as error:
            raise HTTPException(422, str(error))
    return result


from .group_api import router as group_router
app.include_router(group_router)


from .computations import router as computation_router
app.include_router(computation_router)


@app.get('/api/jobs/{aid}')
def get_job(aid: str):
    with db() as conn:
        row=conn.execute('SELECT jobs.*, (SELECT count(*) FROM papers WHERE job=jobs.id) AS received FROM jobs WHERE id=?',(short_id(aid),)).fetchone()
    if not row:raise HTTPException(404,'尚未采集该作者')
    value=dict(row);value.pop('cursor');value['author']=json.loads(value['author']) if value['author'] else None
    return value



def ensure_collection_scheduler():
    if not KEY:return
    with db() as conn:
        pending=conn.execute("SELECT 1 FROM jobs WHERE status='queued' LIMIT 1").fetchone()
    if pending and SCHEDULER_LOCK.acquire(blocking=False):
        threading.Thread(target=drain_collection_queue,daemon=True).start()


def drain_collection_queue():
    try:
        while KEY:
            with db() as conn:
                if not conn.execute("SELECT 1 FROM jobs WHERE status='queued' LIMIT 1").fetchone():break
            if not LOCK.acquire(blocking=False):
                time.sleep(.25)
                continue
            try:
                with db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    row=conn.execute("SELECT id FROM jobs WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
                    if not row:break
                    conn.execute("UPDATE jobs SET status='running',error=NULL WHERE id=?",(row['id'],))
                collect(row['id'],KEY,release_lock=False)
            finally:
                LOCK.release()
    finally:
        SCHEDULER_LOCK.release()
        with db() as conn:
            pending=conn.execute("SELECT 1 FROM jobs WHERE status='queued' LIMIT 1").fetchone()
        if KEY and pending:ensure_collection_scheduler()
