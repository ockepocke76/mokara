import abc
from datetime import datetime, date
import pandas as pd
from typing import Optional, Tuple, List, Dict, Any

class Dialect(abc.ABC):
    """
    Abstract base class for dialect-specific functions.
    """

    @abc.abstractmethod
    def json_parse(self, column):
        """Parses a JSON column."""
        pass

class DatabaseInterface(abc.ABC):
    """
    Abstract base class defining the interface for database operations.
    This allows for multiple database backends (e.g., Snowflake, SQLite, PostgreSQL)
    to be used interchangeably.
    
    All methods are abstract to enforce implementation in concrete classes.
    """

    def __init__(self, queries):
        self.queries = queries

    # ========== JSON Handling ==========
    
    @abc.abstractmethod
    def deserialize_json_column(self, value: Any) -> Any:
        """
        Deserializes a JSON column value to dict/list.
        
        Some databases return JSON columns as strings, others as dicts.
        This method normalizes the behavior across all backends.
        
        Args:
            value: The column value (string or already-deserialized dict/list)
            
        Returns:
            dict/list if value represents JSON, unchanged otherwise
        """
        pass

    # ========== Migrations ==========

    @abc.abstractmethod
    def run_migrations(self, conn=None):
        """Applies database migrations."""
        pass

    # ========== Simulation Results ==========

    @abc.abstractmethod
    def save_simulation_results(self, params, ui_params, stats, results_dataframe, 
                                average_results_df, median_yearly_results_df, 
                                gemini_content, user_id=None):
        """Saves the results of a simulation."""
        pass

    @abc.abstractmethod
    def get_simulation_details(self, simulation_hash: str) -> Tuple[Optional[Dict], Optional[Dict], Optional[int]]:
        """
        Fetches details for a specific simulation.
        
        Returns:
            Tuple of (params, stats, results_id) or (None, None, None) if not found
        """
        pass

    # ========== User Management ==========

    @abc.abstractmethod
    def get_or_create_user_id(self, user_email: str, user_name: str) -> int:
        """
        Gets or creates a user ID.
        
        Returns:
            user_id (int)
        """
        pass

    # ========== User Simulation History ==========

    @abc.abstractmethod
    def get_user_simulations(self, user_email: str) -> List[Dict]:
        """Fetches all simulations for a given user."""
        pass

    @abc.abstractmethod
    def get_user_simulations_with_params(self, user_email: str) -> List[Dict]:
        """
        DEPRECATED: Use get_user_simulations instead.
        Fetches user simulations with their parameters.
        """
        pass

    @abc.abstractmethod
    def add_to_user_history(self, user_id: int, simulation_hash: str, simulation_name: str) -> int:
        """
        Add simulation to user history.
        
        Returns:
            history_id (int)
        """
        pass

    @abc.abstractmethod
    def mark_simulation_as_removed(self, simulation_id: int):
        """Marks a simulation as removed (soft delete)."""
        pass

    @abc.abstractmethod
    def permanently_delete_simulation(self, simulation_id: int):
        """Permanently deletes a simulation."""
        pass

    # ========== Simulation Cache ==========

    @abc.abstractmethod
    def check_simulation_cache(self, simulation_hash: str) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """
        Check simulation cache.
        
        Returns:
            Tuple of (status, results_id, component_hashes) or (None, None, None) if not found
        """
        pass

    @abc.abstractmethod
    def create_cached_simulation_entry(self, simulation_hash: str, params: Dict):
        """Creates a new cached simulation entry with PENDING status."""
        pass

    @abc.abstractmethod
    def update_cached_simulation_params(self, simulation_hash: str, params: Dict):
        """Updates the parameters of a cached simulation."""
        pass

    @abc.abstractmethod
    def update_cached_simulation_status(self, simulation_hash: str, status: str):
        """Updates the status of a cached simulation."""
        pass

    @abc.abstractmethod
    def update_cached_simulation_results(self, simulation_hash: str, stats: Dict, 
                                        precalculated_data: Dict, status: str = 'COMPLETED',
                                        evaluation_data: Optional[Dict] = None):
        """Updates a cached simulation with results."""
        pass

    # ========== Custom Strategies ==========

    @abc.abstractmethod
    def save_custom_strategy(self, user_id: int, strategy_name: str, class_name: str, 
                            description: str, ai_description: str, code: str, parameters_json: str,
                            validation_status: str = 'not_checked', validation_error: str = None,
                            last_validation_timestamp: str = None, strategy_id: int = None,
                            parent_strategy_id: int = None, clone_source_commit_sha: str = None,
                            git_branch_name: str = None, git_commit_sha: str = None,
                            evolution_request: str = None):
        """Saves a custom strategy."""
        pass

    @abc.abstractmethod
    def get_user_custom_strategies(self, user_id: int) -> List[Dict]:
        """Fetches all custom strategies for a user."""
        pass

    @abc.abstractmethod
    def get_custom_strategy(self, strategy_id: int) -> Optional[Dict]:
        """Fetches a specific custom strategy by ID."""
        pass

    @abc.abstractmethod
    def delete_custom_strategy(self, strategy_id: int, user_id: int):
        """Deletes a custom strategy."""
        pass

    @abc.abstractmethod
    def soft_delete_custom_strategy(self, strategy_id: int, user_id: int) -> bool:
        """
        Soft deletes a custom strategy by setting deleted_at timestamp.
        
        Args:
            strategy_id: ID of the strategy to delete
            user_id: ID of the user (for ownership verification)
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abc.abstractmethod
    def restore_custom_strategy(self, strategy_id: int, user_id: int) -> bool:
        """
        Restores a soft-deleted strategy by clearing deleted_at timestamp.
        
        Args:
            strategy_id: ID of the strategy to restore
            user_id: ID of the user (admin check should be done by caller)
            
        Returns:
            True if successful, False otherwise
        """
        pass

    @abc.abstractmethod
    def update_custom_strategy(self, strategy_id: int, user_id: int, strategy_name: str, 
                              description: str, parameters_json: str,
                              git_branch_name: str = None, git_commit_sha: str = None):
        """Updates a custom strategy's details."""
        pass

    @abc.abstractmethod
    def get_strategy_evolution_history(self, strategy_id: int) -> List[Dict]:
        """Fetches evolution history for a strategy from Git metadata."""
        pass

    @abc.abstractmethod
    def increment_fork_count(self, strategy_id: int):
        """Increments the fork count for a strategy."""
        pass

    @abc.abstractmethod
    def save_strategy_evaluation(self, user_id: int, strategy_name: str, is_custom: bool,
                                custom_strategy_id: Optional[int], strategy_category: str,
                                metrics: Dict):
        """Saves strategy evaluation metrics to leaderboard."""
        pass

    # ========== Leaderboard ==========

    @abc.abstractmethod
    def get_leaderboard(self, category: Optional[str] = None, limit: int = 50) -> List[Dict]:
        """Fetch leaderboard, optionally filtered by category."""
        pass

    @abc.abstractmethod
    def get_all_custom_strategies_for_admin(self) -> List[Dict]:
        """Fetch all custom strategies for admin evaluation."""
        pass

    # ========== General ==========

    @abc.abstractmethod
    def get_all_simulations(self) -> List[Dict]:
        """Fetches all simulations."""
        pass

    @abc.abstractmethod
    def cleanup_old_simulations(self, days_old: int = 90):
        """Cleans up old simulations."""
        pass

    # ========== PDF Storage ==========

    @abc.abstractmethod
    def get_pdf_info_by_hash(self, simulation_hash: str) -> Optional[Dict]:
        """Get PDF information for a simulation hash."""
        pass

    @abc.abstractmethod
    def update_simulation_pdf_storage(self, simulation_hash: str, storage_path: Optional[str],
                                     status: str, error_msg: Optional[str] = None,
                                     gen_time_ms: Optional[int] = None):
        """Update PDF storage information for a simulation."""
        pass

    @abc.abstractmethod
    def get_simulations_needing_pdf(self, limit: int = 10) -> List[Dict]:
        """Get simulations that need PDF generation."""
        pass

    # ========== Admin Management ==========
    
    @abc.abstractmethod
    def ensure_admin_user_exists(self):
        """
        Ensures at least one admin user exists.
        If no users have ADMIN tier, assigns it to the bootstrap admin email.
        """
        pass

    @abc.abstractmethod
    def get_database_info(self) -> Dict[str, Any]:
        """
        Returns connection information about the current database.
        
        Returns:
            dict: { 'host': ..., 'database': ..., 'port': ..., 'user': ... }
        """
        pass
