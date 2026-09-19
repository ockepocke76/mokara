"""
Ask a question about a strategy build or a finished simulation.

Flow per question: resolve the subject (ownership + context) -> triage
(fast tier; off-topic gets a fixed refusal and costs no credit) -> answer
(strong tier) -> persist both turns -> charge one AI credit.
"""
import logging

from app.agents.llm import get_llm_call, parse_json_response
from app.qa import prompts
from app.qa.context import QAContext, from_generation_run, from_simulation
from db import qa as qa_db
from db import strategy_generation as sg
from db.database import db

HISTORY_TURNS = 10
MAX_QUESTION_CHARS = 2000


class QAError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class Subject:
    def __init__(self, subject_type: str, subject_id: str, build_context, can_refine: bool):
        self.subject_type = subject_type
        self.subject_id = subject_id
        self._build_context = build_context
        self.can_refine = can_refine

    def context(self) -> QAContext:
        context = self._build_context()
        if context is None:
            raise QAError(409, "This strategy has no test results to talk about yet")
        return context


def resolve_subject(user: dict, subject_type: str, subject_id: str) -> Subject:
    """Ownership gate + a lazy context builder for the subject."""
    if subject_type == 'generation_run':
        run = sg.get_run(subject_id)
        if not run or run['user_id'] != user['id']:
            raise QAError(404, "Strategy build not found")
        return Subject(subject_type, run['id'],
                       lambda: from_generation_run(run, sg.list_events(run['id'])),
                       can_refine=(run['status'] == 'needs_input'))
    if subject_type == 'simulation':
        from app.access import require_simulation_view
        require_simulation_view(subject_id, user)  # raises 404 when hidden
        return Subject(subject_type, subject_id,
                       lambda: _simulation_context(subject_id), can_refine=False)
    raise QAError(422, f"Unknown subject type {subject_type!r}")


def _simulation_context(simulation_hash: str) -> QAContext | None:
    from db.regeneration_db import _load_dataframe_from_db

    params, stats, results_id = db.get_simulation_details(simulation_hash)
    if not params or not stats:
        return None
    conn = db.get_connection()
    try:
        sampled = _load_dataframe_from_db(conn, results_id, 'sampled_paths')
    finally:
        db.release_connection(conn)
    return from_simulation(simulation_hash, params, stats, sampled)


def get_thread(user: dict, subject_type: str, subject_id: str) -> dict:
    subject = resolve_subject(user, subject_type, subject_id)
    thread_id = qa_db.get_thread(user['id'], subject.subject_type, subject.subject_id)
    messages = qa_db.list_messages(thread_id) if thread_id else []
    return {'thread_id': thread_id, 'messages': messages,
            'can_refine': subject.can_refine}


def ask(user: dict, subject_type: str, subject_id: str, question: str,
        llm_call=None) -> dict:
    from core.limits import LimitEnforcer

    question = (question or '').strip()
    if not question:
        raise QAError(422, "Ask a question")
    if len(question) > MAX_QUESTION_CHARS:
        raise QAError(422, f"Keep the question under {MAX_QUESTION_CHARS} characters")

    subject = resolve_subject(user, subject_type, subject_id)
    limiter = LimitEnforcer(db)
    allowed, msg, _usage = limiter.check_ai_credits(user['id'])
    if not allowed:
        raise QAError(429, msg)
    context = subject.context()
    llm_call = llm_call or get_llm_call()

    thread_id = qa_db.get_or_create_thread(user['id'], subject.subject_type, subject.subject_id)
    history = qa_db.list_messages(thread_id, limit=HISTORY_TURNS)
    user_message = qa_db.append_message(thread_id, 'user', question)

    triage = _json(llm_call(prompts.triage_prompt(context, question), tier='fast', json_mode=True))
    if not triage.get('on_topic'):
        assistant = qa_db.append_message(thread_id, 'assistant', prompts.REFUSAL,
                                         on_topic=False, llm_calls=1)
        return _result(thread_id, user_message, assistant, subject)

    answer = _json(llm_call(prompts.answer_prompt(context, history, question),
                            tier='strong', json_mode=True))
    answer_md = str(answer.get('answer_md') or '').strip()
    if not answer_md:
        raise QAError(502, "The model returned an empty answer — try again")
    assistant = qa_db.append_message(
        thread_id, 'assistant', answer_md, on_topic=True, llm_calls=2,
        suggested_change=_suggested_change(answer.get('suggested_change')))
    try:
        limiter.increment_ai_credits(user['id'])
    except Exception:
        logging.exception("qa: failed to charge AI credit for user %s", user['id'])
    return _result(thread_id, user_message, assistant, subject)


def _json(text: str) -> dict:
    try:
        return parse_json_response(text)
    except ValueError as e:
        raise QAError(502, f"The model returned an unreadable response: {e}") from e


def _suggested_change(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    summary = str(value.get('summary') or '').strip()
    feedback = str(value.get('refine_feedback') or '').strip()
    if not feedback:
        return None
    return {'summary': summary or feedback[:80], 'refine_feedback': feedback}


def _result(thread_id: str, user_message: dict, assistant: dict, subject: Subject) -> dict:
    return {'thread_id': thread_id, 'user': user_message, 'assistant': assistant,
            'can_refine': subject.can_refine}
