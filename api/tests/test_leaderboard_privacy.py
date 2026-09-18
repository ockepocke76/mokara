"""
Leaderboard rows must never carry user emails: the author field is the
display name or 'anonymous' (same rule as the strategy family tree), and
the raw email column stays out of the payload entirely.
"""
import uuid

from db.database import db
from utils.strategy_utils import calculate_strategy_hash

CODE = '''
class LeaderStrategy(BaseStrategy):
    @property
    def parameters(self):
        return {'withdrawal_rate': {'description': 'Annual withdrawal rate',
                                    'default': 0.04}}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''.strip()


def _published_strategy_without_display_name():
    email = f"leader-{uuid.uuid4().hex[:10]}@example.com"
    user_id = db.get_or_create_user_id(email, "Leader Test")
    sid = db.save_custom_strategy(
        user_id=user_id, strategy_name=f"Leader {uuid.uuid4().hex[:6]}",
        class_name="LeaderStrategy", description='', ai_description='',
        code=CODE, parameters_json={}, validation_status='validated')
    assert sid
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE USERS SET display_name = NULL WHERE id = %s",
                       (user_id,))
        cursor.execute(
            "UPDATE CUSTOM_STRATEGIES SET is_published_to_leaderboard = TRUE "
            "WHERE id = %s", (sid,))
        conn.commit()
    finally:
        db.release_connection(conn)
    row = db.get_custom_strategy(sid)
    sha = row['git_commit_sha'] or calculate_strategy_hash(CODE, {})
    assert db.save_strategy_evaluation({
        'strategy_name': row['strategy_name'], 'git_commit_sha': sha,
        'user_id': user_id, 'is_custom': True, 'custom_strategy_id': sid,
        'strategy_category': 'WITHDRAWAL_ONLY', 'excellence_score': 99.9,
        'scenario_results_json': '[]'})
    return email, sid


def test_leaderboard_author_never_falls_back_to_email():
    email, sid = _published_strategy_without_display_name()

    rows = db.get_leaderboard_with_profile(
        profile_key='balanced_withdrawal', category='WITHDRAWAL_ONLY',
        limit=1000)
    mine = next(r for r in rows if r.get('custom_strategy_id') == sid)
    assert mine['user_name'] == 'anonymous'
    assert 'user_email' not in mine
    assert email not in str(mine.values())

    # The plain query too (limit dodges its TTL-cached default arguments)
    rows = db.get_leaderboard(category='WITHDRAWAL_ONLY', limit=999)
    mine = next(r for r in rows if r.get('custom_strategy_id') == sid)
    assert mine['user_name'] == 'anonymous'
    assert 'user_email' not in mine

    # Built-in rows keep a NULL author (the API shows them as community/
    # built-in, never 'anonymous')
    assert all(r['user_name'] is None for r in rows if not r['is_custom'])
