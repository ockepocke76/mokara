"""Job-queue correctness: heartbeat-based recovery and owner fences.

CODE_REVIEW R2.1: stale-job recovery used a global 900s wall-clock cutoff
(ignoring each job's own timeout_seconds), so a legitimately long simulation
was re-queued mid-run and executed concurrently — and the evicted worker's
complete/fail overwrote the reclaimer's state because terminal transitions
had no ownership fence.
"""
import uuid

import pytest

from db.database import db


def _forge(job_id, **cols):
    """Directly set timestamp/int columns on a job row for test scenarios."""
    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        sets = ", ".join(
            f"{k} = CURRENT_TIMESTAMP - make_interval(secs => %({k})s)"
            if k.endswith('_at') else f"{k} = %({k})s"
            for k in cols
        )
        cur.execute(
            f"UPDATE BACKGROUND_JOBS SET {sets} WHERE id = %(id)s",
            {**cols, 'id': job_id})
        conn.commit()
    finally:
        db.release_connection(conn)


def _job_row(job_id):
    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        cur.execute(
            "SELECT status, worker_id, error_message FROM BACKGROUND_JOBS WHERE id = %s",
            (job_id,))
        status, worker_id, error = cur.fetchone()
        return {'status': status, 'worker_id': worker_id, 'error': error}
    finally:
        db.release_connection(conn)


@pytest.fixture()
def job_id():
    # Inserted directly with a future scheduled_at so a dev worker polling
    # this DB can never claim it out from under the test (_claim ignores
    # scheduled_at on purpose).
    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        cur.execute("""
            INSERT INTO BACKGROUND_JOBS
                (job_type, payload, idempotency_key, timeout_seconds, scheduled_at)
            VALUES ('pdf_generation', '{"test": true}'::jsonb, %s, 1800,
                    CURRENT_TIMESTAMP + interval '1 hour')
            RETURNING id
        """, (f"r2-test-{uuid.uuid4().hex}",))
        jid = str(cur.fetchone()[0])
        conn.commit()
    finally:
        db.release_connection(conn)
    yield jid
    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        cur.execute("DELETE FROM BACKGROUND_JOBS WHERE id = %s", (jid,))
        conn.commit()
    finally:
        db.release_connection(conn)


def _claim(worker, job_id):
    """Claim THIS job for the given worker (deterministic against other
    pending rows a shared dev DB may hold); mirrors fetch_and_lock_job's
    claim update, including the heartbeat stamp."""
    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        cur.execute("""
            UPDATE BACKGROUND_JOBS
            SET status = 'PROCESSING', started_at = CURRENT_TIMESTAMP,
                heartbeat_at = CURRENT_TIMESTAMP, worker_id = %s
            WHERE id = %s AND status = 'PENDING'
            RETURNING id
        """, (worker, job_id))
        row = cur.fetchone()
        conn.commit()
        return row is not None
    finally:
        db.release_connection(conn)


def test_live_heartbeat_prevents_reset_even_for_old_jobs(job_id):
    assert _claim('wA', job_id)
    # Long-running job: started 20 min ago, but the worker beat 10s ago.
    _forge(job_id, started_at=1200, heartbeat_at=10)
    db.reset_stale_jobs(heartbeat_timeout_seconds=300)
    assert _job_row(job_id)['status'] == 'PROCESSING'


def test_silent_worker_gets_job_requeued_and_fenced_out(job_id):
    assert _claim('wA', job_id)
    # Worker went silent 10 minutes ago.
    _forge(job_id, started_at=1200, heartbeat_at=600)
    assert db.reset_stale_jobs(heartbeat_timeout_seconds=300) >= 1
    row = _job_row(job_id)
    assert row['status'] == 'PENDING' and row['worker_id'] is None

    # A second worker reclaims it.
    assert _claim('wB', job_id)

    # The evicted worker's late reports are all fenced out...
    assert db.complete_job(job_id, {'zombie': True}, worker_id='wA') is False
    assert db.fail_job(job_id, 'zombie error', worker_id='wA') is False
    assert db.retry_job(job_id, 'zombie retry', 0, worker_id='wA') is False
    assert db.heartbeat_job(job_id, 'wA') is False
    row = _job_row(job_id)
    assert row['status'] == 'PROCESSING' and row['worker_id'] == 'wB'

    # ...while the current owner's completion lands.
    assert db.complete_job(job_id, {'ok': True}, worker_id='wB') is True
    assert _job_row(job_id)['status'] == 'COMPLETED'


def test_per_job_timeout_fails_runaway_but_live_jobs(job_id):
    assert _claim('wA', job_id)
    # Shorten this job's own budget, make it look 2 minutes old with a
    # fresh heartbeat: alive but over budget.
    _forge(job_id, timeout_seconds=60, started_at=120, heartbeat_at=5)
    db.reset_stale_jobs(heartbeat_timeout_seconds=300)
    assert _job_row(job_id)['status'] == 'PROCESSING'
    assert db.fail_timed_out_jobs(heartbeat_timeout_seconds=300) >= 1
    row = _job_row(job_id)
    assert row['status'] == 'FAILED'
    assert 'timeout' in (row['error'] or '')
    # The zombie's eventual completion must not resurrect it.
    assert db.complete_job(job_id, {'late': True}, worker_id='wA') is False
    assert _job_row(job_id)['status'] == 'FAILED'


def test_never_heartbeated_job_gets_its_full_timeout_before_reclaim(job_id):
    """Rolling-deploy case: a pre-heartbeat worker binary never beats.
    Such jobs must get their own timeout_seconds (1800 here), not the
    5-minute heartbeat window, before being presumed dead."""
    assert _claim('old_worker_v1', job_id)
    # 10 minutes in, no heartbeat ever — within its 1800s budget.
    _forge(job_id, started_at=600)
    _null_heartbeat(job_id)
    db.reset_stale_jobs(heartbeat_timeout_seconds=300)
    assert _job_row(job_id)['status'] == 'PROCESSING'
    # 31 minutes in — over budget, now reclaimable.
    _forge(job_id, started_at=1860)
    _null_heartbeat(job_id)
    assert db.reset_stale_jobs(heartbeat_timeout_seconds=300) >= 1
    assert _job_row(job_id)['status'] == 'PENDING'


def _null_heartbeat(job_id):
    conn = db.get_connection()
    try:
        cur = db._get_cursor(conn)
        cur.execute("UPDATE BACKGROUND_JOBS SET heartbeat_at = NULL WHERE id = %s", (job_id,))
        conn.commit()
    finally:
        db.release_connection(conn)


def test_within_budget_long_job_is_not_timed_out(job_id):
    assert _claim('wA', job_id)
    # 20 minutes into a 30-minute budget, heartbeating.
    _forge(job_id, started_at=1200, heartbeat_at=5)
    db.fail_timed_out_jobs(heartbeat_timeout_seconds=300)
    assert _job_row(job_id)['status'] == 'PROCESSING'


def test_progress_updates_are_fenced_and_beat(job_id):
    assert _claim('wA', job_id)
    _forge(job_id, heartbeat_at=600)
    db.update_job_progress(job_id, 0.5, 'halfway', worker_id='wA')
    job_after = db.get_job_by_id(job_id)
    payload = job_after['payload']
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    assert payload.get('progress_value') == 0.5
    assert payload.get('progress_message') == 'halfway'
    # The progress write refreshed the heartbeat: no longer stale.
    db.reset_stale_jobs(heartbeat_timeout_seconds=300)
    assert _job_row(job_id)['status'] == 'PROCESSING'

    # A non-owner's progress write is ignored.
    db.update_job_progress(job_id, 0.9, 'zombie progress', worker_id='wZ')
    job_after = db.get_job_by_id(job_id)
    payload = job_after['payload']
    if isinstance(payload, str):
        import json
        payload = json.loads(payload)
    assert payload.get('progress_value') == 0.5
    db.complete_job(job_id, {}, worker_id='wA')


def test_simulation_progress_reaches_the_callback():
    """R2.2: run_and_save_simulation reports through progress_callback."""
    import inspect

    from background_tasks import run_and_save_simulation

    sig = inspect.signature(run_and_save_simulation)
    assert 'progress_callback' in sig.parameters
