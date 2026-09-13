"""R2.4: concurrent report requests for one hash must not render in parallel."""
import threading
import time


def test_same_hash_renders_are_serialized(monkeypatch):
    from app.routers import simulations as sim

    state = {'active': 0, 'max_active': 0, 'calls': 0}
    guard = threading.Lock()

    def fake_render(simulation_hash, viewer_is_admin):
        with guard:
            state['active'] += 1
            state['calls'] += 1
            state['max_active'] = max(state['max_active'], state['active'])
        time.sleep(0.15)  # simulate an expensive render
        with guard:
            state['active'] -= 1
        return "{}"

    monkeypatch.setattr(sim, '_render_report_json', fake_render)

    threads = [
        threading.Thread(
            target=sim._render_report_json_singleflight, args=('samehash', False))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert state['calls'] == 4  # every request was served
    assert state['max_active'] == 1  # but never two renders at once


def test_different_hashes_can_render_concurrently(monkeypatch):
    from app.routers import simulations as sim

    # Two keys on different stripes must not block each other.
    keys = ['a', 'b', 'c', 'd', 'e']
    stripes = {hash((k, False)) % 32 for k in keys}
    assert len(stripes) > 1, "test needs keys on at least two stripes"

    state = {'active': 0, 'max_active': 0}
    guard = threading.Lock()

    def fake_render(simulation_hash, viewer_is_admin):
        with guard:
            state['active'] += 1
            state['max_active'] = max(state['max_active'], state['active'])
        time.sleep(0.1)
        with guard:
            state['active'] -= 1
        return "{}"

    monkeypatch.setattr(sim, '_render_report_json', fake_render)

    threads = [
        threading.Thread(
            target=sim._render_report_json_singleflight, args=(k, False))
        for k in keys
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    assert state['max_active'] > 1
