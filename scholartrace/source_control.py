"""Process-wide request pacing and shared upstream backoff; never log credentials."""
import threading
import time
from email.utils import parsedate_to_datetime

class RequestGate:
    def __init__(self, per_second=8, clock=time.monotonic, sleeper=time.sleep):
        self.interval=1/per_second;self.clock=clock;self.sleep=sleeper
        self.lock=threading.Lock();self.next_request=0.;self.blocked_until=0.

    def wait(self):
        while True:
            with self.lock:
                now=self.clock();delay=max(self.next_request,self.blocked_until)-now
                if delay<=0:
                    self.next_request=now+self.interval;return
            if delay>30:raise ValueError('数据源要求较长等待，请稍后重试；本次进度可继续。')
            self.sleep(delay)

    def defer(self, seconds):
        with self.lock:self.blocked_until=max(self.blocked_until,self.clock()+seconds)

GATE=RequestGate()
TRACKING=threading.local()

# All fields consumed by timeline, graph, group evidence, BM25, inference and
# yearly/ranking analyses. Keep abstracts/references so opening a collaborator
# later does not silently downgrade those features.
WORK_FIELDS='id,doi,title,display_name,publication_year,publication_date,type,authorships,is_authors_truncated,is_retracted,is_paratext,topics,primary_location,abstract_inverted_index,referenced_works,cited_by_count'


def retry_delay(value, attempt, wall_time=time.time):
    try:return max(0.,float(value))
    except (TypeError,ValueError):
        try:return max(0.,parsedate_to_datetime(value).timestamp()-wall_time())
        except (TypeError,ValueError,OverflowError):return 2**attempt

# Separate from member workers: a member can wait for its full-authorship
# requests without occupying a worker in this pool. HTTP connections and GATE
# remain shared, so this does not multiply upstream concurrency.
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
FULL_WORK_POOL=ThreadPoolExecutor(max_workers=8,thread_name_prefix='full-authorships')

class CollectionPaused(Exception):
    pass


def complete_authorships(works, aid, key):
    import re
    from . import server
    indices=[i for i,w in enumerate(works) if w.get('is_authors_truncated') or w.get('authors_count',0)>len(w.get('authorships',[]))]
    observer=getattr(TRACKING,'observer',None)
    def fetch(index):
        TRACKING.observer=observer
        try:
            with server.db() as c:
                job=c.execute('SELECT status FROM jobs WHERE id=?',(aid,)).fetchone()
                if job and job['status']=='paused':raise CollectionPaused()
            wid=works[index]['id'].rsplit('/',1)[-1]
            if not re.fullmatch(r'W\d+',wid):raise ValueError('数据源返回了无效论文 ID')
            return index,server.upstream('works/'+wid,{'select':WORK_FIELDS},key=key)
        finally:TRACKING.observer=None
    if indices:
        pending=set();queue=iter(indices);failure=None;exhausted=False
        while pending or not exhausted:
            while not exhausted and not failure and len(pending)<8:
                index=next(queue,None)
                if index is None:exhausted=True;break
                pending.add(FULL_WORK_POOL.submit(fetch,index))
            if not pending:break
            done,pending=wait(pending,return_when=FIRST_COMPLETED)
            for future in done:
                try:
                    index,work=future.result();works[index]=work
                except Exception as error:failure=failure or error;exhausted=True
            # Drain every submitted request before the parent releases its lock.
        if failure:raise failure
    for work in works:
        if work.get('is_authors_truncated') or work.get('authors_count',0)>len(work.get('authorships',[])):
            raise ValueError('单篇接口仍返回截断作者列表，不能确认历史完整，请稍后重试。')
        work.setdefault('authors_count',len(work.get('authorships',[])))
    return works
