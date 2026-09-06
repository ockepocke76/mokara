"""
Strategy Evaluation Engine

This module provides the core functionality for evaluating investment strategies
across standardized parametric asset scenarios to generate risk-adjusted performance scores.

The evaluation system:
1. Auto-categorizes strategies by observing their behavior
2. Runs strategies across 8 standardized market scenarios
3. Calculates composite Excellence Scores (0-100)
4. Supports leaderboard ranking within categories
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple
from core.stats import calculate_final_statistics
from simulation import run_simulation
from core.shared_logic import prepare_results_dataframe


# Test scenario definitions with weights
TEST_SCENARIOS = [
    {
        'name': 'Bull Market',
        'description': 'Strong returns with moderate volatility',
        'annual_return': 0.12,
        'annual_volatility': 0.15,
        'weight': 0.15
    },
    {
        'name': 'Normal Market',
        'description': 'Historical S&P 500-like conditions',
        'annual_return': 0.08,
        'annual_volatility': 0.18,
        'weight': 0.25  # Highest weight - most important
    },
    {
        'name': 'Bear Market',
        'description': 'Negative returns with high stress',
        'annual_return': -0.02,
        'annual_volatility': 0.20,
        'weight': 0.20  # High weight - survival matters
    },
    {
        'name': 'High Volatility',
        'description': 'Crypto-like volatility',
        'annual_return': 0.08,
        'annual_volatility': 0.30,
        'weight': 0.15
    },
    {
        'name': 'Low Volatility',
        'description': 'Bond-like stability',
        'annual_return': 0.05,
        'annual_volatility': 0.10,
        'weight': 0.03  # CHANGED: 0.05 → 0.03 (freed weight for new scenarios)
    },
    {
        'name': 'Extreme Bull',
        'description': 'Best case scenario',
        'annual_return': 0.20,
        'annual_volatility': 0.25,
        'weight': 0.05
    },
    {
        'name': 'Extreme Bear',
        'description': 'Worst case scenario (2008-like crisis)',
        'annual_return': -0.10,
        'annual_volatility': 0.35,
        'weight': 0.10  # Stress testing emphasis
    },
    {
        'name': 'Sideways Market',
        'description': 'Low returns with moderate volatility',
        'annual_return': 0.03,
        'annual_volatility': 0.22,
        'weight': 0.04  # CHANGED: 0.05 → 0.04 (freed weight for new scenarios)
    },
    {
        'name': 'Stagflation',
        'description': 'Low growth with high inflation-era volatility (1970s-like)',
        'annual_return': 0.01,
        'annual_volatility': 0.20,
        'weight': 0.02  # NEW: Tests purchasing power preservation
    },
    {
        'name': 'Deflation',
        'description': 'Zero growth with moderate volatility (Japan-like stagnation)',
        'annual_return': 0.00,
        'annual_volatility': 0.15,
        'weight': 0.01  # NEW: Tests strategies under zero-return conditions
    }
]
# Total weights = 1.00 ✓

from core.metrics import (
    PresentValueMetric, PurchasingPowerMetric, WithdrawalStabilityMetric,
    RiskScoreMetric, RobustnessScoreMetric, CapitalEfficiencyMetric,
    LegacyScoreMetric, AdequacyScoreMetric, UsabilityScoreMetric,
    ConsumptionRatioMetric,
    CoastFIREMetric, AccumulationVelocityMetric, ContributionEfficiencyMetric,
    SharpeRatioMetric, CalmarRatioMetric, DownsideStabilityMetric, UlcerIndexMetric
)

# Metric Registry: Defines active metrics and their weights
METRIC_REGISTRY = {
    'pv_score': PresentValueMetric(
        weight=0.20, name="Present Value Score", 
        description="Total withdrawal value (time-adjusted)"
    ),
    'purchasing_power_score': PurchasingPowerMetric(
        weight=0.15, name="Purchasing Power Score", 
        description="Inflation tracking"
    ),
    'stability_score': WithdrawalStabilityMetric(
        weight=0.15, name="Withdrawal Stability", 
        description="Income predictability"
    ),
    'risk_score': RiskScoreMetric(
        weight=0.20, name="Risk Score", 
        description="Portfolio survival + tail risk"
    ),
    'robustness_score': RobustnessScoreMetric(
        weight=0.05, name="Robustness Score", 
        description="Consistency across scenarios"
    ),
    'capital_efficiency_score': CapitalEfficiencyMetric(
        weight=0.15, name="Capital Efficiency", 
        description="ROI on total capital"
    ),
    'legacy_score': LegacyScoreMetric(
        weight=0.10, name="Legacy Score", 
        description="Capital Preservation"
    ),
    'consumption_ratio_score': ConsumptionRatioMetric(
        weight=0.00, name="Consumption Ratio",  # Weight controlled per profile
        description="Pure withdrawal efficiency (excludes legacy)"
    ),
    # Accumulation-specific metrics (0 weight in balanced, controlled per profile)
    'coast_fire_score': CoastFIREMetric(
        weight=0.00, name="Coast FIRE Score",
        description="Years to financial independence"
    ),
    'accumulation_velocity_score': AccumulationVelocityMetric(
        weight=0.00, name="Accumulation Velocity",
        description="Rate of wealth growth (CAGR)"
    ),
    'contribution_efficiency_score': ContributionEfficiencyMetric(
        weight=0.00, name="Contribution Efficiency",
        description="ROI on contributions"
    ),
    # New scoring metrics (0 weight in balanced, controlled per profile)
    'sharpe_ratio_score': SharpeRatioMetric(
        weight=0.00, name="Sharpe Ratio",
        description="Risk-adjusted return (Sharpe)"
    ),
    'calmar_ratio_score': CalmarRatioMetric(
        weight=0.00, name="Calmar Ratio",
        description="Return relative to max drawdown"
    ),
    'downside_stability_score': DownsideStabilityMetric(
        weight=0.00, name="Downside Stability",
        description="Income predictability (downside only)"
    ),
    'ulcer_index_score': UlcerIndexMetric(
        weight=0.00, name="Ulcer Index",
        description="Drawdown depth and duration"
    ),
    # Deprecated metrics (0 weight)
    'adequacy_score': AdequacyScoreMetric(weight=0.0, name="Adequacy"),
    'usability_score': UsabilityScoreMetric(weight=0.0, name="Usability"),
}

# Compatibility mapping for UI (so we don't break strategy_leaderboard.py immediately)
METRIC_WEIGHTS = {key: {'name': m.name, 'weight': m.weight} for key, m in METRIC_REGISTRY.items()}

# Centralized HYBRID pre-probing parameters
# These control how we find balanced initial investments for HYBRID strategies
HYBRID_PROBING_PARAMS = {
    'target_transition_ratio': 0.5,  # Target transition at 50% of simulation time
    'tolerance': 0.20,               # Accept ±20% deviation from target
    'max_iterations': 8,             # Max binary search iterations
    'probe_simulations': 10,         # Quick probe simulations per iteration
    'search_range_low': 50_000,      # Minimum initial investment to try
    'search_range_high': 10_000_000, # Maximum initial investment to try
}


# Standardized evaluation parameters by category
STANDARD_EVAL_PARAMS = {
    'WITHDRAWAL_ONLY': {
        'initial_investment': 1_000_000,
        'num_years': 30,
        'num_simulations': 200,
        'inflation_rate': 0.02,
        'asset_model': 'parametric',
        'tax_method': 'isk',
        'isk_tax_rate': 0.01,
        'cash_interest_rate': 0.01,
        'asset_management_fee': 0.001,
        'loan_interest_rate': 0.05,
        # Withdrawal rate forced by wrapper
    },
    'CONTRIBUTION_ONLY': {
        'initial_investment': 100_000,
        'annual_contribution': 50_000,
        'num_years': 30,
        'num_simulations': 200,
        'inflation_rate': 0.02,
        'asset_model': 'parametric',
        'tax_method': 'isk',
        'isk_tax_rate': 0.01,
        'cash_interest_rate': 0.01,
        'asset_management_fee': 0.001,
        'loan_interest_rate': 0.05,
        'loan_interest_rate': 0.05,
    },
    'HYBRID': {
        'initial_investment': 500_000,
        'num_years': 40,  # Longer for accumulation phase
        'num_simulations': 200,
        'target_net_worth': 3_000_000,  # Realistic target from 500K start
        'inflation_rate': 0.02,
        'asset_model': 'parametric',
        'tax_method': 'isk',
        'isk_tax_rate': 0.01,
        'cash_interest_rate': 0.01,
        'asset_management_fee': 0.001,
        'loan_interest_rate': 0.05,
        # No constraints - strategy controls behavior
    }
}


def auto_categorize_strategy(strategy_instance, params: Dict) -> str:
    """
    Gets the evaluation category from the strategy itself.
    
    Args:
        strategy_instance: Instantiated strategy object
        params: Base simulation parameters (unused, kept for compatibility)
        
    Returns:
        str: 'WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', or 'HYBRID'
    """
    logging.info(f"Getting evaluation category for: {strategy_instance.__class__.__name__}")
    
    try:
        # Get category from strategy's self-declaration
        category = strategy_instance.evaluation_category()
        
        # Validate category
        valid_categories = ['WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', 'HYBRID']
        if category not in valid_categories:
            logging.warning(f"Invalid category '{category}' returned. Defaulting to HYBRID.")
            category = 'HYBRID'
        
        logging.info(f"Category: {category}")
        return category
        
    except Exception as e:
        logging.warning(f"Failed to get category from strategy: {e}. Defaulting to HYBRID.")
        return 'HYBRID'


def classify_strategy_phases(simulation_results: List, num_years: int = 40) -> Dict:
    """
    Classify each year as accumulation or decumulation based on net cash flow.
    Handles strategies with multiple transitions (e.g., dynamic strategies that switch back and forth).
    
    Args:
        simulation_results: List of SimulationResult objects from run_simulation
        num_years: Total simulation years
        
    Returns:
        Dict with:
            - 'accumulation_years': Total years spent in accumulation across all sims
            - 'decumulation_years': Total years spent in decumulation across all sims
            - 'is_pure_accumulation': True if >95% of time is accumulation
            - 'is_pure_decumulation': True if >95% of time is decumulation
            - 'transition_count': Average number of phase changes per simulation
            - 'phase_ratio': accumulation_years / total_years (0.0 to 1.0)
    """
    total_accumulation_years = 0
    total_decumulation_years = 0
    first_transitions = []
    all_transition_counts = []
    
    for sim_result in simulation_results:
        yearly_data = sim_result.yearly_results
        first_transition = None
        transition_count = 0
        previous_phase = None
        
        for year_data in yearly_data:
            year = year_data.get('Year', 0)
            if year == 0:
                continue
                
            withdrawals = year_data.get('Consumption Delivered', 0)
            contributions = year_data.get('Amount Contributed', 0)
            net_cash_flow = withdrawals - contributions
            
            # Classify this year's phase
            current_phase = 'decumulation' if net_cash_flow > 0 else 'accumulation'
            
            # Count years by phase
            if current_phase == 'accumulation':
                total_accumulation_years += 1
            else:
                total_decumulation_years += 1
            
            # Track first transition
            if current_phase == 'decumulation' and first_transition is None:
                first_transition = year
            
            # Count phase changes
            if previous_phase is not None and previous_phase != current_phase:
                transition_count += 1
            
            previous_phase = current_phase
        
        first_transitions.append(first_transition if first_transition else num_years)
        all_transition_counts.append(transition_count)
    
    # Calculate aggregate statistics
    total_years = total_accumulation_years + total_decumulation_years
    
    if total_years == 0:
        # No data - return defaults
        return {
            'accumulation_years': num_years,
            'decumulation_years': 0,
            'is_pure_accumulation': True,
            'is_pure_decumulation': False,
            'transition_count': 0,
            'phase_ratio': 1.0
        }
    
    phase_ratio = total_accumulation_years / total_years
    avg_transition_count = np.mean(all_transition_counts) if all_transition_counts else 0
    
    # Detect pure strategies (>95% in one phase)
    is_pure_accumulation = phase_ratio > 0.95
    is_pure_decumulation = phase_ratio < 0.05
    
    return {
        'accumulation_years': total_accumulation_years,
        'decumulation_years': total_decumulation_years,
        'is_pure_accumulation': is_pure_accumulation,
        'is_pure_decumulation': is_pure_decumulation,
        'transition_count': avg_transition_count,
        'phase_ratio': phase_ratio
    }


def find_balanced_initial(strategy_class, scenario: Dict, base_eval_params: Dict,
                          target_transition_year: int = None, 
                          tolerance: float = None,
                          max_iterations: int = None, 
                          probe_sims: int = None) -> float:
    """
    Binary search to find initial investment where strategy transitions at ~50% of sim time.
    
    For HYBRID strategies, we want to evaluate both accumulation and decumulation phases.
    This function finds an initial investment amount that causes the strategy to transition
    from accumulation (net contributions) to decumulation (net withdrawals) around the
    midpoint of the simulation.
    
    Args:
        strategy_class: Strategy class to instantiate
        scenario: Market scenario dict with annual_return, annual_volatility
        base_eval_params: Base evaluation parameters to use
        target_transition_year: Ideal transition year (default: uses HYBRID_PROBING_PARAMS['target_transition_ratio'])
        tolerance: Acceptable deviation (default: HYBRID_PROBING_PARAMS['tolerance'])
        max_iterations: Maximum binary search iterations (default: HYBRID_PROBING_PARAMS['max_iterations'])
        probe_sims: Number of simulations per probe (default: HYBRID_PROBING_PARAMS['probe_simulations'])
        
    Returns:
        Optimal initial investment, or default if no good transition found
    """
    from core.evaluation_wrapper import EvaluationStrategyWrapper
    
    # Set defaults from centralized params if not provided
    if tolerance is None:
        tolerance = HYBRID_PROBING_PARAMS['tolerance']
    if max_iterations is None:
        max_iterations = HYBRID_PROBING_PARAMS['max_iterations']
    if probe_sims is None:
        probe_sims = HYBRID_PROBING_PARAMS['probe_simulations']
    
    num_years = base_eval_params.get('num_years', 40)
    if target_transition_year is None:
        target_transition_year = int(num_years * HYBRID_PROBING_PARAMS['target_transition_ratio'])
    
    min_acceptable = int(target_transition_year * (1 - tolerance))
    max_acceptable = int(target_transition_year * (1 + tolerance))
    
    # Search range for initial investment
    low = HYBRID_PROBING_PARAMS['search_range_low']
    high = HYBRID_PROBING_PARAMS['search_range_high']
    best_initial = base_eval_params.get('initial_investment', 500_000)  # Fallback
    best_distance = float('inf')
    
    for iteration in range(max_iterations):
        mid = (low + high) / 2
        
        # Create probe params
        probe_params = base_eval_params.copy()
        probe_params['initial_investment'] = mid
        probe_params['num_simulations'] = probe_sims
        probe_params['annual_return'] = scenario['annual_return']
        probe_params['annual_volatility'] = scenario['annual_volatility']
        probe_params['asset_model'] = 'parametric'
        
        # Create strategy factory for probing
        def make_strategy():
            instance = strategy_class(probe_params)
            return EvaluationStrategyWrapper(instance, 'HYBRID', base_eval_params)
        
        # Run quick probe simulation
        try:
            results = run_simulation(
                probe_params, 
                mu=scenario['annual_return'],
                sigma=scenario['annual_volatility'],
                strategy_factory=make_strategy
            )
            
            phase_info = classify_strategy_phases(results, num_years)
            
            # For HYBRID strategies, we want a balanced mix of accumulation and decumulation
            # Use phase_ratio: target is around 0.5 (50% accumulation, 50% decumulation)
            # This works for strategies with multiple transitions too
            target_phase_ratio = target_transition_year / num_years if target_transition_year else 0.5
            actual_phase_ratio = phase_info['phase_ratio']
            
            distance = abs(actual_phase_ratio - target_phase_ratio)
            
            # Track best result so far
            if distance < best_distance:
                best_distance = distance
                best_initial = mid
            
            # Check if within tolerance (convert year tolerance to ratio tolerance)
            ratio_tolerance = (tolerance / num_years) if tolerance else 0.05
            if abs(actual_phase_ratio - target_phase_ratio) <= ratio_tolerance:
                acc_years = int(actual_phase_ratio * num_years)
                logging.info(f"Found balanced initial ${mid:,.0f} for {scenario['name']} (phase ratio: {actual_phase_ratio:.1%}, ~{acc_years} acc years, {phase_info['transition_count']:.1f} transitions)")
                return mid
            
            # Binary search adjustment
            if actual_phase_ratio > target_phase_ratio:
                # Too much accumulation - need lower initial to increase withdrawals
                high = mid
            else:
                # Too much decumulation - need higher initial to increase accumulation
                low = mid
                
        except Exception as e:
            logging.warning(f"Probe failed for initial ${mid:,.0f}: {e}")
            high = mid  # Try smaller
    
    # If probing completely failed (all iterations failed), raise an error
    if best_distance == float('inf'):
        raise RuntimeError(
            f"HYBRID probing completely failed for {scenario['name']}. "
            f"All {max_iterations} probe iterations encountered errors. "
            f"This usually means the strategy code has a bug (e.g., KeyError in portfolio_history access). "
            f"Check the logs for 'Probe failed' warnings."
        )
    
    logging.info(f"Using best found initial ${best_initial:,.0f} for {scenario['name']} (best distance: {best_distance})")
    return best_initial





def calculate_excellence_score(scenario_results: List[Dict], category: str) -> Dict:
    """
    Calculates composite Excellence Score from scenario results.
    
    NEW FORMULA:
    - 20% Present Value Score (total value delivered, time-adjusted)
    - 15% Purchasing Power Score (inflation tracking)
    - 15% Withdrawal Stability Score (income predictability)
    - 20% Risk Score (survival + tail risk)
    - 5% Robustness Score (consistency across scenarios)
    - 10% Withdrawal Adequacy (meets minimum livable standard)
    - 5% Usability Score (consistency of livable income)
    - 10% Legacy Score (capital preservation)
    
    Args:
        scenario_results: List of dicts with scenario metrics
        category: Strategy category
        
    Returns:
        Dict with excellence_score and component scores
    """
    scenario_scores = []
    sortino_ratios = []
    success_rates = []
    all_withdrawals = []  # Track withdrawals across scenarios
    
    for scenario in scenario_results:
        stats = scenario['stats']
        weight = scenario['weight']
        params = scenario['params']
        
        # Extract withdrawal history if available
        withdrawal_history = stats.get('drawdown_history', [])
        if withdrawal_history:
            all_withdrawals.append(withdrawal_history)
        
        # 1. PRESENT VALUE SCORE (based on withdrawal stream)
        if withdrawal_history:
            inflation = params.get('inflation_rate', 0.02)
            pv = calculate_present_value(withdrawal_history, inflation)
            # Normalize: Stricter baseline. 
            # A standard 4% rule is "good" (80%), not perfect.
            # $1M * 4% * 30 years = $1.2M nominal. 
            # PV of annuity due (30yr, 2% inf, 4% rate) ~ $1.0M.
            # Let's set 100 points at $1.5M (significantly outperforming)
            # and 80 points at $1.0M (meeting expectation).
            target_pv_excellent = 1_500_000
def calculate_excellence_score(scenario_results: List[Dict], category: str) -> Dict:
    """
    Calculates composite Excellence Score from scenario results.
    Uses metric classes from METRIC_REGISTRY to compute scores.
    Now category-aware: excludes metrics that return None (not applicable).
    
    Returns:
        Dict with excellence_score and component scores breakdown
    """
    scenario_scores = []
    
    # Pre-instantiate robustness metric for aggregate calculation later
    robustness_metric = METRIC_REGISTRY['robustness_score']
    
    for scenario in scenario_results:
        stats = scenario['stats']
        weight = scenario['weight']
        params = scenario['params']
        
        # Calculate individual metric scores with category context
        metric_scores = {}
        applicable_weights = {}
        
        for key, metric in METRIC_REGISTRY.items():
            if key == 'robustness_score':
                # Calculated aggregated later, use placeholder for now
                metric_scores[key] = 50.0
                if metric.is_applicable(category):
                    applicable_weights[key] = metric.weight
                continue
            
            # Pass category in context
            context = {'category': category}
            score = metric.calculate(stats, params, context)
            
            if score is None:
                # Metric not applicable - skip it
                metric_scores[key] = None
                continue
            
            metric_scores[key] = score
            if metric.is_applicable(category):
                applicable_weights[key] = metric.weight
        
        # Normalize weights (since we excluded some metrics)
        total_weight = sum(applicable_weights.values())
        if total_weight == 0:
            raise ValueError(f"No applicable metrics for category {category}")
        
        normalized_weights = {k: v / total_weight for k, v in applicable_weights.items()}
        
        # Calculate weighted sum using only applicable metrics
        weighted_sum = sum(
            metric_scores[k] * normalized_weights.get(k, 0)
            for k in metric_scores
            if metric_scores[k] is not None and k in normalized_weights
        )
        
        # Store full breakdown
        scenario_scores.append({
            'score': weighted_sum,
            'weight': weight,
            **metric_scores
        })
    
    # Calculate Robustness Score (Aggregate across all scenarios)
    robustness_score = robustness_metric.calculate_aggregate(scenario_results, category=category)
    
    # Get applicable weights for final normalization
    applicable_weights_final = {}
    for key, metric in METRIC_REGISTRY.items():
        if metric.is_applicable(category):
            applicable_weights_final[key] = metric.weight
    
    total_weight_final = sum(applicable_weights_final.values())
    normalized_weights_final = {k: v / total_weight_final for k, v in applicable_weights_final.items()}
    
    # Update robustness score in all scenario entries and adjust total score
    final_scenario_scores = []
    for sc_score in scenario_scores:
        # Subtract placeholder contribution
        previous_robustness_contrib = sc_score['robustness_score'] * normalized_weights_final.get('robustness_score', 0)
        
        # Add actual robustness contribution
        new_robustness_contrib = robustness_score * normalized_weights_final.get('robustness_score', 0)
        
        sc_score['score'] = sc_score['score'] - previous_robustness_contrib + new_robustness_contrib
        sc_score['robustness_score'] = robustness_score
        final_scenario_scores.append(sc_score)
    
    # Weighted Excellence Score across all scenarios
    # (Sum of weighted scenario scores)
    excellence_score = sum(item['score'] * item['weight'] for item in final_scenario_scores)
    
    # Calculate weighted aggregate scores for each metric to satisfy database schema
    aggregate_scores = {}
    for key, metric in METRIC_REGISTRY.items():
        if key == 'robustness_score':
            aggregate_scores[key] = round(robustness_score, 2)
        else:
            # Weighted average of this metric across all scenarios
            # Only include non-None scores in average
            valid_scores = [(s[key], s['weight']) for s in final_scenario_scores if s[key] is not None]
            if valid_scores:
                weighted_avg = sum(score * weight for score, weight in valid_scores)
                aggregate_scores[key] = round(weighted_avg, 2)
            else:
                aggregate_scores[key] = None  # No applicable scores
    
    return {
        'excellence_score': round(excellence_score, 2),
        'scenario_scores': final_scenario_scores,
        **aggregate_scores
    }



def get_test_scenarios() -> List[Dict]:
    """Returns the standardized test scenarios."""
    return TEST_SCENARIOS


def get_standard_eval_params(category: str) -> Dict:
    """Returns standardized evaluation parameters for a category."""
    return STANDARD_EVAL_PARAMS.get(category, {}).copy()


def evaluate_strategy(strategy_class, strategy_name: str, base_params: Dict = None) -> Dict:
    """
    Full evaluation pipeline for a strategy.
    
    Args:
        strategy_class: The strategy class to evaluate
        strategy_name: Human-readable name for the strategy
        base_params: Base parameters (optional)
        
    Returns:
        Dict with evaluation results ready for database
    """
    import json
    from core.evaluation_wrapper import EvaluationStrategyWrapper
    
    logging.info(f"===== Evaluating {strategy_name} =====")
    
    if base_params is None:
        base_params = {}
    
    # Auto-categorize
    diagnostic_instance = strategy_class(base_params)
    category = auto_categorize_strategy(diagnostic_instance, base_params)
    
    # Get standardized params
    eval_params = get_standard_eval_params(category)
    
    # Inject strategy-specific defaults into eval_params
    # This ensures strategies like BBD which depend on default params have them.
    try:
        # Retrieve parameters from the diagnostic instance
        # Handle both @property (returns dict) and methods (returns callable)
        params_attr = diagnostic_instance.parameters
        
        if callable(params_attr):
             strategy_defaults = params_attr()
        else:
             strategy_defaults = params_attr
             
        if isinstance(strategy_defaults, dict):
            for param_key, param_info in strategy_defaults.items():
                if 'default' in param_info:
                    # Only set if not already defined (standard params take precedence)
                    eval_params.setdefault(param_key, param_info['default'])
    except Exception as e:
        logging.warning(f"Failed to inject default parameters for {strategy_name}: {e}")

    test_scenarios = get_test_scenarios()
    
    # For HYBRID strategies, pre-probe to find balanced initial investments per scenario
    # This ensures both accumulation and decumulation phases are evaluated fairly
    scenario_initials = {}
    if category == 'HYBRID':
        logging.info("Pre-probing for balanced initial investments (HYBRID strategy)...")
        for scenario in test_scenarios:
            balanced_initial = find_balanced_initial(
                strategy_class, scenario, eval_params
            )
            scenario_initials[scenario['name']] = balanced_initial
        logging.info(f"Pre-probing complete. Initials: {scenario_initials}")
    
    # Run across all scenarios
    scenario_results = []
    for i, scenario in enumerate(test_scenarios):
        logging.info(f"[{i+1}/8] {scenario['name']}...")
        
        test_params = eval_params.copy()
        test_params['annual_return'] = scenario['annual_return']
        test_params['annual_volatility'] = scenario['annual_volatility']
        
        # For HYBRID strategies, use the probed balanced initial for this scenario
        if category == 'HYBRID' and scenario['name'] in scenario_initials:
            test_params['initial_investment'] = scenario_initials[scenario['name']]
            logging.info(f"  Using probed initial ${test_params['initial_investment']:,.0f} for {scenario['name']}")
        
        # Create factory function for fresh strategy instances per simulation
        # This makes evaluation immune to strategies that don't implement reset() properly
        def make_strategy():
            instance = strategy_class(test_params)
            return EvaluationStrategyWrapper(instance, category, eval_params)
        
        results = run_simulation(test_params, mu=scenario['annual_return'], 
                                sigma=scenario['annual_volatility'],
                                strategy_factory=make_strategy)
        results_df = prepare_results_dataframe(results)
        stats = calculate_final_statistics(results_df, test_params)
        
        # Extract median drawdown history for this scenario
        drawdown_history = []
        if results and len(results) > 0:
            final_real_net_worths = []
            
            # Get median simulation for drawdown history
            # Sort results by final Net Worth to find the true median performance
            results.sort(key=lambda x: x.yearly_results[-1].get('Net Worth', 0.0))
            median_idx = len(results) // 2
            for year_data in results[median_idx].yearly_results:
                if year_data['Year'] > 0:  # Skip year 0
                    # Consumption Delivered = consumption_paid (actual delivered, any source)
                    drawdown_history.append(year_data.get('Consumption Delivered', 0.0))
            
            # Calculate median final real net worth
            inflation = test_params.get('inflation_rate', 0.0)
            years = test_params.get('num_years', 30)
            inflation_adjustment = 1 / ((1 + inflation) ** years)
            
            for sim in results:
                if sim.yearly_results:
                    final_nominal = sim.yearly_results[-1].get('Net Worth', 0.0)
                    final_real = final_nominal * inflation_adjustment
                    final_real_net_worths.append(final_real)
            
            if final_real_net_worths:
                stats['median_final_real_net_worth'] = np.median(final_real_net_worths)
            else:
                stats['median_final_real_net_worth'] = 0.0
                
        stats['drawdown_history'] = drawdown_history
        
        scenario_results.append({'name': scenario['name'], 'weight': scenario['weight'],
                                'params': test_params, 'stats': stats})
    
    # Calculate scores
    scores = calculate_excellence_score(scenario_results, category)
    logging.info(f"Complete: {scores['excellence_score']:.2f}/100")
    
    # --- NEW: Calculate scores for ALL weighting profiles ---
    from core.weighting_profiles import WEIGHTING_PROFILES, recalculate_excellence_score
    
    profile_scores = {}
    for profile_key in WEIGHTING_PROFILES.keys():
        # Create mock strategy entry for recalculation
        # recalculate_excellence_score needs the component scores
        mock_entry = {
            'strategy_category': category,
            **{k: v for k, v in scores.items() if k.endswith('_score')}  # All metric scores
        }
        
        profile_score = recalculate_excellence_score(mock_entry, profile_key)
        profile_scores[profile_key] = profile_score
        logging.info(f"  Profile '{profile_key}': {profile_score:.2f}/100")
    
    # Package for database
    return {
        'strategy_name': strategy_name,
        'strategy_class_name': strategy_class.__name__,
        'strategy_category': category,
        **scores,
        'profile_scores': profile_scores,  # NEW: Dict of {profile_key: score}
        'scenario_results_json': json.dumps([
            {'name': s['name'], 
             'sortino_ratio': s['stats'].get('strategy_sortino_ratio', 0.0),
             'success_rate': s['stats'].get('success_rate', 0.0),
             'cvar_95_loss': s['stats'].get('cvar_95_loss', 0.0),
             'drawdown_history': s['stats'].get('drawdown_history', [])}
            for s in scenario_results
        ]),
        'evaluation_params_json': json.dumps(eval_params)
    }
