"""
Persistence for strategy Q&A threads.

QA_THREADS holds one conversation per user per subject (a generation run or
a simulation); QA_MESSAGES is its ordered transcript. The subject's own data
(code, test results) is never copied here — the context is rebuilt from the
subject's tables on every turn.
"""
import json
import uuid

from db.database import db

SUBJECT_TYPES = ('generation_run', 'simulation')

_MESSAGE_KEYS = ['id', 'role', 'content', 'on_topic', 'suggested_change',
                 'llm_calls', 'created_at']


def get_or_create_thread(user_id: int, subject_type: str, subject_id: str) -> str:
    if subject_type not in SUBJECT_TYPES:
        raise ValueError(f"unknown subject_type {subject_type!r}")
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO QA_THREADS (id, user_id, subject_type, subject_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id, subject_type, subject_id) DO UPDATE
                SET updated_at = CURRENT_TIMESTAMP
            RETURNING id
            """,
            (str(uuid.uuid4()), user_id, subject_type, subject_id),
        )
        thread_id = str(cursor.fetchone()[0])
        conn.commit()
        return thread_id
    finally:
        db.release_connection(conn)


def get_thread(user_id: int, subject_type: str, subject_id: str) -> str | None:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM QA_THREADS WHERE user_id = %s AND subject_type = %s "
            "AND subject_id = %s",
            (user_id, subject_type, subject_id),
        )
        row = cursor.fetchone()
        return str(row[0]) if row else None
    finally:
        db.release_connection(conn)


def append_message(thread_id: str, role: str, content: str,
                   on_topic: bool | None = None,
                   suggested_change: dict | None = None,
                   llm_calls: int = 0) -> dict:
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO QA_MESSAGES
                (thread_id, role, content, on_topic, suggested_change, llm_calls)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, role, content, on_topic, suggested_change, llm_calls, created_at
            """,
            (thread_id, role, content, on_topic,
             json.dumps(suggested_change) if suggested_change else None, llm_calls),
        )
        row = cursor.fetchone()
        cursor.execute(
            "UPDATE QA_THREADS SET updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (thread_id,),
        )
        conn.commit()
        return _message(row)
    finally:
        db.release_connection(conn)


def list_messages(thread_id: str, limit: int | None = None) -> list[dict]:
    """The transcript in order; with `limit`, the LAST `limit` messages."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        if limit is None:
            cursor.execute(
                "SELECT id, role, content, on_topic, suggested_change, llm_calls, created_at "
                "FROM QA_MESSAGES WHERE thread_id = %s ORDER BY id",
                (thread_id,),
            )
        else:
            cursor.execute(
                """
                SELECT * FROM (
                    SELECT id, role, content, on_topic, suggested_change, llm_calls, created_at
                    FROM QA_MESSAGES WHERE thread_id = %s ORDER BY id DESC LIMIT %s
                ) recent ORDER BY id
                """,
                (thread_id, limit),
            )
        return [_message(row) for row in cursor.fetchall()]
    finally:
        db.release_connection(conn)


def _message(row) -> dict:
    message = dict(zip(_MESSAGE_KEYS, row))
    message['suggested_change'] = (
        db.deserialize_json_column(message['suggested_change'])
        if message['suggested_change'] else None)
    return message
