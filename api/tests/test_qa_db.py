import uuid

import pytest

from db import qa
from db.database import db


def _user() -> int:
    return db.get_or_create_user_id(f"qa-db-{uuid.uuid4().hex[:10]}@example.com", "QA DB")


def test_thread_is_unique_per_user_and_subject():
    user_id = _user()
    other = _user()
    first = qa.get_or_create_thread(user_id, 'simulation', 'abc123')
    assert qa.get_or_create_thread(user_id, 'simulation', 'abc123') == first
    assert qa.get_thread(user_id, 'simulation', 'abc123') == first
    assert qa.get_or_create_thread(user_id, 'generation_run', 'abc123') != first
    assert qa.get_or_create_thread(other, 'simulation', 'abc123') != first
    assert qa.get_thread(other, 'generation_run', 'nope') is None


def test_unknown_subject_type_rejected():
    with pytest.raises(ValueError):
        qa.get_or_create_thread(_user(), 'report', 'x')


def test_messages_round_trip_in_order_with_tail_limit():
    thread = qa.get_or_create_thread(_user(), 'generation_run', str(uuid.uuid4()))
    qa.append_message(thread, 'user', 'why no transition?')
    answer = qa.append_message(
        thread, 'assistant', 'The ratio peaked at 4.1 against a 6.0 trigger.',
        on_topic=True, llm_calls=2,
        suggested_change={'summary': 'Lower the trigger',
                          'refine_feedback': 'Lower transition_ratio default to 4.0'})
    assert answer['on_topic'] is True
    assert answer['suggested_change']['summary'] == 'Lower the trigger'
    qa.append_message(thread, 'user', 'and the capital of France?')
    qa.append_message(thread, 'assistant', 'Only questions about this strategy.',
                      on_topic=False)

    messages = qa.list_messages(thread)
    assert [m['role'] for m in messages] == ['user', 'assistant', 'user', 'assistant']
    assert messages[0]['on_topic'] is None and messages[0]['suggested_change'] is None
    assert messages[1]['llm_calls'] == 2
    assert messages[3]['on_topic'] is False

    tail = qa.list_messages(thread, limit=2)
    assert [m['content'] for m in tail] == ['and the capital of France?',
                                            'Only questions about this strategy.']
