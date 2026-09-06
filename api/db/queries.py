class SQLiteQueries:
    CREATE_SCHEMA_VERSION_TABLE = "CREATE TABLE IF NOT EXISTS schema_version (version TEXT PRIMARY KEY, applied_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    SAVE_CUSTOM_STRATEGY = """
        INSERT OR REPLACE INTO CUSTOM_STRATEGIES (
            user_id, strategy_name, class_name, description, ai_description, code, parameters_json, 
            validation_status, validation_error, last_validation_timestamp,
            parent_strategy_id, clone_source_commit_sha, git_branch_name, git_commit_sha
        )
        VALUES (
            :user_id, :strategy_name, :class_name, :description, :ai_description, :code, :parameters_json, 
            :validation_status, :validation_error, :last_validation_timestamp,
            :parent_strategy_id, :clone_source_commit_sha, :git_branch_name, :git_commit_sha
        );
    """
    GET_APPLIED_MIGRATIONS = "SELECT version FROM schema_version"
    INSERT_MIGRATION_VERSION = "INSERT INTO schema_version (version) VALUES (:version)"
    INSERT_SIMULATION = """
        INSERT INTO SIMULATIONS (strategy, asset_model, num_years, num_simulations, 
                                initial_investment, user_id, simulation_name, 
                                pdf_report_path)
        VALUES (:strategy, :asset_model, :num_years, :num_simulations, 
                :initial_investment, :user_id, :simulation_name, 
                :pdf_report_path)
    """
    INSERT_SIMULATION_PARAMETERS = "INSERT INTO SIMULATION_PARAMETERS (simulation_id, parameters) VALUES (:simulation_id, :parameters)"
    INSERT_AI_ANALYSIS = """
        INSERT INTO AI_ANALYSIS (simulation_id, analysis_content, main_outcome_content, bottom_line_content)
        VALUES (:simulation_id, :analysis, :main_outcome, :bottom_line)
    """
    INSERT_STATISTICS = """
        INSERT INTO STATISTICS (simulation_id, median_final_net_worth, mean_final_net_worth, p5_final_net_worth,
                                p10_final_net_worth, p25_final_net_worth, p75_final_net_worth,
                                p90_final_net_worth, p95_final_net_worth, chance_of_ruin,
                                chance_of_profit, chance_of_real_profit, success_rate,
                                median_year_of_ruin, median_total_withdrawn,
                                median_real_final_net_worth, median_years_of_spending_left,
                                chance_of_nominal_loss, chance_drawdown_capped,
                                chance_drawdown_suspended, median_accumulated_interest,
                                median_accumulated_tax, median_accumulated_fees,
                                median_final_ltv, p50_max_ltv, p75_max_ltv, p90_max_ltv, 
                                strategy_sharpe_ratio, strategy_sortino_ratio,
                                asset_sharpe_ratio, asset_sortino_ratio, var_95_loss, cvar_95_loss,
                                asset_ulcer_index, median_strategy_ulcer_index, mean_strategy_ulcer_index,
                                median_time_underwater, median_recovery_time, p90_consecutive_declines,
                                median_severe_drawdown_count, median_years_below_initial,
                                risk_score, risk_return_score, all_stats)
        SELECT :simulation_id, :median_final_net_worth, :mean_final_net_worth, :p5_final_net_worth,
            :p10_final_net_worth, :p25_final_net_worth, :p75_final_net_worth,
            :p90_final_net_worth, :p95_final_net_worth, :chance_of_ruin,
            :chance_of_profit, :chance_of_real_profit, :success_rate, :median_year_of_ruin,
            :median_total_withdrawn, :median_real_final_net_worth, :median_years_of_spending_left,
            :chance_of_nominal_loss, :chance_drawdown_capped, :chance_drawdown_suspended,
            :median_accumulated_interest, :median_accumulated_tax, :median_accumulated_fees, :median_final_ltv,
            :p50_max_ltv, :p75_max_ltv, :p90_max_ltv, :strategy_sharpe_ratio, :strategy_sortino_ratio,
            :asset_sharpe_ratio, :asset_sortino_ratio, :var_95_loss, :cvar_95_loss, 
            :asset_ulcer_index, :median_strategy_ulcer_index, :mean_strategy_ulcer_index,
            :median_time_underwater, :median_recovery_time, :p90_consecutive_declines,
            :median_severe_drawdown_count, :median_years_below_initial,
            :risk_score, :risk_return_score, :all_stats
    """
    GET_USER_SIMULATIONS = """
        SELECT h.id, h.simulation_name, h.timestamp, c.status, c.simulation_hash
        FROM USER_SIMULATION_HISTORY h
        JOIN CACHED_SIMULATIONS c ON h.simulation_hash = c.simulation_hash
        WHERE h.user_id = (SELECT id FROM USERS WHERE email = ?) AND h.is_removed = FALSE
        ORDER BY h.timestamp DESC
    """
    GET_USER_ID = "SELECT id FROM USERS WHERE email = :email"
    INSERT_USER = "INSERT INTO USERS (email, name) VALUES (:email, :name)"
    GET_USER_SIMULATIONS_WITH_PARAMS = """
        SELECT 
            h.id, h.user_id, h.simulation_name, h.is_removed, c.is_public, h.timestamp,
            u.email,
            c.simulation_hash, c.parameters as all_params, c.status
        FROM USER_SIMULATION_HISTORY h
        JOIN CACHED_SIMULATIONS c ON h.simulation_hash = c.simulation_hash
        LEFT JOIN USERS u ON h.user_id = u.id
        WHERE h.is_removed = FALSE 
            AND ((? IS NOT NULL AND u.email = ?) OR c.is_public = TRUE)
        ORDER BY h.timestamp DESC
    """
    DELETE_USER_HISTORY_ENTRY = "DELETE FROM USER_SIMULATION_HISTORY WHERE id = ?"
    MARK_SIMULATION_AS_REMOVED = "UPDATE USER_SIMULATION_HISTORY SET is_removed = TRUE WHERE id = ?"
    DELETE_AI_ANALYSIS = "DELETE FROM AI_ANALYSIS WHERE simulation_id = :sim_id"
    DELETE_STATISTICS = "DELETE FROM STATISTICS WHERE simulation_id = :sim_id"
    DELETE_SIMULATION_PARAMETERS = "DELETE FROM SIMULATION_PARAMETERS WHERE simulation_id = :sim_id"
    DELETE_SIMULATION_RESULTS_DATA = "DELETE FROM SIMULATION_RESULTS_DATA WHERE simulation_id = :sim_id"
    DELETE_SIMULATION = "DELETE FROM SIMULATIONS WHERE id = :sim_id"
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
    GET_SIMULATION_DETAILS = """
        SELECT 
            s.id, s.user_id, s.strategy, s.asset_model, s.num_years, 
            s.num_simulations, s.initial_investment, s.simulation_name, 
            s.pdf_report_path, s.is_removed, s.timestamp,
            p.parameters as all_params
        FROM SIMULATIONS s
        LEFT JOIN SIMULATION_PARAMETERS p ON s.id = p.simulation_id
        WHERE s.id = :simulation_id
    """
    GET_STATISTICS = "SELECT * FROM STATISTICS WHERE simulation_id = :simulation_id"

    GET_USER_CUSTOM_STRATEGIES = """
        SELECT * FROM CUSTOM_STRATEGIES 
        WHERE (user_id = :user_id OR is_public = TRUE)
        AND NOT EXISTS (
            SELECT 1 FROM USER_HIDDEN_ITEMS ahi 
            WHERE ahi.user_id = :user_id 
            AND ahi.item_type = 'strategy' 
            AND ahi.item_id = CUSTOM_STRATEGIES.id
        )
        ORDER BY updated_at DESC
    """
    GET_CUSTOM_STRATEGY = "SELECT * FROM CUSTOM_STRATEGIES WHERE id = ?"
    DELETE_CUSTOM_STRATEGY = "DELETE FROM CUSTOM_STRATEGIES WHERE id = :strategy_id AND user_id = :user_id"
    UPDATE_CUSTOM_STRATEGY_DETAILS = """
        UPDATE CUSTOM_STRATEGIES
        SET strategy_name = :strategy_name,
            description = :description,
            ai_description = :ai_description,
            parameters_json = :parameters_json,
            git_branch_name = :git_branch_name,
            git_commit_sha = :git_commit_sha,
            updated_at = CURRENT_TIMESTAMP()
        WHERE id = :strategy_id AND user_id = :user_id
    """
    SAVE_ASSET_DATA_CACHE = """
        INSERT OR REPLACE INTO ASSET_DATA_CACHE (asset_key, data_blob, updated_at)
        VALUES (:asset_key, :data_blob, CURRENT_TIMESTAMP)
    """
    LOAD_ASSET_DATA_CACHE = "SELECT data_blob FROM ASSET_DATA_CACHE WHERE asset_key = :asset_key"
    LOAD_SIMULATION_RESULTS_DATA = "SELECT data_blob FROM SIMULATION_RESULTS_DATA WHERE results_id = :results_id AND data_key = :data_key"
    # --- New Global Cache Queries (SQLite Dialect) ---
    CHECK_SIMULATION_CACHE = "SELECT status, results_id, component_hashes FROM CACHED_SIMULATIONS WHERE simulation_hash = :simulation_hash"
    ADD_TO_USER_HISTORY = "INSERT INTO USER_SIMULATION_HISTORY (user_id, simulation_hash, simulation_name) VALUES (:user_id, :simulation_hash, :simulation_name)" # noqa
    # --- FIX: Use INSERT OR IGNORE to prevent race conditions ---
    # If two processes check the cache, find a miss, and then both try to create the entry,
    # the second one will fail with a UNIQUE constraint error. INSERT OR IGNORE gracefully handles this.
    CREATE_CACHED_SIMULATION_ENTRY = "INSERT OR IGNORE INTO CACHED_SIMULATIONS (simulation_hash, parameters, status) VALUES (:simulation_hash, :parameters, 'PENDING')"
    UPDATE_CACHED_SIMULATION_PARAMS = "UPDATE CACHED_SIMULATIONS SET parameters = :parameters, updated_at = CURRENT_TIMESTAMP WHERE simulation_hash = :simulation_hash"

    UPDATE_CACHED_SIMULATION_STATUS = "UPDATE CACHED_SIMULATIONS SET status = :status, updated_at = CURRENT_TIMESTAMP WHERE simulation_hash = :simulation_hash"
    INSERT_SIMULATION_RESULTS = "INSERT INTO SIMULATION_RESULTS (stats, gemini_content, pdf_status) VALUES (:stats, :gemini_content, NULL)"
    # GET_LAST_RESULTS_ID is handled by cursor.lastrowid in SQLite
    LINK_RESULTS_TO_CACHE = "UPDATE CACHED_SIMULATIONS SET status = 'COMPLETED', results_id = :results_id, updated_at = CURRENT_TIMESTAMP WHERE simulation_hash = :simulation_hash"
    INSERT_RESULTS_DATA_BLOB = "INSERT INTO SIMULATION_RESULTS_DATA (results_id, data_key, data_blob) VALUES (:results_id, :data_key, :data_blob)"

class PostgreSQLQueries(SQLiteQueries):
    """PostgreSQL-specific query overrides."""
    
    # Override SQLite-specific UPSERT syntax
    SAVE_ASSET_DATA_CACHE = """
        INSERT INTO ASSET_DATA_CACHE (asset_key, data_blob, updated_at)
        VALUES (:asset_key, :data_blob, CURRENT_TIMESTAMP)
        ON CONFLICT (asset_key) 
        DO UPDATE SET data_blob = EXCLUDED.data_blob, updated_at = CURRENT_TIMESTAMP
    """
    
    # Override INSERT OR IGNORE with PostgreSQL's ON CONFLICT DO NOTHING
    CREATE_CACHED_SIMULATION_ENTRY = """
        INSERT INTO CACHED_SIMULATIONS (simulation_hash, parameters, status) 
        VALUES (:simulation_hash, :parameters, 'PENDING')
        ON CONFLICT (simulation_hash) DO NOTHING
    """
    
    # PostgreSQL-specific strategy evaluation UPSERT (SHA-keyed)
    # PostgreSQL-specific strategy evaluation UPSERTs
    
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

    # PostgreSQL specific: Use %(email)s instead of ? for named parameters (passed as dict)
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
    
    # PostgreSQL specific: Use %s instead of ? for positional parameters
    GET_USER_SIMULATIONS = """
        SELECT h.id, h.simulation_name, h.timestamp, c.status, c.simulation_hash
        FROM USER_SIMULATION_HISTORY h
        JOIN CACHED_SIMULATIONS c ON h.simulation_hash = c.simulation_hash
        WHERE h.user_id = (SELECT id FROM USERS WHERE email = %s) AND h.is_removed = FALSE
        ORDER BY h.timestamp DESC
    """
    
    # Also override GET_USER_ID which uses named param :email in Snowflake but ? in SQLite
    # Since PG code passes dict {'email': ...}, we need %(email)s
    GET_USER_ID = "SELECT id FROM USERS WHERE email = %(email)s"

    HIDE_SHARED_ITEM = """
        INSERT INTO USER_HIDDEN_ITEMS (user_id, item_type, item_id)
        VALUES (%(user_id)s, %(item_type)s, %(item_id)s)
        ON CONFLICT (user_id, item_type, item_id) DO NOTHING
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