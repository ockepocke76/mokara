"""
Few-shot retrieval for strategy generation.

Two sources, no embeddings (per the W5 design):
- The built-in strategies: each carries get_user_prompt_template() — a real
  (natural-language prompt -> verified code) pair.
- Top public validated user strategies from CUSTOM_STRATEGIES, ranked by
  their evaluation excellence score. (No category column exists on the
  table, so ranking is global; the built-ins carry the category signal.)

Also picks the paired-baseline strategy for the test-flight comparison.
"""
import inspect
import logging

from core.strategy import BuyBorrowDieStrategy, TrinityStrategy
from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy

_BUILTINS = {
    'trinity': TrinityStrategy,
    'buy_borrow_die': BuyBorrowDieStrategy,
    'get_rich_stay_rich': GetRichStayRichStrategy,
}

# category -> ordered builtin preference (few-shot AND baseline choice)
_CATEGORY_BUILTINS = {
    'WITHDRAWAL_ONLY': ['trinity', 'buy_borrow_die'],
    'CONTRIBUTION_ONLY': ['get_rich_stay_rich', 'trinity'],
    'HYBRID': ['get_rich_stay_rich', 'trinity'],
}


def builtin_examples(category: str, limit: int = 2) -> list[dict]:
    keys = _CATEGORY_BUILTINS.get(category, ['trinity', 'get_rich_stay_rich'])[:limit]
    examples = []
    for key in keys:
        cls = _BUILTINS[key]
        examples.append({
            'name': cls.__name__,
            'source': 'builtin',
            'prompt': cls.get_user_prompt_template().strip(),
            'code': inspect.getsource(cls),
        })
    return examples


def public_examples(user_id: int, limit: int = 2) -> list[dict]:
    """Top public validated strategies with a leaderboard evaluation."""
    from db.database import db

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cs.strategy_name, cs.code,
                   COALESCE(cs.ai_description, cs.description, '') AS description,
                   se.excellence_score
            FROM CUSTOM_STRATEGIES cs
            JOIN LATERAL (
                SELECT excellence_score
                FROM STRATEGY_EVALUATIONS e
                WHERE e.is_custom = TRUE AND e.custom_strategy_id = cs.id
                ORDER BY e.excellence_score DESC NULLS LAST
                LIMIT 1
            ) se ON TRUE
            WHERE cs.is_published_to_leaderboard = TRUE
              AND cs.deleted_at IS NULL
              AND cs.validation_status = 'validated'
              AND cs.code IS NOT NULL
              AND cs.user_id != %s
            ORDER BY se.excellence_score DESC NULLS LAST
            LIMIT %s
            """,
            (user_id, limit),
        )
        return [
            {'name': row[0], 'source': 'community', 'prompt': row[2] or row[0],
             'code': row[1], 'score': row[3]}
            for row in cursor.fetchall()
        ]
    except Exception:
        logging.exception("public_examples retrieval failed; continuing without")
        return []
    finally:
        db.release_connection(conn)


def baseline_for_category(category: str) -> tuple[str, str, str]:
    """(display name, class name, source code) of the paired-baseline builtin."""
    key = _CATEGORY_BUILTINS.get(category, ['trinity'])[0]
    cls = _BUILTINS[key]
    return key, cls.__name__, inspect.getsource(cls)
