"""Bounded online member acquisition; every author retains their own cursor.

Batch metadata only. Do not union author filters for works: that would obscure
individual coverage and identity-conflict evidence in source author histories.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
import json
import threading
import time
from .source_control import TRACKING

WORKERS=8


def run(aid, selected, key):
    from . import server
    from .group_api import state, update, calculate, Parameters
    started=time.monotonic();completed=0;pending={};active={};metrics={'source_requests':0,'downloaded_bytes':0,'request_seconds':0.,'rate_limit_responses':0}
    lock=threading.Lock();failure=None;paused=False;queue=iter(selected);estimates={}

    def observe(seconds,size,status):
        with lock:
            metrics['source_requests']+=1;metrics['downloaded_bytes']+=size
            metrics['request_seconds']+=seconds;metrics['rate_limit_responses']+=status==429

    def publish(**extra):
        with lock:stats=dict(metrics)
        update(aid,completed=completed,current=next(iter(active),None),
               current_name='、'.join(active.values()),active_authors=list(active),
               workers=WORKERS,elapsed_seconds=round(time.monotonic()-started,2),**stats,**extra)

    def fetch(author):
        target=server.short_id(author['id']);TRACKING.observer=observe
        try:
            with server.db() as conn:
                value=json.loads(conn.execute('SELECT raw FROM group_collections WHERE id=?',(aid,)).fetchone()[0])
                if value.get('pause_requested'):return 'paused',None
                job=conn.execute('SELECT status FROM jobs WHERE id=?',(target,)).fetchone()
                if job and job['status']=='complete':return 'complete',None
                conn.execute("INSERT OR IGNORE INTO jobs VALUES (?,'running','*',0,NULL,NULL,NULL)",(target,))
                conn.execute("UPDATE jobs SET status='running',error=NULL WHERE id=?",(target,))
            server.collect(target,key,release_lock=False)
            with server.db() as conn:job=conn.execute('SELECT status,error FROM jobs WHERE id=?',(target,)).fetchone()
            return job['status'],job['error']
        finally:TRACKING.observer=None

    def halt_active():
        with server.db() as conn:
            for target in active:
                conn.execute("UPDATE jobs SET status='paused' WHERE id=? AND status='running'",(target,))

    try:
        update(aid,started_at=datetime.now(timezone.utc).isoformat(),workers=WORKERS,active_authors=[])
        # At most 100 IDs per documented OR lookup; missing/merged records fall
        # back to the individual endpoint rather than being guessed or dropped.
        TRACKING.observer=observe
        for offset in range(0,len(selected),100):
            if state(aid).get('pause_requested'):paused=True;break
            ids=[server.short_id(a['id']) for a in selected[offset:offset+100]]
            response=server.upstream('authors',{'filter':'openalex_id:'+'|'.join(ids),'per_page':100},key)
            with server.db() as conn:
                for author in response.get('results',[]):
                    target=(author.get('id') or '').removeprefix('https://openalex.org/')
                    if target not in ids:continue
                    count=author.get('works_count')
                    if isinstance(count,int) and count>=0:estimates[target]=count
                    conn.execute("INSERT OR IGNORE INTO jobs VALUES (?,'waiting','*',0,NULL,NULL,NULL)",(target,))
                    conn.execute('UPDATE jobs SET author=? WHERE id=?',(json.dumps(author),target))
        TRACKING.observer=None
        # Start long histories early so a large late-listed author does not leave
        # seven lanes idle at the end. Stable ties preserve the cohort priority.
        queue=iter(sorted(selected,key=lambda a:-estimates.get(server.short_id(a['id']),0)))
        with ThreadPoolExecutor(max_workers=WORKERS,thread_name_prefix='member-source') as pool:
            exhausted=paused
            while pending or not exhausted:
                if state(aid).get('pause_requested'):paused=True
                if paused or failure:exhausted=True;halt_active()
                while not exhausted and len(pending)<WORKERS:
                    author=next(queue,None)
                    if author is None:exhausted=True;break
                    target=server.short_id(author['id']);active[target]=author['name']
                    pending[pool.submit(fetch,author)]=target
                publish()
                if not pending:break
                done,_=wait(pending,timeout=.25,return_when=FIRST_COMPLETED)
                for future in done:
                    target=pending.pop(future);active.pop(target,None)
                    try:status,error=future.result()
                    except Exception:status,error='error','成员获取失败，请重试。'
                    if status=='complete':completed+=1
                    elif status=='paused':paused=True
                    else:failure=failure or error or '成员历史未完成，请重试。'
        if failure or paused:
            with server.db() as conn:
                for author in selected:
                    conn.execute("UPDATE jobs SET status='paused' WHERE id=? AND status='waiting'",(server.short_id(author['id']),))
            if failure:publish(status='error',message=failure);return
            publish(status='paused',message='已暂停全部并发获取，本次分页进度可继续。');return
        value=state(aid);calculation=time.monotonic()
        summary=calculate(aid,Parameters(**value['plan']['parameters']))[0]['summary']
        publish(status='complete',result_summary=summary,calculation_seconds=round(time.monotonic()-calculation,3),message='成员历史获取完成，画像已重新计算。')
    except Exception as error:
        publish(status='error',message=str(error) if isinstance(error,ValueError) else '成员获取中断，本次进度可继续。')
    finally:
        TRACKING.observer=None
        server.LOCK.release()
