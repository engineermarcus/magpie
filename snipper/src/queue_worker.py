import threading
import time

_jobs: dict = {}
_lock = threading.Lock()


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
