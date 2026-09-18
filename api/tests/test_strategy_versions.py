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
    # The restore lives in the version chain alone — the legacy V37
    # timeline is retired (V40) and stays untouched
    assert db.get_strategy_evolution_history(sid) == []


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
    """A clone of another user's strategy sees the shared head node (marked
    inherited, its evolve prompt redacted) but never the donor's private
    iteration history — and evolving the clone keeps exactly that boundary
    node restorable."""
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
    # The donor's evolve prompt is private — redacted on the boundary node
    assert visible[0]['owned'] is False
    assert visible[0]['request'] is None
    # The donor sees their own prompt untouched
    assert db.get_strategy_versions(donor, owner)[0]['request'] == "private iteration"

    # Evolve the clone (cross-user fork): the boundary node must stay in the
    # chain so the pre-evolve state is restorable — the feature's core flow.
    _save(cloner, "Their Clone", CODE_V3, strategy_id=clone_id,
          evolution_request="my own change")
    chain = db.get_strategy_versions(clone_id, cloner)
    assert [v['id'] for v in chain] == [chain[0]['id'], donor_head['id']]
    assert chain[0]['owned'] is True and chain[0]['request'] == "my own change"
    assert chain[1]['owned'] is False and chain[1]['request'] is None
    # ...but never the donor's deeper history (the create node stays hidden)
    assert len(chain) == 2

    # Restore to the boundary node works and brings back the cloned code
    res = db.revert_strategy_to_version(clone_id, cloner, donor_head['id'])
    assert res['success'], res
    assert db.get_custom_strategy(clone_id)['code'] == CODE_V2


def test_pure_clone_revert_is_refused():
    """An unedited clone tracks its parent — revert must not silently
    materialize it into a fork."""
    owner = _new_user()
    cloner = _new_user()
    donor = _save(owner, "Fixed Donor", CODE_V1)
    donor_head = db.get_strategy_versions(donor, owner)[0]
    clone_id = db.save_custom_strategy(
        user_id=cloner, strategy_name="Tracking Clone",
        class_name="VersionedStrategy", description='', ai_description='',
        code=None, parameters_json={}, validation_status='validated',
        parent_strategy_id=donor)

    res = db.revert_strategy_to_version(clone_id, cloner, donor_head['id'])
    assert not res['success']
    assert 'unedited clone' in res['error']
    row = db.get_custom_strategy(clone_id)
    assert row['is_pure_clone'] is True  # still a tracking pointer


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


def test_cloning_over_a_soft_deleted_name_never_resurrects_it():
    """The upsert's name lookup matches soft-deleted rows too (and its UPDATE
    resurrects them), so the collision guard must see deleted names."""
    from services.strategy_clone import clone_strategy

    user_id = _new_user()
    sid = _save(user_id, "Trash Test", CODE_V1)
    assert db.soft_delete_custom_strategy(sid, user_id)

    donor_owner = _new_user()
    donor = _save(donor_owner, "Trash Test", CODE_V2)
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE CUSTOM_STRATEGIES SET is_public = TRUE WHERE id = %s",
                       (donor,))
        conn.commit()
    finally:
        db.release_connection(conn)

    res = clone_strategy(strategy_id=donor, user_id=user_id, db=db)
    assert res['success'], res
    assert res['strategy_id'] not in (sid, donor)
    clone = db.get_custom_strategy(res['strategy_id'])
    assert clone['strategy_name'] == "Trash Test (clone)"
    # The soft-deleted row stays deleted and untouched
    trashed = db.get_custom_strategy(sid)
    assert trashed['deleted_at'] is not None
    assert trashed['code'] == CODE_V1


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


def test_lineage_includes_own_forks_with_head_markers():
    """The lineage graph adds the user's own forks to the ancestry spine,
    with head markers naming which strategy each head node is current for."""
    from services.strategy_clone import clone_strategy

    user_id = _new_user()
    sid = _save(user_id, "Lineage Root", CODE_V1)
    clone = clone_strategy(strategy_id=sid, user_id=user_id, db=db)
    assert clone['success']
    clone_id = clone['strategy_id']
    _save(user_id, "Lineage Root (clone)", CODE_V2, strategy_id=clone_id,
          evolution_request="fork it")

    lineage = db.get_strategy_lineage(sid, user_id)
    assert [v['id'] for v in lineage['spine']] == \
        [db.get_strategy_versions(sid, user_id)[0]['id']]
    assert len(lineage['spine']) == 1 and len(lineage['forks']) == 1
    root_node = lineage['spine'][0]
    fork_node = lineage['forks'][0]
    assert fork_node['parent_version_id'] == root_node['id']
    assert fork_node['strategy_name'] == "Lineage Root (clone)"
    assert fork_node['request'] == "fork it"
    assert fork_node['strategy_deleted'] is False
    # Head markers land on the SPINE rows too (not just copies): the root
    # node heads the original, the fork heads the clone
    assert [h['name'] for h in root_node['heads']] == ["Lineage Root"]
    assert [h['name'] for h in fork_node['heads']] == ["Lineage Root (clone)"]

    # Soft-deleting the clone must not amputate the branch from the graph —
    # its nodes stay as flagged pass-through (and it stops being a head).
    assert db.soft_delete_custom_strategy(clone_id, user_id)
    lineage = db.get_strategy_lineage(sid, user_id)
    assert len(lineage['forks']) == 1
    assert lineage['forks'][0]['strategy_deleted'] is True
    assert lineage['forks'][0]['heads'] == []


def test_lineage_excludes_other_users_forks():
    """Another user's fork of my public strategy is THEIR private history —
    my lineage graph must not include it."""
    owner = _new_user()
    forker = _new_user()
    sid = _save(owner, "Public Root", CODE_V1)
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE CUSTOM_STRATEGIES SET is_public = TRUE WHERE id = %s", (sid,))
        conn.commit()
    finally:
        db.release_connection(conn)

    from services.strategy_clone import clone_strategy
    clone = clone_strategy(strategy_id=sid, user_id=forker, db=db)
    assert clone['success']
    _save(forker, "Public Root", CODE_V2, strategy_id=clone['strategy_id'],
          evolution_request="their private fork")

    lineage = db.get_strategy_lineage(sid, owner)
    assert lineage['forks'] == []
    assert all(n['in_spine'] for n in lineage['spine'])


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
    # Historical nodes get their parameters reconstructed from the code (the
    # snapshots never stored them), so a restore must not wipe the row's
    # params — the pre-fix behavior wrote '{}' over them.
    hist_params = json.loads(db.get_strategy_version(versions[1]['id'])['parameters_json'])
    assert hist_params['withdrawal_rate']['default'] == 0.04
    res = db.revert_strategy_to_version(sid, user_id, versions[1]['id'])
    assert res['success'], res
    row = db.get_custom_strategy(sid)
    assert row['code'] == CODE_V1
    restored_params = db.deserialize_json_column(row['parameters_json'])
    assert restored_params['withdrawal_rate']['default'] == 0.04
    # The clone points at the reconstructed head
    assert [v['id'] for v in db.get_strategy_versions(clone_id, user_id)][0] == versions[0]['id']
    # Idempotent for reconstruction: a later pass rebuilds nothing (the
    # revert above legitimately appended one node)
    assert backfill_strategy_versions(db) == 0
    assert len(db.get_strategy_versions(sid, user_id)) == 3


def test_v40_migration_strips_snapshots_only_from_versioned_rows():
    """The V40 SQL removes previous_code blobs from rows that have a version
    head (the DAG holds their code) and keeps the light timeline fields; a
    headless row keeps its snapshots — they are the startup backfill's input."""
    from pathlib import Path

    sql = (Path(__file__).parent.parent / 'db' / 'migrations' / 'postgresql'
           / 'V40__retire_evolution_snapshots.sql').read_text()

    user_id = _new_user()
    versioned = _save(user_id, "V40 Versioned", CODE_V1)
    headless = _save(user_id, "V40 Headless", CODE_V1)
    entries = [{'timestamp': '2026-09-15T00:00:00+00:00', 'request': 'legacy',
                'user_id': user_id, 'commit_sha': 'x',
                'previous_code': CODE_V2},
               {'timestamp': '2026-09-16T00:00:00+00:00', 'request': 'later',
                'user_id': user_id, 'commit_sha': 'y'}]
    conn = db.get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE CUSTOM_STRATEGIES SET evolution_history = %s::jsonb "
            "WHERE id IN (%s, %s)",
            (json.dumps(entries), versioned, headless))
        cursor.execute(
            "UPDATE CUSTOM_STRATEGIES SET head_version_id = NULL WHERE id = %s",
            (headless,))
        cursor.execute(sql)
        conn.commit()
        cursor.execute(
            "SELECT id, evolution_history FROM CUSTOM_STRATEGIES "
            "WHERE id IN (%s, %s)", (versioned, headless))
        rows = dict(cursor.fetchall())
    finally:
        db.release_connection(conn)

    stripped = rows[versioned]
    assert [e.get('request') for e in stripped] == ['legacy', 'later']
    assert all('previous_code' not in e for e in stripped)
    assert stripped[0]['timestamp'] == '2026-09-15T00:00:00+00:00'
    kept = rows[headless]
    assert kept[0]['previous_code'] == CODE_V2  # backfill input, untouched
