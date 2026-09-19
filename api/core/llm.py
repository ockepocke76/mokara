"""
The one place that talks to Gemini.

Every LLM call in the app — designer graph (create/evolve), strategy Q&A,
simulation-report analysis — goes through call_gemini_safe, and every call
is written to LLM_USAGE from here (tokens incl. thinking + cached, cost at
the day's list price, latency), so cost tracking cannot be bypassed by a
caller that forgets to log. Callers say WHAT the call belongs to by
wrapping their work in llm_scope(); the scope rides a ContextVar so nothing
threads through function signatures. No scope → recorded as 'unknown'
(the admin page shows those so they get a scope, not lost).
"""
import contextvars
import logging
import os
import time
from contextlib import contextmanager
from typing import Optional

from google import genai
from config import CONFIG

# Model tiers: 'fast' for spec/clarify/review-style calls and report analysis,
# 'strong' for code generation and analysis. Override with GEMINI_MODEL_FAST /
# GEMINI_MODEL_STRONG (see .env.example for the why behind the defaults).
DEFAULT_MODELS = {'strong': 'gemini-3.8-flash', 'fast': 'gemini-3.5-flash-lite'}


def model_for_tier(tier: str) -> str:
    tier = tier if tier in DEFAULT_MODELS else 'fast'
    return os.environ.get(f'GEMINI_MODEL_{tier.upper()}', DEFAULT_MODELS[tier])


# {'operation', 'user_id', 'ref_id', 'step'} for the operation in progress.
_llm_scope: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar('llm_scope', default=None)


@contextmanager
def llm_scope(operation: Optional[str] = None, user_id: Optional[int] = None,
              ref_id: Optional[str] = None, step: Optional[str] = None):
    """Attribute every LLM call inside the block to one user-facing operation
    (strategy_create, strategy_evolve, strategy_qa, report_analysis, ...).
    ref_id groups the calls of one operation (run id, message id, sim hash);
    nested scopes inherit what they don't set — the graph uses that to add
    the node name as `step` without restating the run."""
    parent = _llm_scope.get() or {}
    scope = {
        'operation': operation or parent.get('operation'),
        'user_id': user_id if user_id is not None else parent.get('user_id'),
        'ref_id': ref_id if ref_id is not None else parent.get('ref_id'),
        'step': step if step is not None else parent.get('step'),
    }
    token = _llm_scope.set(scope)
    try:
        yield scope
    finally:
        _llm_scope.reset(token)


def current_llm_scope() -> dict:
    return dict(_llm_scope.get() or {})


# Initialize the global client
# Note: Google GenAI SDK automatically looks for GEMINI_API_KEY or GOOGLE_API_KEY environment variables
# but we provide it explicitly from our CONFIG if present.
_client = None

def _get_client(api_key=None):
    global _client
    if api_key:
        return genai.Client(api_key=api_key)

    if _client is None:
        # Priority: CONFIG -> Environment Variables
        env_key = CONFIG.get('google_api_key') or CONFIG.get('api_key') or os.environ.get('GOOGLE_API_KEY') or os.environ.get('GEMINI_API_KEY')

        if env_key:
            _client = genai.Client(api_key=env_key)
        else:
            # Fallback to SDK automatic environment detection (looks for GOOGLE_API_KEY)
            logging.info("No explicit Gemini API key found in CONFIG or environment. Falling back to SDK default detection.")
            _client = genai.Client()
    return _client


def _usage_from_response(response) -> dict:
    """Token counts as Gemini reports them. prompt_tokens includes the cached
    part; thinking_tokens is billed as output — both matter for cost."""
    meta = getattr(response, 'usage_metadata', None)
    if meta is None:
        return {}
    return {
        'prompt_tokens': getattr(meta, 'prompt_token_count', 0) or 0,
        'cached_tokens': getattr(meta, 'cached_content_token_count', 0) or 0,
        'completion_tokens': getattr(meta, 'candidates_token_count', 0) or 0,
        'thinking_tokens': getattr(meta, 'thoughts_token_count', 0) or 0,
        'total_tokens': getattr(meta, 'total_token_count', 0) or 0,
    }


def _record(model_name: str, tier: Optional[str], usage: dict, latency_ms: int,
            error: Optional[str]) -> None:
    """Persist the call. Never raises: a logging failure must not turn a
    successful generation into a user-facing error."""
    try:
        from core.llm_pricing import estimate_cost_usd
        from db import llm_usage

        scope = current_llm_scope()
        tokens = {k: usage.get(k, 0) for k in
                  ('prompt_tokens', 'cached_tokens', 'completion_tokens', 'thinking_tokens')}
        llm_usage.record_call(
            operation=scope.get('operation') or 'unknown',
            user_id=scope.get('user_id'),
            ref_id=scope.get('ref_id'),
            step=scope.get('step'),
            tier=tier,
            model=model_name,
            cost_usd=estimate_cost_usd(model_name, **tokens),
            latency_ms=latency_ms,
            ok=error is None,
            error=error,
            **tokens,
        )
    except Exception:
        logging.exception("LLM usage logging failed (call itself unaffected)")


def call_gemini_safe(model_name: str, prompt: str, generation_config=None, api_key=None,
                     tier: Optional[str] = None) -> tuple[str | None, str | None, dict | None]:
    """
    Safely calls the Gemini API with centralized error handling.

    Args:
        model_name (str): The model name (e.g., 'gemini-1.5-flash').
        prompt (str): The text prompt.
        generation_config (dict, optional): Generation parameters.
        tier (str, optional): 'fast' / 'strong' — recorded with the call.

    Returns:
        tuple: (response_text, error_message, usage_metadata)
            - response_text: The generated text if successful, else None.
            - error_message: A user-friendly error message if failed, else None.
            - usage_metadata: A dict with token counts if available, else None.
    """
    started = time.monotonic()
    try:
        client = _get_client(api_key)

        # New SDK uses 'contents' instead of 'prompt' and 'model' instead of positional argument
        # config can be a dict
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=generation_config
        )

        usage = _usage_from_response(response)
        if not usage:
            logging.warning("Could not extract usage metadata from Gemini response")
        _record(model_name, tier, usage, int((time.monotonic() - started) * 1000), None)

        return response.text, None, usage

    except Exception as e:
        err_msg = str(e)
        logging.error(f"Gemini API call failed: {e}", exc_info=True)
        _record(model_name, tier, {}, int((time.monotonic() - started) * 1000), err_msg[:500])

        # quota/429 check
        if "429" in err_msg or "quota" in err_msg.lower() or "resourceexhausted" in err_msg.lower():
            return None, "We are experiencing high load at the moment and cannot handle your request. Please try again later.", None

        # General error
        return None, f"An unexpected error occurred while processing your request: {err_msg}", None
