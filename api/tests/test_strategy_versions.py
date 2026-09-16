"""
V39 strategy version DAG: every code-changing save appends a version node,
heads move like branch refs, clones share nodes, revert is append-only, and
legacy rows are backfilled from their evolution_history snapshots.
Runs against the real local Postgres like the rest of the suite.
"""
import json
import uuid

from db.database import db
from services.version_backfill import backfill_strategy_versions

CODE_V1 = '''
class VersionedStrategy(BaseStrategy):
    @property
    def parameters(self):
        return {'withdrawal_rate': {'description': 'Annual withdrawal rate',
                                    'default': 0.04}}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''.strip()

CODE_V2 = CODE_V1.replace("'default': 0.04", "'default': 0.05")
CODE_V3 = CODE_V1.replace("'default': 0.04", "'default': 0.06")


def _new_user() -> int:
    return db.get_or_create_user_id(
        f"versions-{uuid.uuid4().hex[:10]}@example.com", "Versions Test")


def _save(user_id, name, code, strategy_id=None, evolution_request=None,
          **kwargs):
    sid = db.save_custom_strategy(
        user_id=user_id, strategy_name=name, class_name="VersionedStrategy",
        description='', ai_description='', code=code,
        parameters_json={'withdrawal_rate': {'default': 0.04}},
        validation_status='validated', strategy_id=strategy_id,
        evolution_request=evolution_request, **kwargs)
    assert sid
    return sid


def test_create_edit_evolve_chain():
    user_id = _new_user()
    sid = _save(user_id, "Chain Test", CODE_V1)

    versions = db.get_strategy_versions(sid, user_id)
    assert [v['source'] for v in versions] == ['create']
    assert versions[0]['is_head']

    _save(user_id, "Chain Test", CODE_V2, strategy_id=sid)  # plain edit
    _save(user_id, "Chain Test", CODE_V3, strategy_id=sid,
          evolution_request="make it 6%")

    versions = db.get_strategy_versions(sid, user_id)
    assert [v['source'] for v in versions] == ['evolve', 'edit', 'create']
    assert versions[0]['request'] == "make it 6%"
    # A proper chain: each node's parent is the next-older node
    assert versions[0]['parent_version_id'] == versions[1]['id']
    assert versions[1]['parent_version_id'] == versions[2]['id']
    assert versions[2]['parent_version_id'] is None


def test_identical_content_records_no_new_version():
    user_id = _new_user()
    sid = _save(user_id, "Idempotent Test", CODE_V1)
    _save(user_id, "Idempotent Test", CODE_V1, strategy_id=sid)
    versions = db.get_strategy_versions(sid, user_id)
    assert len(versions) == 1


def test_revert_is_append_only_and_restores_content():
    user_id = _new_user()
    sid = _save(user_id, "Revert Test", CODE_V1)
    _save(user_id, "Revert Test", CODE_V2, strategy_id=sid,
          evolution_request="5% instead")
    v_create = db.get_strategy_versions(sid, user_id)[-1]

    result = db.revert_strategy_to_version(sid, user_id, v_create['id'])
    assert result['success'], result

    row = db.get_custom_strategy(sid)
    assert row['code'] == CODE_V1
    assert row['git_commit_sha'] == v_create['content_hash']
    versions = db.get_strategy_versions(sid, user_id)
    assert [v['source'] for v in versions] == ['revert', 'evolve', 'create']
    assert versions[0]['content_hash'] == v_create['content_hash']
    # The restore shows up on the human timeline too
    history = db.get_strategy_evolution_history(sid)
    assert history and history[-1]['request'] == 'Restored an earlier version'


def test_revert_refuses_foreign_users_and_foreign_versions():
    user_id = _new_user()
    other_id = _new_user()
    sid = _save(user_id, "Guard Test", CODE_V1)
    _save(user_id, "Guard Test", CODE_V2, strategy_id=sid)
    old = db.get_strategy_versions(sid, user_id)[-1]

    assert not db.revert_strategy_to_version(sid, other_id, old['id'])['success']

    unrelated = _save(other_id, "Unrelated", CODE_V3)
    foreign_head = db.get_strategy_versions(unrelated, other_id)[0]
    res = db.revert_strategy_to_version(sid, user_id, foreign_head['id'])
    assert not res['success']
    assert 'history' in (res['error'] or '')

    head = db.get_strategy_versions(sid, user_id)[0]
    assert not db.revert_strategy_to_version(sid, user_id, head['id'])['success']


def test_clone_ancestry_stops_at_other_users_history():
    """A clone of another user's strategy sees the shared head node but never
    the donor's private iteration history."""
    owner = _new_user()
    cloner = _new_user()
    donor = _save(owner, "Donor", CODE_V1)
    _save(owner, "Donor", CODE_V2, strategy_id=donor,
          evolution_request="private iteration")
    donor_head = db.get_strategy_versions(donor, owner)[0]

    clone_id = db.save_custom_strategy(
        user_id=cloner, strategy_name="Their Clone",
        class_name="VersionedStrategy", description='', ai_description='',
        code=None, parameters_json={}, validation_status='validated',
        parent_strategy_id=donor)
    assert clone_id

    visible = db.get_strategy_versions(clone_id, cloner)
    assert [v['id'] for v in visible] == [donor_head['id']]  # head only


def test_cloning_your_own_strategy_never_destroys_it():
    """Regression: save_custom_strategy upserts by (user_id, name), so a
    same-name clone of your OWN strategy used to UPDATE the original row —
    is_clone_unedited=True then nulled its code. The clone service now
    suffixes colliding names."""
    from services.strategy_clone import clone_strategy

    user_id = _new_user()
    sid = _save(user_id, "Self Clone", CODE_V1)

    res = clone_strategy(strategy_id=sid, user_id=user_id, db=db)
    assert res['success'], res
    assert res['strategy_id'] != sid
    assert db.get_custom_strategy(sid)['code'] == CODE_V1  # original intact
    clone = db.get_custom_strategy(res['strategy_id'])
    assert clone['strategy_name'] == "Self Clone (clone)"
    assert clone['code'] == CODE_V1  # inherited through the parent pointer
    # And the clone's head points at the shared version node
    assert ([v['id'] for v in db.get_strategy_versions(res['strategy_id'], user_id)]
            == [db.get_strategy_versions(sid, user_id)[0]['id']])


def test_revert_to_head_repairs_a_diverged_row():
    """A row whose content diverged from its own head (e.g. the historical
    self-clone corruption) is repaired by restoring the head."""
    user_id = _new_user()
    sid = _save(user_id, "Repair Test", CODE_V1)
    head = db.get_strategy_versions(sid, user_id)[0]

    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE CUSTOM_STRATEGIES SET code = NULL, "
                       "git_commit_sha = NULL WHERE id = %s", (sid,))
        conn.commit()
    finally:
        db.release_connection(conn)

    result = db.revert_strategy_to_version(sid, user_id, head['id'])
    assert result['success'], result
    assert db.get_custom_strategy(sid)['code'] == CODE_V1
    # Content equals the head, so no duplicate node was appended
    assert len(db.get_strategy_versions(sid, user_id)) == 1
    # A true no-op (row already matches head) is still refused
    assert not db.revert_strategy_to_version(sid, user_id, head['id'])['success']


def test_backfill_reconstructs_legacy_rows():
    user_id = _new_user()
    sid = _save(user_id, "Legacy Test", CODE_V2)

    # Rewind the row to its pre-V39 shape: no head, no version rows, and a
    # legacy evolution_history entry carrying the old previous_code snapshot.
    legacy_entry = {'timestamp': '2026-09-15T00:00:00+00:00',
                    'request': 'legacy evolve', 'user_id': user_id,
                    'commit_sha': 'x', 'previous_code': CODE_V1}
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE CUSTOM_STRATEGIES SET head_version_id = NULL, "
                       "evolution_history = %s::jsonb WHERE id = %s",
                       (json.dumps([legacy_entry]), sid))
        cursor.execute("DELETE FROM STRATEGY_VERSIONS WHERE strategy_id = %s", (sid,))
        # A pointer clone of the legacy row, also headless
        cursor.execute("""
            INSERT INTO CUSTOM_STRATEGIES (user_id, strategy_name, class_name,
                parameters_json, parent_strategy_id, validation_status)
            VALUES (%s, 'Legacy Clone', 'VersionedStrategy', '{}', %s, 'validated')
            RETURNING id
        """, (user_id, sid))
        clone_id = cursor.fetchone()[0]
        conn.commit()
    finally:
        db.release_connection(conn)

    assert backfill_strategy_versions(db) >= 2  # the row + its clone

    versions = db.get_strategy_versions(sid, user_id)
    assert [v['source'] for v in versions] == ['backfill', 'backfill']
    assert versions[0]['is_head']
    assert db.get_strategy_version(versions[0]['id'])['code'] == CODE_V2
    assert db.get_strategy_version(versions[1]['id'])['code'] == CODE_V1
    assert versions[0]['request'] == 'legacy evolve'
    # The clone points at the reconstructed head
    assert [v['id'] for v in db.get_strategy_versions(clone_id, user_id)][0] == versions[0]['id']
    # Idempotent: a second pass changes nothing
    assert backfill_strategy_versions(db) == 0
    assert len(db.get_strategy_versions(sid, user_id)) == 2
