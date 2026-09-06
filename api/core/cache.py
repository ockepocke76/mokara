"""
In-process TTL cache — framework-free replacement for st.cache_data.

Every cache created by ttl_cache() is registered globally so clear_all()
can wipe them in one call (the admin "clear caches" path, and the
post-delete cache invalidation in the UI).

Like st.cache_data, cached values are returned as deep copies so callers
cannot mutate the stored entry. Objects that refuse deepcopy are returned
as-is.
"""
import copy
import threading
import time
from functools import wraps

_registry: list[dict] = []
_registry_lock = threading.Lock()


def ttl_cache(ttl: float = 300, maxsize: int = 256):
    """
    Decorator caching results per argument tuple for `ttl` seconds.

    Arguments must be hashable; unhashable ones fall back to their repr()
    as the cache key. The decorated function gets a .clear() method.
    """
    def decorator(func):
        cache: dict = {}
        lock = threading.Lock()
        with _registry_lock:
            _registry.append(cache)

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            try:
                hash(key)
            except TypeError:
                key = repr(key)

            now = time.monotonic()
            with lock:
                hit = cache.get(key)
                if hit is not None and hit[1] > now:
                    return _safe_copy(hit[0])

            value = func(*args, **kwargs)

            with lock:
                if len(cache) >= maxsize:
                    for k in [k for k, (_, exp) in cache.items() if exp <= now]:
                        del cache[k]
                    while len(cache) >= maxsize:
                        cache.pop(next(iter(cache)))
                cache[key] = (value, now + ttl)
            return _safe_copy(value)

        wrapper.clear = cache.clear
        return wrapper
    return decorator


def _safe_copy(value):
    try:
        return copy.deepcopy(value)
    except Exception:
        return value


def clear_all():
    """Clear every ttl_cache in the process (admin reset / invalidation)."""
    with _registry_lock:
        for cache in _registry:
            cache.clear()
