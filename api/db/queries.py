"""PostgreSQL query strings used by PostgreSQLDatabase and regeneration_db.

Only queries actually referenced by live code live here. All placeholders are
native psycopg2 style: %s for positional params, %(name)s for dict params.
"""


class PostgreSQLQueries:
    # --- Simulation history / listing ---
    GET_USER_SIMULATIONS_WITH_PARAMS = """
        SELECT DISTINCT
            h.id, h.user_id, h.simulation_name, h.is_removed, c.is_public, h.timestamp,
            u.email,
            c.simulation_hash, c.parameters as all_params, c.status
        FROM USER_SIMULATION_HISTORY h
        JOIN CACHED_SIMULATIONS c ON h.simulation_hash = c.simulation_hash
        LEFT JOIN USERS u ON h.user_id = u.id
        WHERE h.is_removed = FALSE
            AND ((%(email)s IS NOT NULL AND u.email = %(email)s) OR c.is_public = TRUE)
            AND (
                %(email)s IS NULL  -- Anonymous users see all public sims
                OR NOT EXISTS (     -- Logged-in users don't see their hidden items
                    SELECT 1 FROM USER_HIDDEN_ITEMS ahi
                    WHERE ahi.user_id = (SELECT id FROM USERS WHERE email = %(email)s)
                    AND ahi.item_type = 'simulation'
                    AND ahi.item_id = h.id
                )
            )
        ORDER BY h.timestamp DESC
    """

    GET_ALL_SIMULATIONS = """
        SELECT
            h.id, h.user_id, h.simulation_name, h.is_removed, h.timestamp,
            u.email,
            c.status, c.simulation_hash, c.parameters as all_params
        FROM USER_SIMULATION_HISTORY h
        JOIN CACHED_SIMULATIONS c ON h.simulation_hash = c.simulation_hash
        LEFT JOIN USERS u ON h.user_id = u.id
        WHERE h.is_removed = FALSE
        ORDER BY h.timestamp DESC
    """

    HIDE_SHARED_ITEM = """
        INSERT INTO USER_HIDDEN_ITEMS (user_id, item_type, item_id)
        VALUES (%(user_id)s, %(item_type)s, %(item_id)s)
        ON CONFLICT (user_id, item_type, item_id) DO NOTHING
    """

    # --- Asset data / results blob cache (used by regeneration_db.py) ---
    SAVE_ASSET_DATA_CACHE = """
        INSERT INTO ASSET_DATA_CACHE (asset_key, data_blob, updated_at)
        VALUES (%(asset_key)s, %(data_blob)s, CURRENT_TIMESTAMP)
        ON CONFLICT (asset_key)
        DO UPDATE SET data_blob = EXCLUDED.data_blob, updated_at = CURRENT_TIMESTAMP
    """

    LOAD_ASSET_DATA_CACHE = "SELECT data_blob FROM ASSET_DATA_CACHE WHERE asset_key = %(asset_key)s"

    LOAD_SIMULATION_RESULTS_DATA = "SELECT data_blob FROM SIMULATION_RESULTS_DATA WHERE results_id = %(results_id)s AND data_key = %(data_key)s"

    # --- Strategy evaluations ---

    # 1. For Versioned Strategies (Keyed by SHA)
    SAVE_STRATEGY_EVALUATION_BY_SHA = """
        INSERT INTO STRATEGY_EVALUATIONS (
            strategy_name, git_commit_sha, user_id, is_custom, custom_strategy_id, strategy_category,
            excellence_score, risk_score, pv_score,
            capital_efficiency_score, purchasing_power_score, robustness_score,
            consumption_ratio_score, usability_score, stability_score,
            legacy_score,
            sharpe_ratio_score, calmar_ratio_score, downside_stability_score, ulcer_index_score,
            scenario_results_json,
            updated_at
        ) VALUES (
            %(strategy_name)s, %(git_commit_sha)s, %(user_id)s, %(is_custom)s, %(custom_strategy_id)s, %(strategy_category)s,
            %(excellence_score)s, %(risk_score)s, %(pv_score)s,
            %(capital_efficiency_score)s, %(purchasing_power_score)s, %(robustness_score)s,
            %(consumption_ratio_score)s, %(usability_score)s, %(stability_score)s,
            %(legacy_score)s,
            %(sharpe_ratio_score)s, %(calmar_ratio_score)s, %(downside_stability_score)s, %(ulcer_index_score)s,
            %(scenario_results_json)s,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (git_commit_sha) WHERE git_commit_sha IS NOT NULL DO UPDATE SET
            strategy_name = EXCLUDED.strategy_name,
            user_id = EXCLUDED.user_id,
            is_custom = EXCLUDED.is_custom,
            custom_strategy_id = EXCLUDED.custom_strategy_id,
            strategy_category = EXCLUDED.strategy_category,
            excellence_score = EXCLUDED.excellence_score,
            risk_score = EXCLUDED.risk_score,
            pv_score = EXCLUDED.pv_score,
            capital_efficiency_score = EXCLUDED.capital_efficiency_score,
            purchasing_power_score = EXCLUDED.purchasing_power_score,
            robustness_score = EXCLUDED.robustness_score,
            consumption_ratio_score = EXCLUDED.consumption_ratio_score,
            usability_score = EXCLUDED.usability_score,
            stability_score = EXCLUDED.stability_score,
            legacy_score = EXCLUDED.legacy_score,
            sharpe_ratio_score = EXCLUDED.sharpe_ratio_score,
            calmar_ratio_score = EXCLUDED.calmar_ratio_score,
            downside_stability_score = EXCLUDED.downside_stability_score,
            ulcer_index_score = EXCLUDED.ulcer_index_score,
            scenario_results_json = EXCLUDED.scenario_results_json,
            updated_at = CURRENT_TIMESTAMP
    """

    # 2. For Built-in Strategies (Keyed by Name, SHA is NULL)
    SAVE_STRATEGY_EVALUATION_BY_NAME = """
        INSERT INTO STRATEGY_EVALUATIONS (
            strategy_name, git_commit_sha, user_id, is_custom, custom_strategy_id, strategy_category,
            excellence_score, risk_score, pv_score,
            capital_efficiency_score, purchasing_power_score, robustness_score,
            consumption_ratio_score, usability_score, stability_score,
            legacy_score,
            sharpe_ratio_score, calmar_ratio_score, downside_stability_score, ulcer_index_score,
            scenario_results_json,
            updated_at
        ) VALUES (
            %(strategy_name)s, %(git_commit_sha)s, %(user_id)s, %(is_custom)s, %(custom_strategy_id)s, %(strategy_category)s,
            %(excellence_score)s, %(risk_score)s, %(pv_score)s,
            %(capital_efficiency_score)s, %(purchasing_power_score)s, %(robustness_score)s,
            %(consumption_ratio_score)s, %(usability_score)s, %(stability_score)s,
            %(legacy_score)s,
            %(sharpe_ratio_score)s, %(calmar_ratio_score)s, %(downside_stability_score)s, %(ulcer_index_score)s,
            %(scenario_results_json)s,
            CURRENT_TIMESTAMP
        )
        ON CONFLICT (strategy_name) WHERE git_commit_sha IS NULL DO UPDATE SET
            user_id = EXCLUDED.user_id,
            is_custom = EXCLUDED.is_custom,
            custom_strategy_id = EXCLUDED.custom_strategy_id,
            strategy_category = EXCLUDED.strategy_category,
            excellence_score = EXCLUDED.excellence_score,
            risk_score = EXCLUDED.risk_score,
            pv_score = EXCLUDED.pv_score,
            capital_efficiency_score = EXCLUDED.capital_efficiency_score,
            purchasing_power_score = EXCLUDED.purchasing_power_score,
            robustness_score = EXCLUDED.robustness_score,
            consumption_ratio_score = EXCLUDED.consumption_ratio_score,
            usability_score = EXCLUDED.usability_score,
            stability_score = EXCLUDED.stability_score,
            legacy_score = EXCLUDED.legacy_score,
            sharpe_ratio_score = EXCLUDED.sharpe_ratio_score,
            calmar_ratio_score = EXCLUDED.calmar_ratio_score,
            downside_stability_score = EXCLUDED.downside_stability_score,
            ulcer_index_score = EXCLUDED.ulcer_index_score,
            scenario_results_json = EXCLUDED.scenario_results_json,
            updated_at = CURRENT_TIMESTAMP
    """

    GET_STRATEGY_EVALUATION_BY_SHA = """
        SELECT
            e.*,
            cs.ai_description,
            cs.description as custom_description
        FROM STRATEGY_EVALUATIONS e
        LEFT JOIN CUSTOM_STRATEGIES cs ON e.is_custom = TRUE AND e.custom_strategy_id = cs.id
        WHERE e.git_commit_sha = %s
        ORDER BY e.updated_at DESC
        LIMIT 1
    """
