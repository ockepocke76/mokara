"""Custom strategies: CRUD, lineage, publishing, and evaluations.

Split out of db/postgresql_db.py (R5.2b); method bodies moved verbatim.
"""

import json
import logging
from datetime import datetime, timezone

from psycopg2 import errors as pg_errors
from psycopg2 import extras

from utils.strategy_utils import calculate_strategy_hash, next_free_name

from ..logging_utils import log_db_call


class StrategiesMixin:
    """Custom strategies: CRUD, lineage, publishing, and evaluations. Mixed into PostgreSQLDatabase."""

    def _record_strategy_version(self, cursor, *, strategy_id, code,
                                 parameters_json, class_name, content_hash,
                                 source, request, user_id, prior_code=None):
        """Append a version node (V39 DAG) and move the strategy's head, on
        the caller's cursor/transaction. The version store is the recovery
        substrate, so failures are NOT swallowed — the save fails with them.
        The one tolerated case is a pre-V39 schema (missing table/column):
        that rolls back to a savepoint and returns None so a not-yet-migrated
        database keeps saving (callers degrade accordingly).

        No-op when the head already carries this content_hash. When the
        strategy has no head yet but we know the code being replaced
        (prior_code), a 'backfill' parent node (parameters unknown → NULL) is
        created first so the pre-change code is never lost — this makes the
        save path self-healing for rows the startup backfill missed.
        """
        cursor.execute("SAVEPOINT strategy_version")
        try:
            cursor.execute(
                "SELECT head_version_id FROM CUSTOM_STRATEGIES WHERE id = %s",
                (strategy_id,))
            row = cursor.fetchone()
            head_id = row[0] if row else None
            if head_id:
                cursor.execute(
                    "SELECT content_hash FROM STRATEGY_VERSIONS WHERE id = %s",
                    (head_id,))
                head = cursor.fetchone()
                if head and head[0] == content_hash:
                    cursor.execute("RELEASE SAVEPOINT strategy_version")
                    return head_id  # identical content — no new node
            elif prior_code and prior_code.strip() and prior_code.strip() != (code or '').strip():
                cursor.execute("""
                    INSERT INTO STRATEGY_VERSIONS
                        (strategy_id, content_hash, code, parameters_json,
                         class_name, parent_version_id, source, created_by_user_id)
                    VALUES (%s, %s, %s, NULL, %s, NULL, 'backfill', %s)
                    RETURNING id
                """, (strategy_id, calculate_strategy_hash(prior_code, {}),
                      prior_code, class_name, user_id))
                head_id = cursor.fetchone()[0]
            cursor.execute("""
                INSERT INTO STRATEGY_VERSIONS
                    (strategy_id, content_hash, code, parameters_json,
                     class_name, parent_version_id, source, request,
                     created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (strategy_id, content_hash, code, parameters_json, class_name,
                  head_id, source, request, user_id))
            version_id = cursor.fetchone()[0]
            cursor.execute(
                "UPDATE CUSTOM_STRATEGIES SET head_version_id = %s WHERE id = %s",
                (version_id, strategy_id))
            cursor.execute("RELEASE SAVEPOINT strategy_version")
            return version_id
        except (pg_errors.UndefinedTable, pg_errors.UndefinedColumn):
            logging.warning(
                "Strategy-version store missing (V39 not applied); saving without it")
            cursor.execute("ROLLBACK TO SAVEPOINT strategy_version")
            return None
        except Exception:
            # Anything else is a real failure of the recovery substrate:
            # restore the savepoint so the transaction is clean, then let the
            # save fail loudly instead of silently diverging row from head.
            cursor.execute("ROLLBACK TO SAVEPOINT strategy_version")
            raise

    @log_db_call
    def save_custom_strategy(self, user_id, strategy_name, class_name, description, ai_description, code, 
                            parameters_json, validation_status='not_started', validation_error=None, 
                            last_validation_timestamp=None, strategy_id=None, parent_strategy_id=None, 
                            clone_source_commit_sha=None, git_branch_name=None, git_commit_sha=None, 
                            is_clone_unedited=None, evolution_request=None):
        conn = self.get_connection()
        try:
            # Ensure parameters_json is valid
            if parameters_json is None:
                parameters_json = '{}'
            elif isinstance(parameters_json, (dict, list)):
                parameters_json = json.dumps(parameters_json)
            
            # Ensure validation_error is a string/JSON if it's a dict or list
            if isinstance(validation_error, (dict, list)):
                validation_error = json.dumps(validation_error)
                
            cursor = self._get_cursor(conn)

            # Intent is EXPLICIT: a strategy_id means update that row, no
            # strategy_id means create a new one. (The old behavior matched
            # by (user_id, strategy_name) — soft-deleted rows included — so
            # a same-named create silently overwrote, or resurrected and
            # overwrote, an existing strategy.)
            row = None
            if strategy_id:
                # Code fetched too (pre-change state for the version DAG's
                # transitional pre-V39 snapshot). COALESCE from the parent:
                # a pure-reference clone's own code is NULL but its
                # effective pre-change code is the parent's.
                # NOTE: the update never touches deleted_at — deleting a
                # strategy wins over an in-flight save (e.g. an evolve run
                # seeded before the user trashed it): the row stays in the
                # trash, restorable, and can't collide with a live namesake.
                cursor.execute("""
                    SELECT cs.id, COALESCE(cs.code, p.code)
                    FROM CUSTOM_STRATEGIES cs
                    LEFT JOIN CUSTOM_STRATEGIES p ON p.id = cs.parent_strategy_id
                    WHERE cs.id = %s
                """, (strategy_id,))
                row = cursor.fetchone()
                if row is None:
                    # Update intent against a row that doesn't exist must
                    # not quietly become a create under the caller's name.
                    logging.error(
                        f"save_custom_strategy: strategy {strategy_id} not found for update")
                    conn.rollback()
                    return False
            previous_code = row[1] if row else None

            if row:
                # === UPDATE EXISTING STRATEGY ===
                strategy_id = row[0]

                # Strategy identity: git_commit_sha is a content hash of the
                # code + parameters (the column name is a legacy of the old
                # GitHub-backed app; the DB is the authoritative store).
                if code and not git_commit_sha:
                     git_commit_sha = calculate_strategy_hash(code, json.loads(parameters_json))

                # If code is NULL (pure rename of a pointer), ensure we don't accidentally overwrite with NULL if we didn't mean to?
                # Actually, if code passed is NONE, we keep it NONE. If code passed is value, we update.
                
                if code:
                    # Full Update (Materialization or Code Edit)
                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES 
                    SET class_name = %s, description = %s, ai_description = %s, 
                        parameters_json = %s, validation_status = %s, validation_error = %s, 
                        last_validation_timestamp = %s, updated_at = CURRENT_TIMESTAMP,
                        git_branch_name = %s, git_repo_url = NULL,
                        last_synced_at = CURRENT_TIMESTAMP,
                        parent_strategy_id = COALESCE(parent_strategy_id, %s),
                        clone_source_commit_sha = COALESCE(clone_source_commit_sha, %s),
                        is_clone_unedited = COALESCE(is_clone_unedited, %s),
                        -- If we are specifically saving as an unedited clone, clear existing code/SHA 
                        -- to ensure inheritance from parent works correctly (recycling fix)
                        code = CASE WHEN %s = TRUE THEN NULL ELSE %s END,
                        git_commit_sha = CASE WHEN %s = TRUE THEN NULL ELSE %s END
                    WHERE id = %s
                """, (class_name, description, ai_description, parameters_json,
                      validation_status, validation_error, last_validation_timestamp,
                      git_branch_name,
                      parent_strategy_id, clone_source_commit_sha, is_clone_unedited,
                      is_clone_unedited, code, is_clone_unedited, git_commit_sha, strategy_id))
                else:
                    # Metadata Only Update (e.g. Renaming a Pure Pointer)
                    # We do NOT update 'code' here.
                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES 
                    SET class_name = %s, description = %s, ai_description = %s,
                        parameters_json = %s, validation_status = %s, validation_error = %s,
                        last_validation_timestamp = %s, updated_at = CURRENT_TIMESTAMP,
                        parent_strategy_id = COALESCE(parent_strategy_id, %s),
                        clone_source_commit_sha = COALESCE(clone_source_commit_sha, %s),
                        is_clone_unedited = %s,
                        -- If we are specifically saving as an unedited clone, clear existing code/SHA 
                        -- to ensure inheritance from parent works correctly (recycling fix)
                        code = CASE WHEN %s = TRUE THEN NULL ELSE code END,
                        git_commit_sha = CASE WHEN %s = TRUE THEN NULL ELSE git_commit_sha END
                    WHERE id = %s
                """, (class_name, description, ai_description, parameters_json,
                      validation_status, validation_error, last_validation_timestamp,
                      parent_strategy_id, clone_source_commit_sha, is_clone_unedited,
                      is_clone_unedited, is_clone_unedited, strategy_id))

                version_id = None
                if code and not is_clone_unedited:
                    # V39 version DAG: this save replaces the row's code —
                    # append a version node and move the head.
                    version_id = self._record_strategy_version(
                        cursor, strategy_id=strategy_id, code=code,
                        parameters_json=parameters_json, class_name=class_name,
                        content_hash=(git_commit_sha or
                                      calculate_strategy_hash(code, json.loads(parameters_json))),
                        source=('evolve' if evolution_request else 'edit'),
                        request=evolution_request, user_id=user_id,
                        prior_code=previous_code)

                if (evolution_request and code and not is_clone_unedited
                        and version_id is None):
                    # Transitional, pre-V39 schema only: the version store
                    # couldn't record this evolve, so the legacy V37 timeline
                    # keeps the previous_code snapshot — the only recovery
                    # material until the startup backfill runs. On migrated
                    # databases the legacy timeline is retired (V40): requests
                    # live in STRATEGY_VERSIONS and the generation runs.
                    # Reachable because the API process does NOT run
                    # migrations (only the worker, the deploy script, and the
                    # admin endpoint do) — an API container can serve saves
                    # before the worker has applied V39.
                    # Savepoint: recording it must never fail the save itself.
                    entry = {
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'request': evolution_request,
                        'user_id': user_id,
                        'commit_sha': git_commit_sha,
                        'previous_code': previous_code,
                    }
                    cursor.execute("SAVEPOINT evolution_append")
                    try:
                        cursor.execute("""
                            UPDATE CUSTOM_STRATEGIES
                            SET evolution_history = COALESCE(evolution_history, '[]'::jsonb) || %s::jsonb
                            WHERE id = %s
                        """, (json.dumps([entry]), strategy_id))
                        cursor.execute("RELEASE SAVEPOINT evolution_append")
                    except Exception:
                        logging.exception("Evolution-history append failed; saving without it")
                        cursor.execute("ROLLBACK TO SAVEPOINT evolution_append")

            else:
                # === INSERT NEW STRATEGY ===

                # A colliding LIVE name gets suffixed (deleted names don't
                # conflict — nothing is resurrected on this path anymore).
                # V41's partial unique index turns any remaining race into a
                # clean failed save instead of a corrupted row.
                cursor.execute(
                    "SELECT strategy_name FROM CUSTOM_STRATEGIES "
                    "WHERE user_id = %s AND deleted_at IS NULL", (user_id,))
                existing = {r[0] for r in cursor.fetchall()}
                base_name = strategy_name
                strategy_name = next_free_name(base_name, existing)

                # Pure reference clone (parent + no code) inserts a pointer
                # row; anything else is an independent strategy. Retried on
                # a unique-name race (two concurrent creates picking the same
                # suffix): the loser re-suffixes instead of failing the save
                # and discarding finished work.
                code_column = "NULL" if (parent_strategy_id and code is None) else "%s"
                insert_sql = f"""
                    INSERT INTO CUSTOM_STRATEGIES (
                        user_id, strategy_name, class_name, description, ai_description, code,
                        parameters_json, validation_status, validation_error, last_validation_timestamp,
                        parent_strategy_id, clone_source_commit_sha, fork_count, cloned_at
                    ) VALUES (%s, %s, %s, %s, %s, {code_column}, %s, %s, %s, %s, %s, %s, 0, CURRENT_TIMESTAMP)
                    RETURNING id
                """
                strategy_id = None
                for _ in range(5):
                    params = [user_id, strategy_name, class_name, description,
                              ai_description]
                    if code_column == "%s":
                        params.append(code)
                    params += [parameters_json, validation_status,
                               validation_error, last_validation_timestamp,
                               parent_strategy_id, clone_source_commit_sha]
                    cursor.execute("SAVEPOINT strategy_insert")
                    try:
                        cursor.execute(insert_sql, params)
                        strategy_id = cursor.fetchone()[0]
                        cursor.execute("RELEASE SAVEPOINT strategy_insert")
                        break
                    except pg_errors.UniqueViolation:
                        cursor.execute("ROLLBACK TO SAVEPOINT strategy_insert")
                        existing.add(strategy_name)
                        strategy_name = next_free_name(base_name, existing)
                if strategy_id is None:
                    raise RuntimeError(
                        f"Could not find a free strategy name for user {user_id}")

                if parent_strategy_id:
                    # Inline on the SAME cursor/connection: calling
                    # self.increment_fork_count here would check out a second
                    # pooled connection while this one is mid-transaction
                    # (pool-exhaustion deadlock hazard).
                    cursor.execute(
                        "UPDATE CUSTOM_STRATEGIES SET fork_count = COALESCE(fork_count, 0) + 1 WHERE id = %s",
                        (parent_strategy_id,))

                # Content hash is the strategy's identity (git_commit_sha is
                # a legacy column name; the DB is the authoritative store).
                if code and not git_commit_sha:
                    git_commit_sha = calculate_strategy_hash(code, json.loads(parameters_json) if parameters_json else {})

                    cursor.execute("""
                        UPDATE CUSTOM_STRATEGIES
                        SET git_commit_sha = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (git_commit_sha, strategy_id))

                if code:
                    # V39 version DAG: the first commit on this strategy.
                    self._record_strategy_version(
                        cursor, strategy_id=strategy_id, code=code,
                        parameters_json=parameters_json, class_name=class_name,
                        content_hash=git_commit_sha, source='create',
                        request=evolution_request, user_id=user_id)
                elif parent_strategy_id:
                    # Pure-reference clone: the head is a POINTER to the
                    # parent's current version node — no copy, and a later
                    # evolve of the clone forks the DAG at that node.
                    # Savepoint: must not fail saves on a pre-V39 schema.
                    cursor.execute("SAVEPOINT clone_head")
                    try:
                        cursor.execute("""
                            UPDATE CUSTOM_STRATEGIES SET head_version_id =
                                (SELECT head_version_id FROM CUSTOM_STRATEGIES WHERE id = %s)
                            WHERE id = %s
                        """, (parent_strategy_id, strategy_id))
                        cursor.execute("RELEASE SAVEPOINT clone_head")
                    except Exception:
                        logging.exception("Clone head-pointer set failed; saving without it")
                        cursor.execute("ROLLBACK TO SAVEPOINT clone_head")

            conn.commit()

            return strategy_id
        except Exception as e:
            logging.error(f"Failed to save custom strategy: {e}", exc_info=True)
            conn.rollback()
            return False
        finally:
            self.release_connection(conn)

    @log_db_call
    def get_user_custom_strategies(self, user_id):
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Fetch user's strategies OR public strategies,
                # joined with evaluation results.
                # UPDATED: Includes fallback for unedited clones to use parent's evaluation (Source SHA)
                cursor.execute("""
                    SELECT * FROM (
                        -- Use DISTINCT ON to ensure one row per strategy even if multiple evaluations exist
                        -- Prioritize actual user's strategies over public ones if ID matches
                        SELECT DISTINCT ON (c.id)
                            c.id, c.user_id, c.strategy_name,
                            COALESCE(c.class_name, p.class_name) as class_name,
                            COALESCE(c.description, p.description) as description,
                            COALESCE(c.code, p.code) as code,
                            COALESCE(c.parameters_json, p.parameters_json) as parameters_json,
                            COALESCE(c.ai_description, p.ai_description) as ai_description,
                            c.validation_status, c.validation_error,
                            c.created_at, c.updated_at, c.last_validation_timestamp,
                            c.git_branch_name, c.git_commit_sha, c.git_repo_url,
                            c.parent_strategy_id, c.clone_source_commit_sha, c.cloned_at,
                            c.is_public, c.is_published_to_leaderboard, c.fork_count,
                            c.is_clone_unedited,
                            (c.code IS NULL AND c.parent_strategy_id IS NOT NULL) as is_pure_clone,
                            e.excellence_score, e.sharpe_ratio, e.sortino_ratio,
                            (e.id IS NOT NULL) as has_evaluation
                        FROM CUSTOM_STRATEGIES c
                        LEFT JOIN CUSTOM_STRATEGIES p ON c.parent_strategy_id = p.id
                        LEFT JOIN STRATEGY_EVALUATIONS e ON (
                            e.git_commit_sha = COALESCE(c.git_commit_sha, c.clone_source_commit_sha)
                        )
                        WHERE (c.user_id = %s OR (c.is_public = TRUE AND c.user_id != 0))
                        AND c.deleted_at IS NULL
                        ORDER BY c.id, c.updated_at DESC, e.created_at DESC
                    ) sub
                    ORDER BY sub.updated_at DESC
                """, (user_id,))
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Failed to get custom strategies: {e}", exc_info=True)
            return []

    @log_db_call
    def get_user_strategy_names(self, user_id):
        """The user's LIVE strategy names — the universe new names must be
        unique within (V41 partial index; soft-deleted names are free to
        reuse, nothing resurrects them on the create path anymore)."""
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute(
                    "SELECT strategy_name FROM CUSTOM_STRATEGIES "
                    "WHERE user_id = %s AND deleted_at IS NULL",
                    (user_id,))
                return {row[0] for row in cursor.fetchall()}
        except Exception as e:
            logging.error(f"Failed to get strategy names: {e}", exc_info=True)
            return set()

    @log_db_call
    def get_custom_strategy(self, strategy_id):
        """Fetch a specific custom strategy by ID."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Use LEFT JOIN for Pure Reference Cloning
                cursor.execute("""
                    SELECT
                        c.id, c.user_id, c.strategy_name,
                        COALESCE(c.class_name, p.class_name) as class_name,
                        COALESCE(c.description, p.description) as description,
                        COALESCE(c.code, p.code) as code,
                        COALESCE(c.parameters_json, p.parameters_json) as parameters_json,
                        COALESCE(c.ai_description, p.ai_description) as ai_description,
                        c.validation_status, c.validation_error,
                        c.created_at, c.updated_at, c.last_validation_timestamp,
                        c.git_branch_name, c.git_commit_sha, c.git_repo_url,
                        c.parent_strategy_id, c.clone_source_commit_sha, c.cloned_at,
                        c.is_public, c.is_published_to_leaderboard, c.fork_count,
                        c.deleted_at,
                        (c.code IS NULL AND c.parent_strategy_id IS NOT NULL) as is_pure_clone
                    FROM CUSTOM_STRATEGIES c
                    LEFT JOIN CUSTOM_STRATEGIES p ON c.parent_strategy_id = p.id
                    WHERE c.id = %s
                """, (strategy_id,))

                return cursor.fetchone()
        except Exception as e:
            logging.error(f"Failed to get custom strategy {strategy_id}: {e}", exc_info=True)
            return None

    @log_db_call
    def delete_custom_strategy(self, strategy_id, user_id):
        """DEPRECATED: Use soft_delete_custom_strategy instead."""
        return self.soft_delete_custom_strategy(strategy_id, user_id)

    @log_db_call
    def soft_delete_custom_strategy(self, strategy_id, user_id):
        """
        Soft deletes a custom strategy by setting deleted_at timestamp.
        Preserves data for lineage tracking and potential restore.
        """
        try:
            with self._connection_cursor() as cursor:
                # Verify ownership and that strategy isn't already deleted
                cursor.execute("""
                    SELECT id, user_id FROM CUSTOM_STRATEGIES
                    WHERE id = %s AND deleted_at IS NULL
                """, (strategy_id,))

                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Strategy {strategy_id} not found or already deleted")
                    return False

                _, owner_id = row
                if owner_id != user_id:
                    logging.warning(f"SECURITY: User {user_id} attempted to delete strategy {strategy_id} owned by {owner_id}")
                    return False

                # Soft delete: set timestamp
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET deleted_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (strategy_id,))

                updated = cursor.rowcount > 0
            logging.info(f"Soft deleted strategy {strategy_id} for user {user_id}")
            return updated
        except Exception as e:
            logging.error(f"Failed to soft delete strategy: {e}", exc_info=True)
            return False

    @log_db_call
    def restore_custom_strategy(self, strategy_id, user_id):
        """
        Restores a soft-deleted strategy by clearing deleted_at timestamp.
        Note: Admin check should be done by caller before calling this method.
        """
        try:
            with self._connection_cursor() as cursor:
                # Verify strategy exists and is deleted
                cursor.execute("""
                    SELECT id, user_id FROM CUSTOM_STRATEGIES
                    WHERE id = %s AND deleted_at IS NOT NULL
                """, (strategy_id,))

                row = cursor.fetchone()
                if not row:
                    logging.warning(f"Strategy {strategy_id} not found or not deleted")
                    return False

                # Restore: clear timestamp
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET deleted_at = NULL
                    WHERE id = %s
                """, (strategy_id,))

                updated = cursor.rowcount > 0
            logging.info(f"Restored strategy {strategy_id}")
            return updated
        except Exception as e:
            logging.error(f"Failed to restore strategy: {e}", exc_info=True)
            return False

    @log_db_call
    def update_custom_strategy(self, strategy_id, user_id, strategy_name, description, ai_description, parameters_json, git_branch_name=None, git_commit_sha=None):
        try:
            with self._connection_cursor() as cursor:
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET strategy_name = %s,
                        description = %s,
                        ai_description = %s,
                        parameters_json = %s,
                        git_branch_name = COALESCE(%s, git_branch_name),
                        git_commit_sha = COALESCE(%s, git_commit_sha),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (strategy_name, description, ai_description, parameters_json, git_branch_name, git_commit_sha, strategy_id, user_id))
                updated = cursor.rowcount > 0
            return updated
        except Exception as e:
            logging.error(f"Failed to update custom strategy: {e}", exc_info=True)
            return False

    @log_db_call
    def get_strategy_evolution_history(self, strategy_id, user_id):
        """
        The legacy evolution timeline (V37 column, frozen since V40) —
        OWNER-ONLY, enforced here in SQL like the version-DAG reads: the
        entries carry verbatim evolve requests, which viewing a public
        strategy never grants. Non-owners get []. previous_code snapshots
        are stripped in SQL (post-V40 they only exist on rows the startup
        backfill hasn't reconstructed yet — recovery material, never UI).

        Returns:
            List of entries with timestamp, request, commit_sha, user_id.
        """
        try:
            with self._connection_cursor(commit=False) as cursor:
                cursor.execute("""
                    SELECT COALESCE(
                        (SELECT jsonb_agg(entry - 'previous_code' ORDER BY ord)
                         FROM jsonb_array_elements(cs.evolution_history)
                              WITH ORDINALITY AS t(entry, ord)),
                        '[]'::jsonb)
                    FROM CUSTOM_STRATEGIES cs
                    WHERE cs.id = %s AND cs.user_id = %s
                """, (strategy_id, user_id))

                row = cursor.fetchone()
                if not row:
                    return []

                db_history = row[0]

                if isinstance(db_history, str):
                    db_history = json.loads(db_history)
                return db_history or []
        except Exception as e:
            logging.error(f"Failed to get evolution history: {e}", exc_info=True)
            return []

    # V39 version DAG ------------------------------------------------------

    # A node is GRANTED to the user when they own the strategy it was
    # committed under, or when their own chain forked from it (the clone
    # boundary: the fork point's content was handed over at clone time).
    # Traversal therefore expands only FROM nodes the user owns — a foreign
    # node enters the chain as its boundary, but its own ancestors (the
    # donor's private iterations) stay unreachable.
    _VERSION_ANCESTRY_SQL = """
        WITH RECURSIVE chain AS (
            SELECT v.id, v.content_hash, v.parent_version_id, v.strategy_id,
                   v.source, v.request, v.created_at, 0 AS depth
            FROM CUSTOM_STRATEGIES cs
            JOIN STRATEGY_VERSIONS v ON v.id = cs.head_version_id
            WHERE cs.id = %(strategy_id)s
            UNION ALL
            SELECT p.id, p.content_hash, p.parent_version_id, p.strategy_id,
                   p.source, p.request, p.created_at, c.depth + 1
            FROM STRATEGY_VERSIONS p
            JOIN chain c ON p.id = c.parent_version_id
            JOIN CUSTOM_STRATEGIES co ON co.id = c.strategy_id
            WHERE c.depth < 500 AND co.user_id = %(user_id)s
        )
        SELECT chain.id, chain.content_hash, chain.parent_version_id,
               chain.strategy_id, chain.source, chain.created_at, chain.depth,
               (owner.user_id IS NOT NULL AND owner.user_id = %(user_id)s)
                   AS owned,
               -- The evolve request is the author's private prompt: only the
               -- node's owner gets to read it.
               CASE WHEN owner.user_id = %(user_id)s THEN chain.request END
                   AS request
        FROM chain
        LEFT JOIN CUSTOM_STRATEGIES owner ON owner.id = chain.strategy_id
    """

    @log_db_call
    def get_strategy_versions(self, strategy_id, user_id):
        """The strategy's version ancestry (head first — its `git log`),
        metadata only. Nodes committed under other users' strategies appear
        only as clone-boundary nodes (owned=False, request redacted); their
        ancestors are never traversed."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor,
                                         commit=False) as cursor:
                cursor.execute(self._VERSION_ANCESTRY_SQL + " ORDER BY depth",
                               {'strategy_id': strategy_id, 'user_id': user_id})
                rows = [dict(r) for r in cursor.fetchall()]
                for r in rows:
                    r['is_head'] = r['depth'] == 0
                return rows
        except Exception as e:
            logging.error(f"Failed to get strategy versions: {e}", exc_info=True)
            return []

    @log_db_call
    def get_strategy_lineage(self, strategy_id, user_id):
        """The strategy's lineage GRAPH: its ancestry spine (same granted /
        redacted semantics as get_strategy_versions) plus every descendant
        node on the user's OWN strategies (their forks — soft-deleted ones
        included as pass-through, flagged strategy_deleted, so deleting an
        intermediate clone never amputates a live branch from the graph).
        Other users' forks of the user's strategies are private to those
        users and never appear.

        Everything runs on ONE connection/snapshot — a save landing between
        split reads would otherwise draw the fresh head as a parentless fork.

        Returns {'spine': [...], 'forks': [...]}; both row sets carry
        in_spine and heads = [{'id','name'}] naming the user's live
        strategies whose head is that node.
        """
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor,
                                         commit=False) as cursor:
                cursor.execute(self._VERSION_ANCESTRY_SQL + " ORDER BY depth",
                               {'strategy_id': strategy_id, 'user_id': user_id})
                spine = [dict(r) for r in cursor.fetchall()]
                if not spine:
                    return {'spine': [], 'forks': []}
                for r in spine:
                    r['is_head'] = r['depth'] == 0
                    r['in_spine'] = True
                spine_ids = [r['id'] for r in spine]

                cursor.execute("""
                    WITH RECURSIVE forks AS (
                        SELECT v.id, v.content_hash, v.parent_version_id,
                               v.strategy_id, v.source, v.request, v.created_at,
                               o.strategy_name,
                               (o.deleted_at IS NOT NULL) AS strategy_deleted
                        FROM STRATEGY_VERSIONS v
                        JOIN CUSTOM_STRATEGIES o ON o.id = v.strategy_id
                        WHERE v.parent_version_id = ANY(%(spine_ids)s)
                          AND v.id != ALL(%(spine_ids)s)
                          AND o.user_id = %(user_id)s
                        UNION
                        SELECT c.id, c.content_hash, c.parent_version_id,
                               c.strategy_id, c.source, c.request, c.created_at,
                               o2.strategy_name,
                               (o2.deleted_at IS NOT NULL) AS strategy_deleted
                        FROM STRATEGY_VERSIONS c
                        JOIN forks f ON c.parent_version_id = f.id
                        JOIN CUSTOM_STRATEGIES o2 ON o2.id = c.strategy_id
                        WHERE o2.user_id = %(user_id)s
                    )
                    SELECT * FROM forks ORDER BY created_at, id
                """, {'spine_ids': spine_ids, 'user_id': user_id})
                forks = [dict(r) for r in cursor.fetchall()]
                for r in forks:
                    r['owned'] = True  # the fork walk only visits owned rows
                    r['in_spine'] = False
                    r['is_head'] = False

                all_ids = spine_ids + [r['id'] for r in forks]
                cursor.execute("""
                    SELECT head_version_id, id, strategy_name
                    FROM CUSTOM_STRATEGIES
                    WHERE user_id = %(user_id)s AND deleted_at IS NULL
                      AND head_version_id = ANY(%(ids)s)
                """, {'user_id': user_id, 'ids': all_ids})
                heads = {}
                for row in cursor.fetchall():
                    heads.setdefault(row['head_version_id'], []).append(
                        {'id': row['id'], 'name': row['strategy_name']})
                for n in spine + forks:
                    n['heads'] = heads.get(n['id'], [])
                return {'spine': spine, 'forks': forks}
        except Exception as e:
            logging.error(f"Failed to get strategy lineage: {e}", exc_info=True)
            return {'spine': self.get_strategy_versions(strategy_id, user_id),
                    'forks': []}

    # THE visibility boundary of the family tree, defined once so the walks
    # and the hidden-count negation can never drift apart. IS TRUE forms keep
    # the predicate and its negation provably complementary on NULL flags.
    # is_published_to_leaderboard is the product's actual "make public"
    # action; is_public is honored for built-ins and legacy rows.
    _FAMILY_VISIBLE = ("({a}.is_public IS TRUE "
                       "OR {a}.is_published_to_leaderboard IS TRUE "
                       "OR {a}.user_id = 0 OR {a}.user_id = %(user_id)s)")

    @log_db_call
    def get_strategy_family(self, strategy_id, user_id):
        """The strategy-level family tree: root at the highest ancestor
        reachable through VISIBLE strategies (public/published, built-in, or
        the viewer's own), then every visible descendant. Soft-deleted
        visible strategies are kept as flagged pass-through so a trashed
        intermediate never amputates a live branch. Invisible strategies
        never appear — each visible node instead carries hidden_forks, the
        count of its live direct children the viewer may not see. Built-in
        nodes report hidden_forks 0: a platform-wide private-clone tally is
        not something any other surface exposes.

        Returns a list of node dicts ordered root-first; the caller decides
        which parent pointers are safe to expose.
        """
        params = {'strategy_id': strategy_id, 'user_id': user_id}
        visible_p = self._FAMILY_VISIBLE.format(a='p')
        visible_c = self._FAMILY_VISIBLE.format(a='c')
        visible_h = self._FAMILY_VISIBLE.format(a='h')
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor,
                                         commit=False) as cursor:
                cursor.execute(f"""
                    WITH RECURSIVE up AS (
                        SELECT cs.id, cs.parent_strategy_id, 0 AS height
                        FROM CUSTOM_STRATEGIES cs
                        WHERE cs.id = %(strategy_id)s AND cs.deleted_at IS NULL
                        UNION ALL
                        SELECT p.id, p.parent_strategy_id, up.height + 1
                        FROM CUSTOM_STRATEGIES p
                        JOIN up ON p.id = up.parent_strategy_id
                        WHERE up.height < 50
                          AND p.id != up.id  -- corrupt self-link guard
                          AND {visible_p}
                    ),
                    root AS (
                        SELECT id FROM up ORDER BY height DESC LIMIT 1
                    ),
                    tree AS (
                        SELECT cs.id, cs.parent_strategy_id, cs.strategy_name,
                               cs.user_id, cs.is_public,
                               cs.is_published_to_leaderboard, cs.deleted_at,
                               cs.created_at, cs.git_commit_sha,
                               cs.clone_source_commit_sha, 0 AS depth
                        FROM CUSTOM_STRATEGIES cs
                        JOIN root ON cs.id = root.id
                        UNION ALL
                        SELECT c.id, c.parent_strategy_id, c.strategy_name,
                               c.user_id, c.is_public,
                               c.is_published_to_leaderboard, c.deleted_at,
                               c.created_at, c.git_commit_sha,
                               c.clone_source_commit_sha, tree.depth + 1
                        FROM CUSTOM_STRATEGIES c
                        JOIN tree ON c.parent_strategy_id = tree.id
                        WHERE tree.depth < 50
                          AND c.id != tree.id  -- corrupt self-link guard
                          AND {visible_c}
                    )
                    SELECT t.id, t.parent_strategy_id, t.strategy_name,
                           t.created_at, t.depth,
                           (t.deleted_at IS NOT NULL) AS strategy_deleted,
                           (t.user_id = 0) AS is_builtin,
                           (t.user_id = %(user_id)s) AS is_own,
                           (t.is_public IS NOT TRUE
                            AND t.is_published_to_leaderboard IS NOT TRUE
                            AND t.user_id != 0) AS is_private,
                           -- Public author identity: the chosen display name
                           -- only, never an email (the leaderboard applies
                           -- the same rule).
                           CASE WHEN t.user_id = 0 THEN 'built-in'
                                ELSE COALESCE(u.display_name, 'anonymous')
                           END AS owner_name,
                           ev.excellence_score,
                           CASE WHEN t.user_id = 0 THEN 0 ELSE
                               (SELECT COUNT(*) FROM CUSTOM_STRATEGIES h
                                WHERE h.parent_strategy_id = t.id
                                  AND h.deleted_at IS NULL
                                  AND NOT {visible_h})
                           END AS hidden_forks
                    FROM tree t
                    LEFT JOIN USERS u ON u.id = t.user_id
                    LEFT JOIN LATERAL (
                        -- the LATEST evaluation for this content, matching
                        -- what the list/detail surfaces show
                        SELECT excellence_score FROM STRATEGY_EVALUATIONS e
                        WHERE e.git_commit_sha = COALESCE(t.git_commit_sha,
                                                          t.clone_source_commit_sha)
                        ORDER BY e.created_at DESC LIMIT 1
                    ) ev ON TRUE
                    ORDER BY t.depth, t.created_at, t.id
                    LIMIT 201
                """, params)
                rows = [dict(r) for r in cursor.fetchall()]
                # Deleted rows exist only as connective tissue: prune deleted
                # leaves so trashed dead-ends don't clutter the tree.
                while True:
                    parents = {r['parent_strategy_id'] for r in rows}
                    pruned = [r for r in rows
                              if not (r['strategy_deleted']
                                      and r['id'] not in parents
                                      and r['id'] != strategy_id)]
                    if len(pruned) == len(rows):
                        return pruned
                    rows = pruned
        except Exception as e:
            logging.error(f"Failed to get strategy family: {e}", exc_info=True)
            return []

    @log_db_call
    def get_strategy_version(self, version_id):
        """One version node, code included."""
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor,
                                         commit=False) as cursor:
                cursor.execute("""
                    SELECT id, strategy_id, content_hash, code, parameters_json,
                           class_name, parent_version_id, source, request,
                           created_at, created_by_user_id
                    FROM STRATEGY_VERSIONS WHERE id = %s
                """, (version_id,))
                return cursor.fetchone()
        except Exception as e:
            logging.error(f"Failed to get strategy version {version_id}: {e}", exc_info=True)
            return None

    @log_db_call
    def revert_strategy_to_version(self, strategy_id, user_id, version_id):
        """Git-revert style restore: append a NEW head whose content is an
        ancestor version's (history stays append-only), and write that content
        back onto the strategy row. The target must be in the strategy's own
        ancestry (ownership-bounded), so nobody reverts onto arbitrary or
        foreign version nodes.

        Returns {'success': bool, 'error': str|None, 'version_id': int|None}.
        """
        conn = self.get_connection()
        try:
            cursor = self._get_cursor(conn)
            cursor.execute("""
                SELECT cs.user_id, cs.head_version_id, cs.git_commit_sha,
                       hv.content_hash,
                       (cs.code IS NULL AND cs.parent_strategy_id IS NOT NULL)
                           AS is_pure_clone
                FROM CUSTOM_STRATEGIES cs
                LEFT JOIN STRATEGY_VERSIONS hv ON hv.id = cs.head_version_id
                WHERE cs.id = %s AND cs.deleted_at IS NULL
            """, (strategy_id,))
            row = cursor.fetchone()
            if not row:
                return {'success': False, 'error': 'Strategy not found', 'version_id': None}
            owner_id, head_id, row_sha, head_sha, is_pure_clone = row
            if owner_id != user_id:
                logging.warning(
                    "SECURITY: user %s attempted revert on strategy %s owned by %s",
                    user_id, strategy_id, owner_id)
                return {'success': False, 'error': 'Not your strategy', 'version_id': None}
            if not head_id:
                return {'success': False, 'error': 'No version history yet', 'version_id': None}
            if is_pure_clone:
                # An unedited clone TRACKS its parent — writing code onto it
                # would silently materialize it into a fork. (Its NULL hash
                # would otherwise read as a repairable divergence below.)
                return {'success': False,
                        'error': 'This is an unedited clone — it follows its '
                                 'parent. Evolve it first, or restore on the '
                                 'original strategy.',
                        'version_id': None}
            if version_id == head_id and row_sha == head_sha:
                # Restoring the head is a no-op — unless the row's content has
                # somehow diverged from its own head, where the restore is
                # exactly the repair needed.
                return {'success': False, 'error': 'Already the current version', 'version_id': None}
            cursor.execute(self._VERSION_ANCESTRY_SQL + " ORDER BY depth",
                           {'strategy_id': strategy_id, 'user_id': owner_id})
            if version_id not in [r[0] for r in cursor.fetchall()]:
                return {'success': False, 'error': "Not in this strategy's history",
                        'version_id': None}
            cursor.execute("""
                SELECT code, parameters_json, class_name, content_hash, source
                FROM STRATEGY_VERSIONS WHERE id = %s
            """, (version_id,))
            code, parameters_json, class_name, content_hash, source = cursor.fetchone()
            # Reconstructed ('backfill') nodes have unknown parameters (NULL)
            # and code that never ran under the current validator: never wipe
            # the row's params with an unknown, and don't stamp 'validated'
            # on code this system did not validate.
            cursor.execute("""
                UPDATE CUSTOM_STRATEGIES
                SET code = %s, parameters_json = COALESCE(%s, parameters_json),
                    class_name = COALESCE(%s, class_name),
                    git_commit_sha = %s, is_clone_unedited = FALSE,
                    validation_status = CASE WHEN %s = 'backfill'
                                             THEN validation_status
                                             ELSE 'validated' END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (code, parameters_json, class_name, content_hash, source,
                  strategy_id))
            new_version_id = self._record_strategy_version(
                cursor, strategy_id=strategy_id, code=code,
                parameters_json=parameters_json, class_name=class_name,
                content_hash=content_hash, source='revert',
                request=f"Restored version {version_id}", user_id=user_id)
            if new_version_id is None:
                # Version store unavailable (pre-V39): a restore that cannot
                # record itself must not happen at all.
                conn.rollback()
                return {'success': False,
                        'error': 'Version store unavailable', 'version_id': None}
            conn.commit()
            return {'success': True, 'error': None, 'version_id': new_version_id}
        except Exception as e:
            logging.error(f"Failed to revert strategy {strategy_id}: {e}", exc_info=True)
            conn.rollback()
            return {'success': False, 'error': 'Revert failed', 'version_id': None}
        finally:
            self.release_connection(conn)

    @log_db_call
    def set_strategy_published_status(self, strategy_id, user_id, is_published):
        """Toggle whether a custom strategy is published to the leaderboard."""
        try:
            with self._connection_cursor() as cursor:
                # Verify ownership before allowing change
                cursor.execute("""
                    UPDATE CUSTOM_STRATEGIES
                    SET is_published_to_leaderboard = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                """, (is_published, strategy_id, user_id))
                success = cursor.rowcount > 0

            # Clear leaderboard cache when publish status changes
            if success:
                from db.cache import clear_leaderboard_cache
                clear_leaderboard_cache(
                    f"{'publishing' if is_published else 'unpublishing'} strategy {strategy_id}")

            return success
        except Exception as e:
            logging.error(f"Failed to set publish status: {e}", exc_info=True)
            return False

    @log_db_call
    def save_strategy_evaluation(self, evaluation_data):
        """Save strategy evaluation using INSERT...ON CONFLICT."""
        try:
            # Construct parameters dict ensuring all keys required by query exist
            params = {
                'strategy_name': evaluation_data['strategy_name'],
                'git_commit_sha': evaluation_data.get('git_commit_sha'), # KEY for the new architecture
                'user_id': evaluation_data.get('user_id'),
                'is_custom': evaluation_data.get('is_custom', False),
                'custom_strategy_id': evaluation_data.get('custom_strategy_id'),
                'strategy_category': evaluation_data.get('strategy_category', 'Unknown'),
                'excellence_score': evaluation_data.get('excellence_score'),
                'risk_score': evaluation_data.get('risk_score', 0.0),
                'pv_score': evaluation_data.get('pv_score', 0.0),
                'capital_efficiency_score': evaluation_data.get('capital_efficiency_score', 0.0),
                'purchasing_power_score': evaluation_data.get('purchasing_power_score', 0.0),
                'robustness_score': evaluation_data.get('robustness_score', 0.0),
                'consumption_ratio_score': evaluation_data.get('consumption_ratio_score', 0.0),
                'usability_score': evaluation_data.get('usability_score', 0.0),
                'stability_score': evaluation_data.get('stability_score', 0.0),
                'legacy_score': evaluation_data.get('legacy_score', 0.0),
                'sharpe_ratio_score': evaluation_data.get('sharpe_ratio_score'),
                'calmar_ratio_score': evaluation_data.get('calmar_ratio_score'),
                'downside_stability_score': evaluation_data.get('downside_stability_score'),
                'ulcer_index_score': evaluation_data.get('ulcer_index_score'),
                'scenario_results_json': evaluation_data['scenario_results_json']
            }
            # Sanitize numeric types to python native floats for psycopg2 compatibility
            # This handles numpy scalars (np.float64) which psycopg2 confuses for schema objects
            score_keys = [
                'excellence_score', 'risk_score', 'pv_score',
                'capital_efficiency_score', 'purchasing_power_score', 'robustness_score',
                'consumption_ratio_score', 'usability_score', 'stability_score', 'legacy_score',
                'sharpe_ratio_score', 'calmar_ratio_score', 'downside_stability_score', 'ulcer_index_score'
            ]
            for key in score_keys:
                val = params.get(key)
                if val is not None:
                    try:
                        params[key] = float(val)
                    except (ValueError, TypeError):
                        pass # Keep original if casting fails
            
            # Determine which query to use based on presence of git_commit_sha
            if params.get('git_commit_sha'):
                query = self.queries.SAVE_STRATEGY_EVALUATION_BY_SHA
                id_lookup_query = """
                    SELECT id FROM STRATEGY_EVALUATIONS 
                    WHERE git_commit_sha = %s 
                    LIMIT 1
                """
                id_lookup_param = (params['git_commit_sha'],)
            else:
                query = self.queries.SAVE_STRATEGY_EVALUATION_BY_NAME
                id_lookup_query = """
                    SELECT id FROM STRATEGY_EVALUATIONS 
                    WHERE strategy_name = %s AND git_commit_sha IS NULL
                    LIMIT 1
                """
                id_lookup_param = (params['strategy_name'],)

            with self._connection_cursor() as cursor:
                cursor.execute(query, params)

                # --- Get the evaluation_id of the just-inserted/updated row ---
                cursor.execute(id_lookup_query, id_lookup_param)
                row = cursor.fetchone()
                evaluation_id = row[0] if row else None

                # --- NEW: Insert profile scores if evaluation succeeded ---
                if evaluation_id and 'profile_scores' in evaluation_data:
                    for profile_key, score in evaluation_data['profile_scores'].items():
                        try:
                            cursor.execute("""
                                INSERT INTO STRATEGY_PROFILE_SCORES
                                (evaluation_id, profile_key, excellence_score)
                                VALUES (%s, %s, %s)
                                ON CONFLICT (evaluation_id, profile_key)
                                DO UPDATE SET
                                    excellence_score = EXCLUDED.excellence_score,
                                    calculated_at = CURRENT_TIMESTAMP
                            """, (evaluation_id, profile_key, float(score)))
                        except Exception as e:
                            logging.error(f"Failed to insert profile score for {profile_key}: {e}")
                            # Continue with other profiles even if one fails

                    logging.info(f"Saved {len(evaluation_data['profile_scores'])} profile scores for evaluation {evaluation_id}")

            logging.info(f"Successfully saved evaluation for {evaluation_data['strategy_name']}")
            return True  # Return success indicator
        except Exception as e:
            logging.error(f"Failed to save evaluation: {e}", exc_info=True)
            return False  # Return failure indicator

    @log_db_call
    def get_strategy_evaluation(self, git_commit_sha, lookup_fallback_sha=None):
        """
        Get evaluation for specific strategy version by SHA.
        
        Args:
            git_commit_sha: The SHA of the strategy to look up
            lookup_fallback_sha: Optional fallback SHA (e.g. parent SHA for unedited clones)
            
        Returns:
            Dict with evaluation data or None
        """
        if not git_commit_sha and not lookup_fallback_sha:
            return None

        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                # Primary lookup
                result = None
                if git_commit_sha:
                    cursor.execute(self.queries.GET_STRATEGY_EVALUATION_BY_SHA, (git_commit_sha,))
                    result = cursor.fetchone()

                # Fallback lookup (for clones)
                if not result and lookup_fallback_sha:
                    primary_display = git_commit_sha[:7] if git_commit_sha else "None"
                    fallback_display = lookup_fallback_sha[:7] if lookup_fallback_sha else "None"
                    logging.info(f"Primary SHA {primary_display} not found, checking fallback {fallback_display}")
                    cursor.execute(self.queries.GET_STRATEGY_EVALUATION_BY_SHA, (lookup_fallback_sha,))
                    result = cursor.fetchone()

                return result
        except Exception as e:
            logging.error(f"Failed to get evaluation: {e}", exc_info=True)
            return None

    @log_db_call
    def get_all_custom_strategies_for_admin(self):
        """Fetch all custom strategies for admin evaluation."""
        logging.info("Admin: Fetching all custom strategies for evaluation")
        try:
            with self._connection_cursor(cursor_factory=extras.RealDictCursor, commit=False) as cursor:
                cursor.execute("""
                    SELECT
                        cs.id,
                        cs.user_id,
                        cs.strategy_name,
                        cs.class_name,
                        cs.code,
                        cs.description,
                        cs.parameters_json
                    FROM CUSTOM_STRATEGIES cs
                    ORDER BY cs.user_id, cs.strategy_name
                """)
                records = [dict(row) for row in cursor.fetchall()]
            # Use abstraction layer for JSON deserialization
            for row in records:
                if 'parameters_json' in row:
                    row['parameters_json'] = self.deserialize_json_column(row['parameters_json'])
            return records
        except Exception as e:
            logging.error(f"Failed admin fetch: {e}", exc_info=True)
            return []
