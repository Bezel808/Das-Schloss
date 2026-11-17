"""A bounded, expiring in-memory workspace for interactive searches.

An explicit SCHOLARTRACE_DB path remains available for reproducible offline work.
The web default never opens the legacy paper database.
"""
from contextlib import contextmanager
import sqlite3
import threading
import time

MEMORY_DB = 'file:scholartrace-session?mode=memory&cache=shared'
MAX_SOURCE_BYTES = 512 * 1024 * 1024
IDLE_SECONDS = 1800
_LOCK = threading.RLock()
_ANCHOR = None
_LAST_USE = time.monotonic()


def ephemeral(path):
    return str(path) == MEMORY_DB


@contextmanager
def connect(path):
    global _ANCHOR, _LAST_USE
    # Shared-memory SQLite does not use WAL; serialize short transactions only.
    with _LOCK:
        if ephemeral(path) and _ANCHOR is None:
            _ANCHOR = sqlite3.connect(path, uri=True, check_same_thread=False)
            _ANCHOR.execute('PRAGMA temp_store=MEMORY')
            page_size = _ANCHOR.execute('PRAGMA page_size').fetchone()[0]
            _ANCHOR.execute(f'PRAGMA max_page_count={MAX_SOURCE_BYTES // page_size}')
        conn = sqlite3.connect(path, timeout=30, uri=ephemeral(path))
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA temp_store=MEMORY')
        if ephemeral(path): _LAST_USE = time.monotonic()
        try:
            with conn: yield conn
        finally: conn.close()


def expire_idle(now=None, force=False):
    """Expire the entire idle workspace, never half of an active analysis."""
    global _LAST_USE
    from . import computations, server
    now = time.monotonic() if now is None else now
    with _LOCK:
        if not ephemeral(server.DB) or _ANCHOR is None or (not force and now-_LAST_USE < IDLE_SECONDS):
            return False
        with computations.SUBMIT_LOCK:
            computations.prune(now)
            if any(t['status'] in {'queued', 'running'} for t in computations.TASKS.values()): return False
            if server.LOCK.locked() or server.SCHEDULER_LOCK.locked(): return False
            if _ANCHOR.execute("SELECT count(*) FROM jobs WHERE status IN ('running','queued')").fetchone()[0]: return False
            with _ANCHOR:
                for table in ['papers', 'jobs', 'author_metadata', 'analyses', 'group_collections']:
                    _ANCHOR.execute(f'DELETE FROM {table}')
            _ANCHOR.execute('VACUUM')
            computations.TASKS.clear()
        _LAST_USE = now
        return True


def maintenance(stop):
    from . import computations
    while not stop.wait(30):
        with computations.SUBMIT_LOCK: computations.prune()
        expire_idle()
