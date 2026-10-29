"""Simple worker pool (stub).
"""
from concurrent.futures import ThreadPoolExecutor

executor = ThreadPoolExecutor(max_workers=4)


def submit(fn, *args, **kwargs):
    return executor.submit(fn, *args, **kwargs)
