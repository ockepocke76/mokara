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

    # Keys on distinct stripes must not block each other. Stripe assignment
    # is hash-salted per process, so pick keys that land on different
    # stripes at runtime.
    keys, seen = [], set()
    for i in range(1000):
        k = f"h{i}"
        stripe = hash((k, False)) % 32
        if stripe not in seen:
            seen.add(stripe)
            keys.append(k)
        if len(keys) == 5:
            break
    assert len(keys) == 5

    state = {'active': 0, 'max_active': 0}
    guard = threading.Lock()

    barrier = threading.Barrier(len(keys), timeout=5)

    def fake_render(simulation_hash, viewer_is_admin):
        with guard:
            state['active'] += 1
            state['max_active'] = max(state['max_active'], state['active'])
        # Rendezvous: every thread must be inside its render at once, so the
        # concurrency assertion cannot flake on a slow/loaded runner. Threads
        # serialized by an (unexpected) shared lock would deadlock the
        # barrier and time out instead.
        try:
            barrier.wait()
        except threading.BrokenBarrierError:
            pass
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
