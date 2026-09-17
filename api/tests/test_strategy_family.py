"""
Strategy-level family tree (clone lineage across users): visible = public,
built-in, or the viewer's own; everything else appears only as per-node
hidden-fork counts. Runs against the real local Postgres.
"""
import uuid

from db.database import db

CODE = '''
class FamilyStrategy(BaseStrategy):
    @property
    def parameters(self):
        return {'withdrawal_rate': {'description': 'Annual withdrawal rate',
                                    'default': 0.04}}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''.strip()


def _new_user() -> int:
    return db.get_or_create_user_id(
        f"family-{uuid.uuid4().hex[:10]}@example.com", "Family Test")


def _create(user_id, name, public=False):
    sid = db.save_custom_strategy(
        user_id=user_id, strategy_name=name, class_name="FamilyStrategy",
        description='', ai_description='', code=CODE,
        parameters_json={}, validation_status='validated')
    assert sid
    if public:
        _set_public(sid)
    return sid


def _set_public(sid):
    # The product's real "make public" action: publish to the leaderboard.
    # (is_public is only ever set for built-ins.)
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE CUSTOM_STRATEGIES SET is_published_to_leaderboard = TRUE "
            "WHERE id = %s", (sid,))
        conn.commit()
    finally:
        db.release_connection(conn)


def _clone(user_id, parent_id):
    from services.strategy_clone import clone_strategy

    res = clone_strategy(strategy_id=parent_id, user_id=user_id, db=db)
    assert res['success'], res
    return res['strategy_id']


def test_family_hides_private_strategies_as_counts():
    owner = _new_user()
    forker = _new_user()
    viewer = _new_user()
    root = _create(owner, "Family Root", public=True)
    private_clone = _clone(forker, root)  # stays private

    # A third party sees the root only, with the private fork counted
    rows = db.get_strategy_family(root, viewer)
    assert [r['id'] for r in rows] == [root]
    assert rows[0]['hidden_forks'] == 1
    assert rows[0]['owner_name'] != ''  # display name or 'anonymous'

    # The forker sees their own private clone, flagged private
    rows = db.get_strategy_family(root, forker)
    assert [r['id'] for r in rows] == [root, private_clone]
    clone_row = rows[1]
    assert clone_row['is_private'] is True and clone_row['is_own'] is True
    assert rows[0]['hidden_forks'] == 0  # nothing hidden from the forker

    # Publishing the clone makes it visible to everyone, and it stops being
    # labeled private (published strategies must never claim "only you see it")
    _set_public(private_clone)
    rows = db.get_strategy_family(root, viewer)
    assert [r['id'] for r in rows] == [root, private_clone]
    assert rows[0]['hidden_forks'] == 0
    assert rows[1]['is_private'] is False


def test_family_roots_at_highest_visible_ancestor():
    owner = _new_user()
    forker = _new_user()
    root = _create(owner, "Deep Root", public=True)
    mid = _clone(forker, root)
    # Materialize the clone (pure clones can't be re-cloned), then publish it
    assert db.save_custom_strategy(
        user_id=forker, strategy_name="Deep Root", class_name="FamilyStrategy",
        description='', ai_description='',
        code=CODE.replace("0.04", "0.05"), parameters_json={},
        validation_status='validated', strategy_id=mid) == mid
    _set_public(mid)
    leaf = _clone(forker, mid)  # private leaf, forker's own

    rows = db.get_strategy_family(leaf, forker)
    assert [r['id'] for r in rows] == [root, mid, leaf]
    assert rows[0]['parent_strategy_id'] is None or \
        rows[0]['parent_strategy_id'] not in [r['id'] for r in rows]
    assert rows[1]['parent_strategy_id'] == root
    assert rows[2]['parent_strategy_id'] == mid

    # Owner-name privacy: only display names ever ship, never emails
    assert all('@' not in (r['owner_name'] or '') for r in rows)


def test_family_prunes_deleted_leaves_but_passes_through():
    owner = _new_user()
    root = _create(owner, "Trash Family Root", public=True)
    dead = _clone(owner, root)
    assert db.soft_delete_custom_strategy(dead, owner)

    # A deleted leaf is pruned entirely — neither drawn nor "hidden"
    rows = db.get_strategy_family(root, owner)
    assert [r['id'] for r in rows] == [root]
    assert rows[0]['hidden_forks'] == 0

    # ...but a deleted INTERMEDIATE stays as flagged pass-through so its live
    # descendants are never amputated (the Phase-1 principle).
    forker = _new_user()
    mid = _clone(forker, root)
    assert db.save_custom_strategy(
        user_id=forker, strategy_name="Trash Family Root",
        class_name="FamilyStrategy", description='', ai_description='',
        code=CODE.replace("0.04", "0.06"), parameters_json={},
        validation_status='validated', strategy_id=mid) == mid
    _set_public(mid)
    leaf = _clone(forker, mid)
    _set_public(leaf)
    assert db.soft_delete_custom_strategy(mid, forker)

    rows = db.get_strategy_family(root, owner)
    assert [r['id'] for r in rows] == [root, mid, leaf]
    assert rows[1]['strategy_deleted'] is True
    assert rows[2]['strategy_deleted'] is False


def test_family_builtin_nodes_never_expose_hidden_counts():
    """A builtin root would otherwise tally private clones platform-wide —
    a number no other surface exposes."""
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM CUSTOM_STRATEGIES WHERE user_id = 0 "
                       "AND deleted_at IS NULL LIMIT 1")
        row = cursor.fetchone()
    finally:
        db.release_connection(conn)
    if not row:
        import pytest
        pytest.skip("no builtin rows synced in this database")
    builtin_id = row[0]

    user_id = _new_user()
    clone_id = _clone(user_id, builtin_id)  # a private clone exists now
    rows = db.get_strategy_family(clone_id, user_id)
    builtin_node = next(r for r in rows if r['id'] == builtin_id)
    assert builtin_node['is_builtin'] is True
    assert builtin_node['hidden_forks'] == 0
    assert builtin_node['owner_name'] == 'built-in'
