"""Shared test fixtures.

The API tests mint a fresh @example.com user per run; each one is
auto-approved into the beta allowlist and permanently consumes a
max_beta_users slot. Left alone, repeated runs fill the quota and every
generation test starts failing with "Beta access is full" — so drop the
suite's own users before and after each session.
"""
import logging
import os

import pytest


def _purge_test_users() -> None:
    # Only ever touch the local dev/CI database (or an explicit *_test DB) —
    # never whatever a stray .env might point at.
    from dotenv import load_dotenv

    load_dotenv()
    db_name = os.environ.get('POSTGRES_DB', '')
    if db_name != 'btc_simulator_local' and not db_name.endswith('_test'):
        logging.warning(
            "conftest: skipping test-user purge on non-local database %r", db_name)
        return
    try:
        from db.database import db

        conn = db.get_connection()
        try:
            cursor = db._get_cursor(conn)
            # Independent of the users purge below: an allowlist entry can
            # exist with no matching `users` row yet (approved but never
            # signed up), so this can't be folded into delete_users_by_id.
            cursor.execute(
                "DELETE FROM allowed_users WHERE email LIKE '%@example.com'")
            if cursor.rowcount:
                logging.info("conftest: removed %d @example.com beta users",
                             cursor.rowcount)
            conn.commit()

            # Test users accumulate in `users` itself too (custom strategies,
            # evaluations, etc. all hang off user_id). id 0/1 (system
            # account, real admin) are never @example.com but are excluded
            # explicitly as a belt-and-suspenders guard.
            cursor.execute(
                "SELECT id FROM users WHERE email LIKE '%@example.com' AND id NOT IN (0, 1)")
            test_user_ids = [row[0] for row in cursor.fetchall()]
        finally:
            db.release_connection(conn)

        deleted = db.delete_users_by_id(test_user_ids)
        if deleted:
            logging.info("conftest: removed %d @example.com test users", deleted)
        elif test_user_ids:
            # delete_users_by_id() returns 0 for both "nothing to do" and "it
            # failed" (logging its own error) — test_user_ids being non-empty
            # here means it's the latter.
            logging.warning(
                "conftest: expected to purge %d @example.com test users but "
                "0 were deleted; see the delete_users_by_id error logged above",
                len(test_user_ids))
    except Exception:
        logging.exception("conftest: test-user purge failed; continuing")


@pytest.fixture(scope="session", autouse=True)
def clean_beta_allowlist():
    _purge_test_users()
    yield
    _purge_test_users()
