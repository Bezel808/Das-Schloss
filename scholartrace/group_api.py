"""Group portraits and resumable collection of their members' own histories."""
import hashlib
import json
import math
import threading
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from .groups import portrait, people, institution_ids
from .analytics import clean_works

router = APIRouter(prefix='/api/groups')


class Parameters(BaseModel):
    start: int = Field(2016, ge=1000, le=9999)
    end: int = Field(2025, ge=1000, le=9999)
    scope: Literal['shared_institution', 'all_collaborators'] = 'shared_institution'
    window: int = Field(5, ge=1, le=10)
    early_years: int = Field(3, ge=1, le=5)
    prior_papers: int = Field(5, ge=0, le=20)
    early_papers: int = Field(5, ge=1, le=20)
    followup: int = Field(2, ge=1, le=5)
    incumbent_papers: int = Field(2, ge=1, le=10)
    max_team: int = Field(50, ge=2, le=200)


class CollectionRequest(Parameters):
    limit: int = Field(12, ge=1, le=30)
    plan_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


def snapshot(focal_id, params, bibliometrics=False):
    """Read only the focal history and its directly qualifying collaborators.

    Candidate discovery uses the focal author's own source records. Unrelated
    searches cannot expand this observation boundary or slow the paper scan.
    """
    from . import server
    focal_id = server.short_id(focal_id)
    focal = 'https://openalex.org/' + focal_id
    corpora, coverage, names, metadata = {}, {}, {}, {}
    with server.db() as conn:
        conn.execute('BEGIN')
        fields = ['id', 'doi', 'title', 'display_name', 'publication_year', 'authorships', 'is_retracted', 'is_paratext']
        if bibliometrics: fields += ['referenced_works', 'topics', 'primary_location']
        # Transfer only calculation inputs; abstracts, access locations and other
        # unused payloads stay out of JSON decoding and fingerprint serialization.
        projection = 'json_object(' + ','.join("'%s',json_extract(raw,'$.%s')" % (f,f) for f in fields) + ", 'authors_count',coalesce(json_extract(raw,'$.authors_count'),json_array_length(raw,'$.authorships')))"
        own = [json.loads(r[0]) for r in conn.execute(f'SELECT {projection} FROM papers WHERE job=? ORDER BY id', (focal_id,))]
        own = [{k:v for k,v in w.items() if v is not None} for w in own]
        works, _ = clean_works([w for w in own if isinstance(w.get('publication_year'), int) and w['publication_year'] <= params.end])
        selected = {focal_id}
        for work in works:
            aa = people(work)
            if focal not in aa or len(aa) > params.max_team: continue
            for author, entry in aa.items():
                if params.scope == 'shared_institution' and not institution_ids(aa[focal]) & institution_ids(entry): continue
                short = author.removeprefix('https://openalex.org/')
                if short.startswith('A') and short[1:].isdigit(): selected.add(short)
        jobs, records, meta = [], [], []
        ids = sorted(selected)
        for offset in range(0, len(ids), 500):
            batch = ids[offset:offset+500]; placeholders = ','.join('?' for _ in batch)
            jobs.extend(conn.execute(f'SELECT * FROM jobs WHERE id IN ({placeholders}) ORDER BY id', batch).fetchall())
            records.extend(conn.execute(f'SELECT job,{projection} AS raw FROM papers WHERE job IN ({placeholders}) ORDER BY job,id', batch).fetchall())
            meta.extend(conn.execute(f'SELECT id,raw FROM author_metadata WHERE id IN ({placeholders})', batch).fetchall())
    for row in jobs:
        aid = 'https://openalex.org/' + row['id']
        author = json.loads(row['author'] or '{}')
        names[aid] = author.get('display_name') or row['id']
        metadata[aid] = author
        through = None
        if row['updated']:
            try:
                through = min(datetime.fromisoformat(row['updated']).year,
                              datetime.now(timezone.utc).year) - 1
            except (ValueError, TypeError):
                pass
        corpora[aid] = []
        coverage[aid] = {'complete': row['status'] == 'complete', 'through': through,
                         'status': row['status'], 'retrieved_at': row['updated']}
    for row in records:
        record = {k:v for k,v in json.loads(row['raw']).items() if v is not None}
        corpora.setdefault('https://openalex.org/' + row['job'], []).append(record)
    for row in meta:
        record = json.loads(row['raw'])
        aid = record.get('id') or 'https://openalex.org/' + row['id'].rsplit('/', 1)[-1]
        metadata.setdefault(aid, record)
    return corpora, coverage, names, metadata


def calculate(aid, params):
    from . import server
    aid = server.short_id(aid)
    corpora, coverage, names, metadata = snapshot(aid, params)
    focal = 'https://openalex.org/' + aid
    if not coverage.get(focal, {}).get('complete'):
        raise HTTPException(409, '请先完成目标学者的论文采集')
    try:
        result = portrait(corpora, focal, coverage, names, **params.model_dump())
    except ValueError as error:
        raise HTTPException(422, str(error))
    result['input_schema'] = 'group-analysis-fields-1'
    result['observation_scope'] = {'kind': 'focal_and_direct_collaborator_histories',
                                   'author_histories': len(corpora),
                                   'source_records': sum(map(len, corpora.values())),
                                   'description': '目标学者及符合所选口径的直接合作者历史；不扫描其他查询的数据。'}
    return result, metadata


@router.get('/{aid}')
def get_portrait(aid: str, params: Parameters = Depends()):
    return calculate(aid, params)[0]


def plan(aid, params, limit):
    result, metadata = calculate(aid, params)
    missing = [r for r in result['members'] if not r['history_complete']]
    # An entry's age is unknown before fetching its own history. Never rank by
    # apparent youth computed from the focal author's papers.
    missing.sort(key=lambda r: (not params.start <= r['entry_year'] <= params.end-params.followup,
                                -r['qualifying_papers'], r['id']))
    selected = []
    for row in missing[:limit]:
        count = metadata.get(row['id'], {}).get('works_count')
        selected.append({'id': row['id'], 'name': row['name'], 'entry_year': row['entry_year'],
                         'qualifying_papers': row['qualifying_papers'],
                         'estimated_pages': max(1, math.ceil(count/100)) if isinstance(count, int) and count >= 0 else None})
    value = {'focal': result['focal'], 'parameters': params.model_dump(), 'authors': selected,
             'missing_histories': len(missing), 'complete_histories': len(result['members'])-len(missing),
             'member_count': len(result['members']), 'limit': limit,
             'unknown_cost_authors': sum(a['estimated_pages'] is None for a in selected),
             'known_estimated_pages': sum(a['estimated_pages'] or 0 for a in selected),
             'note': '只补采当前口径内的成员历史；优先观察期已满的进入者，再按共同论文数。当前会话内复用，部分采集从临时游标继续。页数为粗估，不含作者资料与大团队作者列表补全请求。'}
    value['plan_sha256'] = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    return value


@router.get('/{aid}/plan')
def get_plan(aid: str, params: Parameters = Depends(), limit: int = Query(12, ge=1, le=30)):
    return plan(aid, params, limit)


def state(aid):
    from . import server
    with server.db() as conn:
        row = conn.execute('SELECT raw FROM group_collections WHERE id=?', (aid,)).fetchone()
    return json.loads(row[0]) if row else {'status': 'not_started'}


def update(aid, **changes):
    from . import server
    with server.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT raw FROM group_collections WHERE id=?', (aid,)).fetchone()
        value = json.loads(row[0]) if row else {}
        value.update(changes, updated_at=datetime.now(timezone.utc).isoformat())
        conn.execute('INSERT OR REPLACE INTO group_collections VALUES (?,?)', (aid, json.dumps(value)))
    return value


@router.get('/{aid}/collection')
def get_collection(aid: str):
    from . import server
    return state(server.short_id(aid))


def run_collection(aid, selected, key):
    from . import server
    completed = 0
    try:
        for author in selected:
            target = server.short_id(author['id'])
            with server.db() as conn:
                conn.execute('BEGIN IMMEDIATE')
                value = json.loads(conn.execute('SELECT raw FROM group_collections WHERE id=?', (aid,)).fetchone()[0])
                if value.get('pause_requested'):
                    value.update(status='paused', current=None)
                    conn.execute('UPDATE group_collections SET raw=? WHERE id=?', (json.dumps(value), aid))
                    return
                job = conn.execute('SELECT status FROM jobs WHERE id=?', (target,)).fetchone()
                cached = bool(job and job['status'] == 'complete')
                if not cached:
                    conn.execute("INSERT OR IGNORE INTO jobs VALUES (?,'running','*',0,NULL,NULL,NULL)", (target,))
                    conn.execute("UPDATE jobs SET status='running',error=NULL WHERE id=?", (target,))
                value.update(current=target, current_name=author['name'], completed=completed)
                conn.execute('UPDATE group_collections SET raw=? WHERE id=?', (json.dumps(value), aid))
            if not cached:
                server.collect(target, key, release_lock=False)
            with server.db() as conn:
                job = conn.execute('SELECT status,error FROM jobs WHERE id=?', (target,)).fetchone()
            if job['status'] == 'complete':
                completed += 1
            if state(aid).get('pause_requested') or job['status'] == 'paused':
                update(aid, status='paused', completed=completed, current=None, message='已暂停，论文与分页进度已保存。')
                return
            if job['status'] != 'complete':
                update(aid, status='error', completed=completed, message=job['error'] or '采集未完成，请重新预览后继续。')
                return
            update(aid, completed=completed)
        value=state(aid)
        summary=calculate(aid, Parameters(**value['plan']['parameters']))[0]['summary'] if value.get('mode')=='automatic' else None
        update(aid, status='complete', completed=completed, current=None, result_summary=summary,
               message='队列已完成，画像已重新计算。' if summary is not None else '本批成员历史已完成，可以重新计算画像。')
    except Exception:
        update(aid, status='error', completed=completed, message='成员补采中断，进度已保存，请重新预览后继续。')
    finally:
        server.LOCK.release()


@router.post('/{aid}/collect')
def start_collection(aid: str, body: CollectionRequest):
    from . import server
    aid = server.short_id(aid)
    params = Parameters(**body.model_dump())
    if not server.LOCK.acquire(blocking=False):
        raise HTTPException(409, '已有采集正在运行，请等待完成或暂停后重试')
    try:
        proposal = plan(aid, params, body.limit)
        if body.plan_sha256 != proposal['plan_sha256']:
            raise HTTPException(409, '缓存或采集范围已变化，请重新预览补采名单')
        if proposal['authors'] and not server.KEY:
            raise HTTPException(400, '请先在设置中填写 OpenAlex API Key')
        update(aid, status='running', pause_requested=False, completed=0, total=len(proposal['authors']),
               current=None, message='', mode='batch', plan=proposal)
        threading.Thread(target=run_collection, args=(aid, proposal['authors'], server.KEY), daemon=True).start()
    except Exception:
        server.LOCK.release()
        raise
    return {'id': aid, 'total': len(proposal['authors'])}


@router.post('/{aid}/pause')
def pause_collection(aid: str):
    from . import server
    aid = server.short_id(aid)
    with server.db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT raw FROM group_collections WHERE id=?', (aid,)).fetchone()
        if row:
            value = json.loads(row[0])
            if value['status'] == 'running':
                value['pause_requested'] = True
                value['message'] = '正在保存本页，随后暂停。'
                conn.execute('UPDATE group_collections SET raw=? WHERE id=?', (json.dumps(value), aid))
                for target in value.get('active_authors') or ([value['current']] if value.get('current') else []):
                    conn.execute("UPDATE jobs SET status='paused' WHERE id=? AND status='running'", (target,))
    return state(aid)


@router.post('/{aid}/auto')
def auto_collection(aid: str, body: Parameters):
    """Bounded concurrent cohort queue; never recursively crawl coauthors."""
    from . import server
    aid=server.short_id(aid)
    if not server.LOCK.acquire(blocking=False):
        raise HTTPException(409,'已有采集正在运行，请等待完成或暂停后继续')
    try:
        proposal=plan(aid,body,None)
        if proposal['authors'] and not server.KEY:
            raise HTTPException(400,'请先在设置中填写 OpenAlex API Key')
        update(aid,status='running',mode='automatic',pause_requested=False,completed=0,
               total=len(proposal['authors']),current=None,message='已自动建立当前合作圈的全部缺失历史队列。',
               result_summary=None,plan=proposal)
        from .parallel_collection import run as run_parallel
        threading.Thread(target=run_parallel,args=(aid,proposal['authors'],server.KEY),daemon=True).start()
    except Exception:
        server.LOCK.release()
        raise
    return {'id':aid,'total':len(proposal['authors']),'mode':'automatic'}
