
import pytest
import psycopg2
import uuid
import json
import logging
from datetime import datetime
from db.postgresql_db import PostgreSQLDatabase
from db.queries import SQLiteQueries
import pandas as pd
import random

# Configure logging
logging.basicConfig(level=logging.INFO)

# Configuration for test DB
TEST_DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'user': 'oscarsverud', 
    'password': '',
    'database': 'postgres'
}

@pytest.fixture(scope="module")
def db_config():
    """Create a unique test database and yield its config."""
    # 1. Connect to default DB
    conn = psycopg2.connect(**TEST_DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    test_db_name = f"test_btc_sim_{str(uuid.uuid4()).replace('-', '')[:10]}"
    logging.info(f"Creating test database: {test_db_name}")
    
    cursor.execute(f"CREATE DATABASE {test_db_name}")
    cursor.close()
    conn.close()
    
    # 2. Return config
    config = TEST_DB_CONFIG.copy()
    config['database'] = test_db_name
    
    yield config
    
    # 3. Teardown
    logging.info(f"Dropping test database: {test_db_name}")
    conn = psycopg2.connect(**TEST_DB_CONFIG)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    # Force kill connections to allow dropping
    cursor.execute(f"""
        SELECT pg_terminate_backend(pid) 
        FROM pg_stat_activity 
        WHERE datname = '{test_db_name}' AND pid <> pg_backend_pid()
    """)
    
    cursor.execute(f"DROP DATABASE {test_db_name}")
    cursor.close()
    conn.close()

@pytest.fixture(scope="module")
def db(db_config):
    """Initialize PostgreSQLDatabase with test DB and run migrations."""
    from db.queries import PostgreSQLQueries
    db_instance = PostgreSQLDatabase(PostgreSQLQueries(), db_config)
    db_instance.run_migrations()
    yield db_instance
    # Close pool explicitly
    if hasattr(db_instance, 'pool') and db_instance.pool:
        db_instance.pool.closeall()

class TestPostgreSQLFull:
    
    def test_01_user_lifecycle(self, db):
        """Test creating users and updating tiers."""
        email = "integration_test@example.com"
        name = "Test User"
        
        # 1. Create
        user_id = db.get_or_create_user_id(email, name)
        assert isinstance(user_id, int)
        
        # 2. Update Tier
        db.update_user_tier(user_id, "PREMIUM", "system_test", "integration test")
        updated_tier = db.get_user_tier(user_id)
        assert updated_tier == "PREMIUM"

    def test_02_custom_strategies(self, db):
        """Test custom strategy CRUD."""
        # Retrieve user created in previous test
        user_id = db.get_or_create_user_id("integration_test@example.com", "Test User")
        
        strategy_name = f"Test Strat {random.randint(1000,9999)}"
        
        # 1. Save
        db.save_custom_strategy(
            user_id=user_id,
            strategy_name=strategy_name,
            class_name="MyClass",
            description="Test Description",
            ai_description="AI Description",
            code="class MyClass: pass",
            parameters_json='{"a": 1}',
            validation_status='draft'
        )
        
        # 2. Get
        strats = db.get_user_custom_strategies(user_id)
        my_strat = next((s for s in strats if s['strategy_name'] == strategy_name), None)
        assert my_strat is not None

    def test_03_simulations_and_cache(self, db):
        """Test simulation saving, caching, and retrieval."""
        user_id = db.get_or_create_user_id("integration_test@example.com", "Test User")
        sim_hash = f"hash_{random.randint(100000, 999999)}"
        
        # 1. Check cache miss
        status, res_id, comp_hashes = db.check_simulation_cache(sim_hash)
        assert status is None
        
        # 2. Create entry and results
        db.create_cached_simulation_entry(sim_hash, {"p": 1})
        
        # Verify creation worked
        status_check, _, _ = db.check_simulation_cache(sim_hash)
        assert status_check == 'PENDING', f"Failed to create cache entry! Status: {status_check}"

        # Dummy data with proper MultiIndex structure matching real simulations
        stats = {"final_balance": 1000}
        # Create MultiIndex DataFrame - (Year, Metric) index, multiple simulation columns
        years = [0, 1, 2]
        metrics = ['Asset Value', 'Net Worth', 'Cash', 'Debt', 'Consumption Delivered', 'Amount Sold', 'Accumulated Interest', 'Accumulated Tax', 'Accumulated Fees']
        index = pd.MultiIndex.from_product([years, metrics], names=['Year', 'Metric'])
        # Create 3 simulation columns with dummy data
        df = pd.DataFrame({
            'Sim_0': [1000000] * len(index),
            'Sim_1': [1100000] * len(index),
            'Sim_2': [900000] * len(index)
        }, index=index)
        
        results_id = db.update_cached_simulation_results(
            sim_hash, {"p": 1, "num_simulations": 3}, {"ui": 1}, stats, df, df, df, "Gemini Content"
        )
        assert results_id is not None
        
        # 3. Check cache hit
        status, res_id, comp_hashes = db.check_simulation_cache(sim_hash)
        assert status == 'COMPLETED', f"Status not COMPLETED. Got: {status}"
        
        # 4. Add to history
        db.add_to_user_history(user_id, sim_hash, "My Simulation")
        
        # 5. Get user simulations
        user_sims = db.get_user_simulations("integration_test@example.com")
        assert len(user_sims) >= 1
        
        # Verify result is in there
        hashes = [s['simulation_hash'] for s in user_sims]
        assert sim_hash in hashes

    def test_04_pdf_and_cleanup(self, db):
        """Test PDF flagging and simulation cleanup."""
        # Uses data from test_03. In database context, simulations persist.
        # But we need to make sure the simulation result created has pdf_status='pending'.
        # Assuming defaults in schema.
        
        needing_pdf = db.get_simulations_needing_pdf(limit=10)
        # Should be at least 1 from previous test
        assert len(needing_pdf) >= 1
        
        sim_hash = needing_pdf[0]['simulation_hash']
        db.update_simulation_pdf_storage(sim_hash, "/storage/path", "completed")
        
        # Should be gone from pending queue
        needing_pdf_after = db.get_simulations_needing_pdf(limit=10)
        hashes = [x['simulation_hash'] for x in needing_pdf_after]
        assert sim_hash not in hashes

    def test_05_additional_coverage(self, db):
        """Test remaining abstract methods (details, removal, delete)."""
        email = "integration_test@example.com"
        
        # 1. Get Simulation Details (verify blob hydration)
        user_sims = db.get_user_simulations(email)
        assert len(user_sims) > 0
        sim = user_sims[0]
        sim_hash = sim['simulation_hash']
        sim_id = sim['id'] # history id
        
        # Note: get_simulation_details expects simulation_hash usually? 
        loaded_params, loaded_stats, res_id = db.get_simulation_details(sim_hash)
        assert loaded_params is not None
        assert loaded_stats is not None
        assert res_id is not None
        
        # 2. Get User Simulations With Params
        sims_with_params = db.get_user_simulations_with_params(email)
        assert len(sims_with_params) > 0
        # Query uses 'all_params' alias
        assert 'all_params' in sims_with_params[0]
        
        # 3. Mark as Removed (Soft Delete)
        # This operates on USER_SIMULATION_HISTORY id
        db.mark_simulation_as_removed(sim_id)
        
        # Verify in DB directly (bypass Streamlit cache)
        conn = db.get_connection()
        try:
            cursor = conn.cursor() # Wrapper returns wrapper
            # Use internal cursor for raw access or just use wrapper
            cursor.execute("SELECT is_removed FROM USER_SIMULATION_HISTORY WHERE id = %s", (sim_id,))
            row = cursor.fetchone()
            assert row is not None
            # row is tuple (is_removed,) or dict? 
            # Wrapper delegates everything. Default cursor is tuple.
            # But get_connection usually has default cursor factory? 
            # get_cursor in db class sets factory.
            # Here we called conn.cursor(). Default psycopg2 is tuple.
            # But PostgreSQLConnection.cursor delegates to _conn.cursor.
            # So it returns tuple.
            assert row[0] is True
        finally:
            db.release_connection(conn)
        
        # 4. Permanently Delete
        # Create a throwaway simulation for this to avoid emptying DB entirely
        new_hash = f"delete_me_{random.randint(1000,9999)}"
        db.create_cached_simulation_entry(new_hash, {"p": 2})
        user_id = db.get_or_create_user_id(email, "Test User")
        history_id = db.add_to_user_history(user_id, new_hash, "To Delete")
        
        db.permanently_delete_simulation(history_id)
        
        # Verify gone from DB directly
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT count(*) FROM USER_SIMULATION_HISTORY WHERE id = %s", (history_id,))
            count = cursor.fetchone()[0]
            assert count == 0
        finally:
            db.release_connection(conn)

    def test_06_admin_and_leaderboard(self, db):
        """Test admin strategies and leaderboard."""
        # 1. Get Admin Strategies
        # Should have at least one from test_02
        admin_strats = db.get_all_custom_strategies_for_admin()
        assert len(admin_strats) >= 1
        assert 'parameters_json' in admin_strats[0]
        
        # 2. Get Leaderboard (Empty initially acceptable, just checking no crash)
        leaderboard = db.get_leaderboard(limit=10)
        assert isinstance(leaderboard, list)
        
        # 3. Check columns exist in leaderboard query (by checking V8 applied implicitly via success)
        # If V8 didn't run, get_leaderboard would crash with "column does not exist"

    def test_07_protect_public_content_deletion(self, db):
        """Test that public simulations and strategies cannot be deleted."""
        user_id = db.get_or_create_user_id("integration_test@example.com", "Test User")
        
        # ====== Test 1: Public Simulation Protection ======
        public_sim_hash = f"public_sim_{random.randint(1000,9999)}"
        db.create_cached_simulation_entry(public_sim_hash, {"test": 1})
        
        # Mark simulation as public at CACHED_SIMULATIONS level
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE CACHED_SIMULATIONS SET is_public = TRUE WHERE simulation_hash = %s",
            (public_sim_hash,)
        )
        conn.commit()
        db.release_connection(conn)
        
        # Try to delete from CACHED_SIMULATIONS - should be blocked by trigger
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            with pytest.raises(Exception) as exc_info:
                cursor.execute("DELETE FROM CACHED_SIMULATIONS WHERE simulation_hash = %s", (public_sim_hash,))
            assert "Cannot delete public simulation" in str(exc_info.value)
        finally:
            conn.rollback()  # Rollback the failed transaction
            db.release_connection(conn)
        
        # ====== Test 2: Public Strategy Protection ======
        strategy_name = f"Public Strategy {random.randint(1000,9999)}"
        db.save_custom_strategy(
            user_id=user_id,
            strategy_name=strategy_name,
            class_name="PublicClass",
            description="Test Public Strategy",
            ai_description="AI Description",
            code="class PublicClass: pass",
            parameters_json='{"public": true}',
            validation_status='draft'
        )
        
        # Force commit by getting a fresh connection (test ordering fix)
        # Previous tests may have left uncommitted transactions
        conn = db.get_connection()
        try:
            conn.commit()
        finally:
            db.release_connection(conn)
        
        # Get the strategy ID
        strats = db.get_user_custom_strategies(user_id)
        public_strat = next((s for s in strats if s['strategy_name'] == strategy_name), None)
        assert public_strat is not None
        strat_id = public_strat['id']
        
        # Mark as public
        conn = db.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE CUSTOM_STRATEGIES SET is_public = TRUE WHERE id = %s",
            (strat_id,)
        )
        conn.commit()
        db.release_connection(conn)
        
        # Try to delete - should be blocked by trigger
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            with pytest.raises(Exception) as exc_info:
                cursor.execute("DELETE FROM CUSTOM_STRATEGIES WHERE id = %s", (strat_id,))
            assert "Cannot delete public" in str(exc_info.value)
        finally:
            conn.rollback()
            db.release_connection(conn)
        
        # ====== Test 3: Verify Non-Public Content CAN Be Deleted ======
        private_sim_hash = f"private_sim_{random.randint(1000,9999)}"
        db.create_cached_simulation_entry(private_sim_hash, {"test": 1})
        
        # This should succeed (no trigger block)
        conn = db.get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM CACHED_SIMULATIONS WHERE simulation_hash = %s", (private_sim_hash,))
            conn.commit()
            
            # Verify deletion worked
            cursor.execute("SELECT COUNT(*) FROM CACHED_SIMULATIONS WHERE simulation_hash = %s", (private_sim_hash,))
            count = cursor.fetchone()[0]
            assert count == 0
        finally:
            db.release_connection(conn)

    def test_08_database_info(self, db):
        """Test get_database_info method."""
        info = db.get_database_info()
        assert isinstance(info, dict)
        assert 'host' in info
        assert 'database' in info
        assert 'port' in info
        assert 'user' in info
