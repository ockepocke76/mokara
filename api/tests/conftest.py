"""Shared test fixtures.

The API tests mint a fresh @example.com user per run; each one is
auto-approved into the beta allowlist and permanently consumes a
max_beta_users slot. Left alone, repeated runs fill the quota and every
generation test starts failing with "Beta access is full" — so drop the
suite's own users before and after each session.
"""
import logging

import pytest


def _purge_test_users() -> None:
    try:
        from db.database import db

        conn = db.get_connection()
        try:
            cursor = db._get_cursor(conn)
            cursor.execute(
                "DELETE FROM allowed_users WHERE email LIKE '%@example.com'")
            conn.commit()
            if cursor.rowcount:
                logging.info("conftest: removed %d @example.com beta users",
                             cursor.rowcount)
        finally:
            db.release_connection(conn)
    except Exception:
        logging.exception("conftest: test-user purge failed; continuing")


@pytest.fixture(scope="session", autouse=True)
def clean_beta_allowlist():
    _purge_test_users()
    yield
    _purge_test_users()
