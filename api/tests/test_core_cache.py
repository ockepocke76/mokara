"""Tests for core/cache.py — the framework-free st.cache_data replacement."""
import time

from core.cache import ttl_cache, clear_all


def _counting_fn():
    calls = {'n': 0}

    @ttl_cache(ttl=60)
    def f(x, y=1):
        calls['n'] += 1
        return {'value': x + y}

    return f, calls


def test_hit_and_key_by_args():
    f, calls = _counting_fn()
    assert f(1) == {'value': 2}
    assert f(1) == {'value': 2}
    assert calls['n'] == 1
    assert f(2) == {'value': 3}
    assert calls['n'] == 2


def test_cached_value_is_mutation_safe():
    f, calls = _counting_fn()
    result = f(1)
    result['value'] = 999
    assert f(1) == {'value': 2}


def test_ttl_expiry():
    calls = {'n': 0}

    @ttl_cache(ttl=0.05)
    def f():
        calls['n'] += 1
        return calls['n']

    assert f() == 1 and f() == 1
    time.sleep(0.06)
    assert f() == 2


def test_per_function_clear_and_clear_all():
    f, calls = _counting_fn()
    g, g_calls = _counting_fn()
    f(1), g(1)
    f.clear()
    f(1), g(1)
    assert calls['n'] == 2 and g_calls['n'] == 1
    clear_all()
    f(1), g(1)
    assert calls['n'] == 3 and g_calls['n'] == 2


def test_unhashable_args_fall_back_to_repr():
    calls = {'n': 0}

    @ttl_cache(ttl=60)
    def f(items):
        calls['n'] += 1
        return sum(items)

    assert f([1, 2]) == 3
    assert f([1, 2]) == 3
    assert calls['n'] == 1


def test_maxsize_eviction():
    @ttl_cache(ttl=60, maxsize=4)
    def f(x):
        return x

    for i in range(20):
        assert f(i) == i
