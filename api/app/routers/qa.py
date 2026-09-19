"""
Q&A about a strategy's observed behavior — a designer build (generation
run) or a finished simulation. Sync handlers: the answer is one strong-tier
model call, returned when it lands.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.deps import require_user, verify_internal_secret
from app.qa import service

router = APIRouter(dependencies=[Depends(verify_internal_secret)])


class AskBody(BaseModel):
    subject_type: str = Field(pattern='^(generation_run|simulation)$')
    subject_id: str = Field(min_length=1, max_length=128)
    question: str = Field(min_length=1, max_length=service.MAX_QUESTION_CHARS)


def _stringify(message: dict) -> dict:
    out = dict(message)
    if hasattr(out.get('created_at'), 'isoformat'):
        out['created_at'] = out['created_at'].isoformat()
    return out


@router.get("/qa/thread")
def get_thread(subject_type: str = Query(pattern='^(generation_run|simulation)$'),
               subject_id: str = Query(min_length=1, max_length=128),
               user: dict = Depends(require_user)) -> dict:
    try:
        thread = service.get_thread(user, subject_type, subject_id)
    except service.QAError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    thread['messages'] = [_stringify(m) for m in thread['messages']]
    return thread


@router.post("/qa/messages")
def ask(body: AskBody, user: dict = Depends(require_user)) -> dict:
    try:
        result = service.ask(user, body.subject_type, body.subject_id, body.question)
    except service.QAError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    result['user'] = _stringify(result['user'])
    result['assistant'] = _stringify(result['assistant'])
    return result
