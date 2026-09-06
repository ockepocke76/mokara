"""
Evaluation Strategy Wrapper

Wraps user/built-in strategies to enforce standardized evaluation parameters
while preserving the strategy's core allocation logic.
"""

import logging
from typing import Dict
from core.strategy import BaseStrategy
from core.sandbox import _normalize_key  # Reuse the key normalization from sandbox


class EvaluationStrategyWrapper(BaseStrategy):
    """
    Wraps a strategy to enforce standardized evaluation constraints.
    
    This wrapper intercepts strategy method calls and overrides contribution/
    withdrawal behavior based on the evaluation category, while delegating
    allocation decisions to the base strategy.
    """
    
    def __init__(self, base_strategy: BaseStrategy, category: str, evaluation_params: Dict):
        """
        Initialize the wrapper.
        
        Args:
            base_strategy: The strategy instance being evaluated
            category: 'WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', or 'HYBRID'
            evaluation_params: Standardized parameters for this category
        """
        self.base_strategy = base_strategy
        self.category = category
        self.eval_params = evaluation_params
        
        # For tracking hybrid constraints
        self.total_contributions = 0.0
        
        # Call parent init with eval params
        self.eval_params = evaluation_params.copy()
        self.category = category
        
        # Merge strategy's default params with eval params
        # Strategy defaults provide strategy-specific settings (drawdown_method, LTV, etc.)
        # Eval params provide standardized test conditions (years, amount, simulations)
        merged_params = {}
        
        # Start with base strategy's current params (may include user customizations)
        if hasattr(base_strategy, 'params') and base_strategy.params:
            merged_params.update(base_strategy.params)
        
        # Override/add eval params (standardized conditions)
        merged_params.update(self.eval_params)
        
        # Update base strategy with merged params so delegated calls work correctly
        self.base_strategy.params = merged_params
            
        super().__init__(merged_params)
    
    @property
    def display_name(self) -> str:
        """Pass through display name from base strategy."""
        return getattr(self.base_strategy, 'display_name', self.base_strategy.__class__.__name__)
    
    @property
    def parameters(self):
        """Pass through parameters from base strategy."""
        return self.base_strategy.parameters
    
    @property
    def shortfall_funding_policy(self) -> list:
        """Pass through funding policy from base strategy."""
        return self.base_strategy.shortfall_funding_policy
    
    def reset(self):
        """Reset wrapper and base strategy state for each new simulation."""
        # Reset wrapper's own state
        self.total_contributions = 0.0
        # Delegate to base strategy
        if hasattr(self.base_strategy, 'reset'):
            self.base_strategy.reset()
    
    def initialize_portfolio(self, initial_portfolio_state: Dict, market_data_at_start) -> Dict:
        """Delegate portfolio initialization to base strategy."""
        return self.base_strategy.initialize_portfolio(initial_portfolio_state, market_data_at_start)
    
    def get_annual_drawdown(self, year: int, portfolio_state: Dict, portfolio_history: list) -> float:
        """
        Override drawdown based on category.
        
        For WITHDRAWAL_ONLY: Enforce 4% withdrawal rate
        For CONTRIBUTION_ONLY: Force zero withdrawals
        For HYBRID: Delegate to base strategy
        """
        # Normalize portfolio_history keys to lowercase snake_case for custom strategies
        robust_history = [{_normalize_key(k): v for k, v in item.items()} for item in portfolio_history]
        
        if self.category == 'WITHDRAWAL_ONLY':
            # Let strategy control withdrawal amount (enables dynamic strategies)
            return self.base_strategy.get_annual_drawdown(year, portfolio_state, robust_history)
            
        elif self.category == 'CONTRIBUTION_ONLY':
            # No withdrawals allowed
            return 0.0
            
        else:  # HYBRID
            # Delegate to base strategy - it controls its own schedule
            return self.base_strategy.get_annual_drawdown(year, portfolio_state, robust_history)
    
    def execute_strategy_for_year(
        self, 
        year: int, 
        portfolio_state: Dict, 
        portfolio_history: list,
        desired_drawdown: float, 
        mandatory_costs: float
    ) -> Dict:
        """
        Override execution based on category constraints.
        
        Gets base strategy's decision, then enforces category-specific constraints
        on contributions and withdrawals.
        """
        # Normalize portfolio_history keys to lowercase snake_case for custom strategies
        robust_history = [{_normalize_key(k): v for k, v in item.items()} for item in portfolio_history]
        
        # Get base strategy's decision
        decision = self.base_strategy.execute_strategy_for_year(
            year, portfolio_state, robust_history, 
            desired_drawdown, mandatory_costs
        )
        
        # Apply category constraints
        if self.category == 'WITHDRAWAL_ONLY':
            # Force zero contributions
            decision['amount_contributed'] = 0.0
            
        elif self.category == 'CONTRIBUTION_ONLY':
            # Force standardized contributions
            decision['amount_contributed'] = self.eval_params['annual_contribution']
            
        # For HYBRID, no overrides - strategy controls everything
        
        # Track contributions for potential future constraints
        self.total_contributions += decision.get('amount_contributed', 0.0)
        
        return decision

