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


# Tables with a NOT NULL/NO ACTION user_id FK to users.id — must be cleared
# before the user row itself can go. background_jobs uses ON DELETE SET NULL
# so it doesn't need to be listed here.
_USER_OWNED_TABLES = [
    'user_settings', 'user_simulation_history', 'custom_strategies',
    'strategy_evaluations', 'subscription_history', 'ai_credit_usage',
    'logs', 'simulations_old', 'user_hidden_items', 'strategy_generation_runs',
]


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
            cursor.execute(
                "DELETE FROM allowed_users WHERE email LIKE '%@example.com'")
            if cursor.rowcount:
                logging.info("conftest: removed %d @example.com beta users",
                             cursor.rowcount)

            # Test users accumulate in `users` itself too (custom strategies,
            # evaluations, etc. all hang off user_id). Clear those out the
            # same way the one-off 2026-09-18 cleanup did: unpublish any
            # public/leaderboard strategies first (the DB trigger refuses to
            # delete those), then delete dependents, then the users. id 0/1
            # (system account, real admin) are never @example.com but are
            # excluded explicitly as a belt-and-suspenders guard.
            cursor.execute(
                "SELECT id FROM users WHERE email LIKE '%@example.com' AND id NOT IN (0, 1)")
            test_user_ids = [row[0] for row in cursor.fetchall()]
            if test_user_ids:
                cursor.execute(
                    "UPDATE custom_strategies SET is_public = false, is_published_to_leaderboard = false "
                    "WHERE user_id = ANY(%s) AND (is_public OR is_published_to_leaderboard)",
                    (test_user_ids,))
                for table in _USER_OWNED_TABLES:
                    cursor.execute(
                        f"DELETE FROM {table} WHERE user_id = ANY(%s)", (test_user_ids,))
                cursor.execute(
                    "DELETE FROM users WHERE id = ANY(%s)", (test_user_ids,))
                logging.info("conftest: removed %d @example.com test users",
                             len(test_user_ids))

            conn.commit()
        finally:
            db.release_connection(conn)
    except Exception:
        logging.exception("conftest: test-user purge failed; continuing")


@pytest.fixture(scope="session", autouse=True)
def clean_beta_allowlist():
    _purge_test_users()
    yield
    _purge_test_users()
