import threading
import time
from collections import deque

_jobs: dict = {}
_lock = threading.Lock()

# ── Worker pool ───────────────────────────────────────────────────────────────
MAX_ENCODE_WORKERS = 3   # max concurrent FFmpeg encodes
MAX_DOWNLOAD_WORKERS = 4 # max concurrent downloads

_encode_sem = threading.Semaphore(MAX_ENCODE_WORKERS)
_download_sem = threading.Semaphore(MAX_DOWNLOAD_WORKERS)

_encode_queue: deque = deque()
_download_queue: deque = deque()
_queue_lock = threading.Lock()


def get_job(key: str) -> dict:
    with _lock:
        return _jobs.get(key, {}).copy()


def set_job(key: str, status: str, **kwargs):
    with _lock:
        _jobs[key] = {"status": status, "updated": time.time(), **kwargs}


def job_exists(key: str) -> bool:
    with _lock:
        return key in _jobs


def all_jobs() -> dict:
    with _lock:
        return {k: v.copy() for k, v in _jobs.items()}


def remove_job(key: str):
    with _lock:
        _jobs.pop(key, None)


def queue_position(key: str) -> int:
    with _queue_lock:
        try:
            return list(_encode_queue).index(key) + 1
        except ValueError:
            return 0


# ── Encode queue ──────────────────────────────────────────────────────────────
def submit_encode(key: str, fn, *args, **kwargs):
    """
    Submit an encode job. fn(*args, **kwargs) runs when a worker slot is free.
    Returns immediately. Job status transitions: queued → starting → running → done/error
    """
    set_job(key, "queued")

    def worker():
        with _queue_lock:
            _encode_queue.append(key)
        set_job(key, "queued")
        _encode_sem.acquire()
        with _queue_lock:
            try:
                _encode_queue.remove(key)
            except ValueError:
                pass
        set_job(key, "starting")
        try:
            fn(*args, **kwargs)
        except Exception as e:
            set_job(key, "error", error=str(e))
        finally:
            _encode_sem.release()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t


# ── Download queue ────────────────────────────────────────────────────────────
def submit_download(key: str, fn, *args, **kwargs):
    """
    Submit a download job with concurrency cap.
    """
    set_job(key, "queued")

    def worker():
        _download_sem.acquire()
        set_job(key, "starting")
        try:
            fn(*args, **kwargs)
        except Exception as e:
            set_job(key, "error", error=str(e))
        finally:
            _download_sem.release()

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    return t
