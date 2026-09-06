
"""
Evaluation Metrics for Strategy Performance

This module defines the metric classes used to evaluate strategy simulations.
Each metric is responsible for:
1. Calculating its own score based on simulation stats/results
2. Describing itself for documentation (UI)
3. Maintaining its own configuration (weight, name)
"""

import numpy as np
from typing import Dict, List, Any
import logging

class BaseMetric:
    """Abstract base class for all evaluation metrics."""
    
    def __init__(self, weight: float = 0.0, name: str = "Metric", 
                 description: str = "", applicable_categories: List[str] = None):
        self.weight = weight
        self.name = name
        self.description = description
        # If None, applies to all categories
        self.applicable_categories = applicable_categories or ['WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', 'HYBRID']
    
    def is_applicable(self, category: str) -> bool:
        """Check if this metric applies to the given strategy category."""
        return category in self.applicable_categories
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        """
        Calculate score (0-100) for this metric.
        
        Args:
            stats: Statistics dictionary for a single scenario
            params: Parameters for the scenario (inflation, initial, etc.)
            context: Additional context (category, transition_info, etc.)
            
        Returns:
            Score between 0.0 and 100.0, or None if metric not applicable
        """
        raise NotImplementedError
    
    def describe_score_components(self) -> str:
        """Returns the markdown description for the 'Score Components' UI section."""
        return f"- **{self.name}**: {self.description}"

class PresentValueMetric(BaseMetric):
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['WITHDRAWAL_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        category = context.get('category', 'WITHDRAWAL_ONLY') if context else 'WITHDRAWAL_ONLY'
        if not self.is_applicable(category):
            return None
        
        withdrawal_history = stats.get('drawdown_history', [])
        if not withdrawal_history:
            return 0.0
            
        inflation = params.get('inflation_rate', 0.02)
        
        # Calculate PV
        pv = 0.0
        for year, amount in enumerate(withdrawal_history, start=1):
            discount_factor = 1 / ((1 + inflation) ** (year - 1))
            pv += amount * discount_factor
            
        # Scoring: $1.0M = 66 pts, $1.5M = 100 pts
        target_pv_excellent = 1_500_000
        
        if pv >= target_pv_excellent:
            return 100.0
        else:
            return (pv / target_pv_excellent) * 100.0

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Lifetime Real Withdrawal Value\n"
            f"  - **Concept**: Measures the total inflation-adjusted purchasing power extracted from the portfolio.\n"
            f"  - **Formula**: `PV = Sum of [Annual Withdrawal / (1 + Inflation)^Year]`\n"
            f"  - **Normalization**: Linear scale to $1.5M target\n"
            f"  - **Scoring**:\n\n"
            f"    | Total Real Withdrawals | Score | Meaning |\n"
            f"    |------------------------|-------|---------|\n"
            f"    | $0.5M | 33 | Below expectations |\n"
            f"    | $1.0M | 66 | Breakeven with initial capital |\n"
            f"    | $1.5M+ | 100 | Excellent - 1.5x initial |\n"
        )

class PurchasingPowerMetric(BaseMetric):
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['WITHDRAWAL_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        category = context.get('category', 'WITHDRAWAL_ONLY') if context else 'WITHDRAWAL_ONLY'
        if not self.is_applicable(category):
            return None
        
        withdrawals = stats.get('drawdown_history', [])
        if not withdrawals:
            return 100.0
            
        inflation = params.get('inflation_rate', 0.02)
        
        # Find first non-zero withdrawal year
        first_withdrawal_idx = None
        for i, w in enumerate(withdrawals):
            if w > 0:
                first_withdrawal_idx = i
                break
        
        if first_withdrawal_idx is None:
            return 100.0  # No withdrawals at all - don't penalize
        
        # Slice from first withdrawal onward (include all subsequent years)
        withdrawal_phase = withdrawals[first_withdrawal_idx:]
        
        if len(withdrawal_phase) < 2:
            return 100.0  # Not enough data
        
        # Convert to real (inflation-adjusted) terms
        real_withdrawals = []
        for i, amount in enumerate(withdrawal_phase):
            year = first_withdrawal_idx + i + 1  # Actual year (1-indexed)
            real_value = amount / ((1 + inflation) ** (year - 1))
            real_withdrawals.append(real_value)
        
        # Calculate average year-over-year real growth (path-aware)
        yoy_growths = []
        for i in range(1, len(real_withdrawals)):
            prev = real_withdrawals[i-1]
            curr = real_withdrawals[i]
            if prev > 0:
                yoy_growth = (curr / prev) - 1
                yoy_growths.append(yoy_growth)
            elif curr > 0:
                # Previous was 0, current is positive - count as recovery but skip growth calc
                pass
        
        if not yoy_growths:
            return 100.0
        
        avg_real_growth = np.mean(yoy_growths)
        
        if avg_real_growth >= 0.02:
            return 100.0
        elif avg_real_growth >= 0:
            return 80.0 + (avg_real_growth / 0.02) * 20.0
        else:
            score = 80.0 + (avg_real_growth * 1500.0)
            return max(0.0, score)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Inflation Tracking Capability\n"
            f"  - **Concept**: Measures if income keeps up with cost of living (real growth of withdrawals).\n"
            f"  - **Formula**: `Avg Year-over-Year Real Withdrawal Growth`\n"
            f"  - **Normalization**: Linear scale with 2% real growth = 100\n"
            f"  - **Scoring**:\n\n"
            f"    | Avg Real Growth | Score | Meaning |\n"
            f"    |-----------------|-------|---------|\n"
            f"    | -5% | 5 | Severe purchasing power erosion |\n"
            f"    | 0% | 80 | Maintained purchasing power |\n"
            f"    | +2%+ | 100 | Growing lifestyle spending |\n"
        )

class WithdrawalStabilityMetric(BaseMetric):
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['WITHDRAWAL_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        # Check category applicability
        category = context.get('category', 'WITHDRAWAL_ONLY') if context else 'WITHDRAWAL_ONLY'
        if not self.is_applicable(category):
            return None  # Not applicable to contribution-only strategies
        
        withdrawals = stats.get('drawdown_history', [])
        if not withdrawals:
            return 100.0
            
        inflation = params.get('inflation_rate', 0.02)
        
        # Find first non-zero withdrawal year
        first_withdrawal_idx = None
        for i, w in enumerate(withdrawals):
            if w > 0:
                first_withdrawal_idx = i
                break
        
        if first_withdrawal_idx is None:
            return 100.0
        
        # Slice from first withdrawal onward
        withdrawal_phase = withdrawals[first_withdrawal_idx:]
        
        if len(withdrawal_phase) < 2:
            return 100.0
        
        # Use real (inflation-adjusted) withdrawals
        real_withdrawals = []
        for i, amount in enumerate(withdrawal_phase):
            # If we hit a zero withdrawal (and we had started withdrawing), stop.
            # This decouples "Stability" (smoothness) from "Risk" (running out).
            # If you run out of money, your Stability score stays high (you were stable until you died),
            # but your Risk score tanks.
            if amount <= 0:
                break
                
            year = first_withdrawal_idx + i + 1
            real_value = amount / ((1 + inflation) ** (year - 1))
            real_withdrawals.append(real_value)
        
        if not real_withdrawals:
            return 0.0

        mean_withdrawal = np.mean(real_withdrawals)
        std_withdrawal = np.std(real_withdrawals)
        
        if mean_withdrawal <= 0:
            return 0.0
        
        # Coefficient of variation
        cv = std_withdrawal / mean_withdrawal
        
        # Formula: 100 - (CV * 143)
        # CV 0.0 = 100 (perfectly stable), CV 0.3 = 57 (tolerable), CV 0.7 = 0 (wild swings)
        return max(0.0, 100 - (cv * 143))

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Income Predictability\n"
            f"  - **Concept**: Measures volatility of withdrawals. Users prefer steady income over feast-and-famine.\n"
            f"  - **Formula**: `Score = 100 - (Coefficient of Variation × 143)`\n"
            f"  - **Normalization**: CV-based penalty (lower CV = higher score)\n"
            f"  - **Scoring**:\n\n"
            f"    | CV (StdDev/Mean) | Score | Meaning |\n"
            f"    |------------------|-------|---------|\n"
            f"    | 0.0 | 100 | Perfectly stable income |\n"
            f"    | 0.1 | 86 | Minor fluctuations (±10%) |\n"
            f"    | 0.3 | 57 | Moderate variation (tolerable) |\n"
            f"    | 0.5 | 28 | Significant swings |\n"
            f"    | 0.7+ | 0 | Wild swings, hard to plan |\n"
        )

class RiskScoreMetric(BaseMetric):
    """
    Measures portfolio survival probability and tail risk.
    
    Success Rate Definition:
        success_rate = fraction of simulations where final net worth > 0 at maturity.
        This measures portfolio survival TO MATURITY (end of simulation), not whether
        net worth ever dipped below zero during the simulation.
        Calculated in stats.py as: 1.0 - (final_net_worths <= 0).mean()
    
    Tail Risk (CVaR 95%):
        Conditional Value at Risk at 95% confidence. Measures the average loss
        in the worst 5% of scenarios. Industry standard (Basel III compliant).
    """
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        success_rate = stats.get('success_rate', 0.0)
        cvar_loss = stats.get('cvar_95_loss', 0.0)
        initial = params.get('initial_investment', 0)
        
        success_score = success_rate * 100
        
        # tail_risk_score: 100 = no loss, 0 = total loss
        # When cvar_loss is NEGATIVE (a gain!), clamp to 100
        if initial > 0:
            tail_risk_score = 100 - (cvar_loss / initial) * 100
            tail_risk_score = max(0, min(100, tail_risk_score))  # Clamp to 0-100
        else:
            tail_risk_score = 0
        
        # 80% Success Rate, 20% Tail Risk
        return (0.80 * success_score) + (0.20 * tail_risk_score)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Portfolio Survival & Tail Risk\n"
            f"  - **Concept**: Composite measure of not running out of money.\n"
            f"  - **Formula**: `Score = 0.8 × Success Rate + 0.2 × Tail Risk`\n"
            f"  - **Note**: Success Rate = % of simulations where final net worth > 0 at maturity (CVaR 95% for tail risk)\n"
            f"  - **Scoring**:\n\n"
            f"    | Success Rate | Tail Risk | Score | Meaning |\n"
            f"    |--------------|-----------|-------|---------|\n"
            f"    | 100% | Low | 100 | Never runs out |\n"
            f"    | 95% | Low | ~85 | Very safe |\n"
            f"    | 80% | High | ~65 | Risky strategy |\n"
            f"    | 50% | High | ~40 | Coin flip |\n"
        )

class RobustnessScoreMetric(BaseMetric):
    """Note: Robustness is calculated differently (aggregating across all scenarios)."""
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        # Placeholder within scenario loop - actual calculation happens in aggregate
        return 50.0 
    
    def calculate_aggregate(self, scenario_results: List[Dict], category: str = None) -> float:
        """
        Calculates score based on consistency across all scenarios.
        
        For CONTRIBUTION_ONLY strategies, uses max drawdown consistency instead of
        Sortino ratios, since accumulation strategies always have high Sortino/success
        rates making the standard approach non-discriminative.
        """
        if category == 'CONTRIBUTION_ONLY':
            return self._calculate_drawdown_robustness(scenario_results)
        return self._calculate_sortino_robustness(scenario_results)
    
    def _calculate_sortino_robustness(self, scenario_results: List[Dict]) -> float:
        """Standard robustness: Sortino ratio consistency across scenarios."""
        sortino_ratios = []
        success_rates = []
        
        for sc in scenario_results:
            stats = sc['stats']
            sortino_ratios.append(stats.get('strategy_sortino_ratio', 0.0))
            success_rates.append(stats.get('success_rate', 0.0))
            
        sortino_std = np.std(sortino_ratios)
        success_rate_std = np.std(success_rates)
        worst_sortino = min(sortino_ratios)
        best_sortino = max(sortino_ratios) if max(sortino_ratios) > 0 else 1.0
        
        volatility_score = max(0, 100 - (sortino_std * 50))
        consistency_score = max(0, 100 - (success_rate_std * 200))
        
        if best_sortino > 0:
            worst_case_score = max(0, (worst_sortino / best_sortino) * 100)
        else:
            worst_case_score = 0.0
        
        return (0.40 * worst_case_score + 0.30 * volatility_score + 0.30 * consistency_score)
    
    def _calculate_drawdown_robustness(self, scenario_results: List[Dict]) -> float:
        """
        Drawdown-based robustness for accumulation strategies.
        
        Uses max drawdown and Ulcer Index consistency across scenarios,
        which differentiates accumulation strategies better than Sortino.
        """
        max_drawdowns = []  # These are negative (e.g., -0.30 = 30% drawdown)
        ulcer_indices = []
        
        for sc in scenario_results:
            stats = sc['stats']
            # Use strategy-level metrics from stats.py
            # max_drawdown is stored as negative percentage in stats (via calculate_max_drawdown)
            md = stats.get('strategy_max_drawdown', 0.0)
            max_drawdowns.append(abs(md))  # Convert to positive for easier comparison
            ulcer_indices.append(stats.get('median_strategy_ulcer_index', 0.0))
        
        if not max_drawdowns:
            return 50.0
        
        # Worst-case drawdown score: smaller worst drawdown = better
        # 0% drawdown = 100, 50%+ drawdown = 0
        worst_drawdown = max(max_drawdowns)  # Largest drawdown across scenarios
        worst_case_score = max(0, 100 - (worst_drawdown * 200))
        
        # Drawdown consistency: low std = all scenarios similar
        dd_std = np.std(max_drawdowns)
        consistency_score = max(0, 100 - (dd_std * 500))
        
        # Ulcer Index consistency: lower is better
        avg_ulcer = np.mean(ulcer_indices) if ulcer_indices else 0.0
        ulcer_score = max(0, 100 - (avg_ulcer * 2))  # UI 0 = 100, UI 50 = 0
        
        return (0.40 * worst_case_score + 0.30 * consistency_score + 0.30 * ulcer_score)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: All-Weather Consistency\n"
            f"  - **Concept**: Penalizes strategies that only work in specific market conditions.\n"
            f"  - **Formula (Withdrawal/Hybrid)**: `0.4 × Worst Case Sortino + 0.3 × Volatility + 0.3 × Consistency`\n"
            f"  - **Formula (Accumulation)**: `0.4 × Worst Drawdown + 0.3 × Drawdown Consistency + 0.3 × Ulcer Index`\n"
            f"  - **Scoring**:\n\n"
            f"    | Worst/Best Ratio | Consistency | Score | Meaning |\n"
            f"    |------------------|-------------|-------|---------|\n"
            f"    | 0.9+ | High | 90+ | Works everywhere |\n"
            f"    | 0.5 | Medium | ~60 | Some variability |\n"
            f"    | 0.2 | Low | ~30 | Bull market only |\n"
        )

class CapitalEfficiencyMetric(BaseMetric):
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        initial = params.get('initial_investment', 0)
        inflation = params.get('inflation_rate', 0.02)
        years = params.get('num_years', 40)
        
        median_total_withdrawn = stats.get('median_total_withdrawn', 0)
        median_total_contributions = stats.get('median_total_contributions', 0)
        
        # Discount contributions and withdrawals to Year 0 real terms
        adj_factor = (1 + inflation) ** (years / 2)
        real_contributions = median_total_contributions / adj_factor
        real_withdrawals = median_total_withdrawn / adj_factor
        
        total_inputs = initial + real_contributions
        # Consumption-only: excludes Legacy/final net worth (measured separately by LegacyScoreMetric)
        total_outputs = real_withdrawals
        
        if total_inputs <= 0:
            return 0.0
        
        efficiency_ratio = total_outputs / total_inputs
        
        # Sigmoid scoring
        k = 2.5
        x0 = 2.0
        score = 100 / (1 + np.exp(-k * (efficiency_ratio - x0)))
        
        if efficiency_ratio < 0.5:
            score = 0.0
        elif efficiency_ratio > 5.0:
            score = 100.0
            
        return float(score)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Lifetime Consumption Efficiency\n"
            f"  - **Concept**: Total real withdrawals vs total real inputs (excludes legacy).\n"
            f"  - **Formula**: `Real Withdrawals / (Initial + Contributions)`\n"
            f"  - **Key difference**: Unlike Legacy Score (terminal wealth), this measures how much you actually consumed.\n"
            f"  - **Normalization**: Sigmoid centered at 2.0x\n"
            f"  - **Scoring**:\n\n"
            f"    | Efficiency Ratio | Score | Meaning |\n"
            f"    |------------------|-------|---------|\n"
            f"    | 0.5x | 0 | Got back less than half |\n"
            f"    | 1.0x | ~12 | Consumed what you put in |\n"
            f"    | 2.0x | ~50 | Consumed double |\n"
            f"    | 3.0x | ~85 | Consumed triple |\n"
            f"    | 5.0x+ | 100 | Exceptional consumption |\n"
        )

class LegacyScoreMetric(BaseMetric):
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        initial = params.get('initial_investment', 0)
        inflation = params.get('inflation_rate', 0.02)
        years = params.get('num_years', 40)
        median_total_contributions = stats.get('median_total_contributions', 0)
        median_final_real_nw = stats.get('median_final_real_net_worth', 0.0)
        
        # Total capital invested (Real Year 0 terms)
        # Approximate contribution discounting by using midpoint
        adj_factor = (1 + inflation) ** (years / 2)
        real_contributions = median_total_contributions / adj_factor
        total_invested = initial + real_contributions
        
        if total_invested <= 0:
            return 0.0
            
        # Sigmoid based on Preservation Ratio
        # 1.0 = 100% preservation (all buying power kept)
        k = 4.0
        x = median_final_real_nw / total_invested
        x0 = 0.75 # Center point (50 score)
        
        score = 100 / (1 + np.exp(-k * (x - x0)))
        return float(score)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Capital Preservation\n"
            f"  - **Concept**: Real wealth remaining at end vs total investment.\n"
            f"  - **Formula**: `Final Real Net Worth / Total Real Invested`\n"
            f"  - **Normalization**: Sigmoid centered at 0.75x\n"
            f"  - **Scoring**:\n\n"
            f"    | Preservation Ratio | Score | Meaning |\n"
            f"    |--------------------|-------|---------|\n"
            f"    | 0% | 2 | Spent everything |\n"
            f"    | 50% | ~18 | Half remaining |\n"
            f"    | 75% | ~50 | Most preserved |\n"
            f"    | 100% | ~88 | Fully preserved |\n"
            f"    | 150%+ | ~98 | Grew principal |\n"
        )

class AdequacyScoreMetric(BaseMetric):
    """Deprecated / Zero Weight"""
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        return 0.0
        
    def describe_score_components(self) -> str:
        return ""

class UsabilityScoreMetric(BaseMetric):
    """Deprecated / Zero Weight"""
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        return 0.0

    def describe_score_components(self) -> str:
        return ""


class ConsumptionRatioMetric(BaseMetric):
    """
    Measures pure withdrawal efficiency - withdrawals / inputs (excludes legacy).
    
    This is the key metric for "Die With Zero" strategies that prioritize
    maximizing lifetime consumption without caring about leftover capital.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['WITHDRAWAL_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        # Check category applicability
        category = context.get('category', 'WITHDRAWAL_ONLY') if context else 'WITHDRAWAL_ONLY'
        if not self.is_applicable(category):
            return None  # Not applicable to contribution-only strategies
        
        initial = params.get('initial_investment', 0)
        inflation = params.get('inflation_rate', 0.02)
        years = params.get('num_years', 40)
        
        median_total_withdrawn = stats.get('median_total_withdrawn', 0)
        median_total_contributions = stats.get('median_total_contributions', 0)
        
        # Discount to Year 0 real terms (using midpoint approximation)
        adj_factor = (1 + inflation) ** (years / 2)
        real_contributions = median_total_contributions / adj_factor
        real_withdrawals = median_total_withdrawn / adj_factor
        
        total_inputs = initial + real_contributions
        
        if total_inputs <= 0:
            return 0.0
        
        # Pure consumption ratio (excludes legacy!)
        consumption_ratio = real_withdrawals / total_inputs
        
        # Sigmoid normalization: 1.0x = ~27 pts, 1.5x = ~50 pts, 2.5x = ~88 pts
        k = 2.0   # Steepness
        x0 = 1.5  # Center point (50 score)
        score = 100 / (1 + np.exp(-k * (consumption_ratio - x0)))
        
        # Edge case clamping
        if consumption_ratio < 0.5:
            score = 0.0
        elif consumption_ratio > 4.0:
            score = 100.0
            
        return float(score)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Pure Withdrawal Efficiency\n"
            f"  - **Concept**: Measures how much you consumed vs what you invested (excludes legacy).\n"
            f"  - **Formula**: `Ratio = Real_Withdrawals / (Initial + Real_Contributions)`\n"
            f"  - **Key difference**: Unlike Capital Efficiency, this does NOT reward leaving money behind.\n"
            f"  - **Normalization**: Sigmoid curve centered at 1.5x\n"
            f"    - `Score = 100 / (1 + e^(-2.0 × (ratio - 1.5)))`\n"
            f"  - **Scoring**:\n\n"
            f"    | Consumption Ratio | Score | Meaning |\n"
            f"    |-------------------|-------|---------|\n"
            f"    | 1.0x | 27 | Breakeven (withdrew what you put in) |\n"
            f"    | 1.5x | 50 | Consumed 50% more than invested |\n"
            f"    | 2.5x | 88 | More than doubled consumption |\n"
            f"    | 4.0x+ | 100 | Excellent market leverage |\n"
        )


class CoastFIREMetric(BaseMetric):
    """
    Measures how quickly a strategy reaches the Coast FIRE point.
    
    Coast FIRE = when you can stop contributing and growth alone will reach retirement targets.
    This metric uses ROI ratio (Final Wealth / Total Invested) as a proxy for speed to independence.
    
    Higher ROI = faster path to Coast FIRE = higher score.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['CONTRIBUTION_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        category = context.get('category', 'CONTRIBUTION_ONLY') if context else 'CONTRIBUTION_ONLY'
        if not self.is_applicable(category):
            return None
        
        median_final_real_nw = stats.get('median_real_final_net_worth', 0)
        median_total_contributions = stats.get('median_total_contributions', 0)
        initial = params.get('initial_investment', 0)
        num_years = params.get('num_years', 30)
        inflation = params.get('inflation_rate', 0.02)
        
        # Discount contributions to Year 0 real terms (midpoint approximation)
        adj_factor = (1 + inflation) ** (num_years / 2)
        real_contributions = median_total_contributions / adj_factor
        total_invested = initial + real_contributions
        
        if total_invested <= 0:
            return 0.0
        
        # ROI ratio = Final Wealth / Total Invested
        # Higher ratio = more growth vs contributions = faster Coast FIRE
        roi_ratio = median_final_real_nw / total_invested
        
        # Scoring:
        # 1.0x = 0 points (breakeven only)
        # 2.0x = 25 points (doubled money)
        # 3.0x = 50 points (tripled)
        # 5.0x+ = 100 points (5x or more)
        
        if roi_ratio <= 1.0:
            return 0.0
        elif roi_ratio >= 5.0:
            return 100.0
        else:
            # Linear scale from 1.0 to 5.0
            score = ((roi_ratio - 1.0) / 4.0) * 100
            return min(100.0, score)
    
    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Coast FIRE Timeline\n"
            f"  - **Concept**: How quickly does growth exceed contributions? (Coast FIRE milestone)\n"
            f"  - **Philosophy**: The faster you reach a point where you can stop contributing and still hit retirement goals, the more financially free you are.\n"
            f"  - **Formula**: `ROI Ratio = Final Real Wealth / (Initial + Real Contributions)`\n"
            f"  - **Scoring**:\n\n"
            f"    | ROI Ratio | Score | Meaning |\n"
            f"    |-----------|-------|---------|\n"
            f"    | 1.0x | 0 | Breakeven only |\n"
            f"    | 2.0x | 25 | Doubled invested capital |\n"
            f"    | 3.0x | 50 | Tripled invested capital |\n"
            f"    | 5.0x+ | 100 | Exceptional growth (5x or more) |\n"
        )


class AccumulationVelocityMetric(BaseMetric):
    """
    Measures the rate of wealth accumulation (CAGR).
    
    Higher velocity = faster wealth building = higher score.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['CONTRIBUTION_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        category = context.get('category', 'CONTRIBUTION_ONLY') if context else 'CONTRIBUTION_ONLY'
        if not self.is_applicable(category):
            return None
        
        median_final_real_nw = stats.get('median_real_final_net_worth', 0)
        num_years = params.get('num_years', 30)
        initial = params.get('initial_investment', 0)
        
        if num_years <= 0 or initial <= 0:
            return 0.0
        
        # Annualized growth rate (CAGR)
        cagr = ((median_final_real_nw / initial) ** (1 / num_years)) - 1
        
        # Score based on CAGR
        # 0% = 0 points (no growth)
        # 5% = 50 points (inflation + 3% real growth)
        # 10%+ = 100 points (exceptional)
        
        if cagr <= 0:
            return 0.0
        elif cagr >= 0.10:
            return 100.0
        else:
            score = (cagr / 0.10) * 100
            return min(100.0, score)
    
    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Wealth Accumulation Rate\n"
            f"  - **Concept**: How fast does wealth grow per year? (CAGR)\n"
            f"  - **Formula**: `CAGR = (Final / Initial)^(1/Years) - 1`\n"
            f"  - **Scoring**:\n\n"
            f"    | CAGR | Score | Meaning |\n"
            f"    |------|-------|---------|\n"
            f"    | 0% | 0 | No real growth |\n"
            f"    | 5% | 50 | Moderate growth (inflation + 3%) |\n"
            f"    | 10%+ | 100 | Exceptional growth |\n"
        )


class ContributionEfficiencyMetric(BaseMetric):
    """
    Measures growth generated per dollar contributed.
    
    This answers: "For every $1 I saved, how much wealth did the market create?"
    Similar to Capital Efficiency but focuses specifically on ROI from contributions.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['CONTRIBUTION_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        category = context.get('category', 'CONTRIBUTION_ONLY') if context else 'CONTRIBUTION_ONLY'
        if not self.is_applicable(category):
            return None
        
        median_total_contributions = stats.get('median_total_contributions', 0)
        median_final_real_nw = stats.get('median_real_final_net_worth', 0)
        initial = params.get('initial_investment', 0)
        num_years = params.get('num_years', 30)
        inflation = params.get('inflation_rate', 0.02)
        
        if median_total_contributions <= 0:
            # No contributions made - don't penalize
            return 100.0
        
        # Discount contributions to Year 0 real terms
        adj_factor = (1 + inflation) ** (num_years / 2)
        real_contributions = median_total_contributions / adj_factor
        
        # Growth attributable to contributions = (Final - Initial)
        # This is the wealth created beyond the starting capital
        growth_from_contributions = median_final_real_nw - initial
        
        if real_contributions <= 0:
            return 0.0
        
        # Efficiency = Growth / Contributions
        efficiency = growth_from_contributions / real_contributions
        
        # Scoring:
        # 1.0x = 25 points (contributions preserved real value)
        # 2.0x = 50 points (doubled contribution value through growth)
        # 4.0x+ = 100 points (quadrupled or more)
        
        if efficiency <= 0:
            return 0.0
        elif efficiency >= 4.0:
            return 100.0
        else:
            score = (efficiency / 4.0) * 100
            return min(100.0, score)
    
    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Contribution ROI\n"
            f"  - **Concept**: How much wealth was generated per dollar contributed?\n"
            f"  - **Formula**: `(Final Wealth - Initial) / Total Real Contributions`\n"
            f"  - **Scoring**:\n\n"
            f"    | Multiplier | Score | Meaning |\n"
            f"    |------------|-------|---------|\n"
            f"    | 1.0x | 25 | Contributions preserved value |\n"
            f"    | 2.0x | 50 | Doubled contribution value |\n"
            f"    | 4.0x+ | 100 | Quadrupled or more |\n"
        )


class SharpeRatioMetric(BaseMetric):
    """
    Risk-adjusted return using the Sharpe Ratio.
    
    Measures excess return per unit of total volatility.
    Uses strategy_sharpe_ratio already computed in stats.py.
    Industry standard for comparing risk-adjusted performance.
    """
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        sharpe = stats.get('strategy_sharpe_ratio', 0.0)
        
        # Scoring: Sharpe < 0 = 0pts, 1.0 = 50pts, 2.0+ = 100pts
        if sharpe <= 0:
            return 0.0
        elif sharpe >= 2.0:
            return 100.0
        else:
            return (sharpe / 2.0) * 100.0

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Risk-Adjusted Return (Sharpe Ratio)\n"
            f"  - **Concept**: Excess return per unit of total volatility. Industry standard for comparing performance.\n"
            f"  - **Formula**: `(Strategy Return - Risk-Free Rate) / Volatility`\n"
            f"  - **Key difference**: Unlike Risk Score (survival probability), Sharpe measures efficiency of risk-taking.\n"
            f"  - **Scoring**:\n\n"
            f"    | Sharpe Ratio | Score | Meaning |\n"
            f"    |-------------|-------|---------|\n"
            f"    | < 0 | 0 | Losing money on risk-adjusted basis |\n"
            f"    | 0.5 | 25 | Below average |\n"
            f"    | 1.0 | 50 | Good risk-adjusted return |\n"
            f"    | 2.0+ | 100 | Excellent (hedge fund territory) |\n"
        )


class CalmarRatioMetric(BaseMetric):
    """
    Return relative to maximum drawdown.
    
    Calmar = Annualized Return / |Max Drawdown|
    Measures how much return is generated per unit of worst-case pain.
    """
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        calmar = stats.get('strategy_calmar_ratio', 0.0)
        
        # Scoring: Calmar < 0 = 0pts, 1.0 = 33pts, 3.0+ = 100pts
        if calmar <= 0:
            return 0.0
        elif calmar >= 3.0:
            return 100.0
        else:
            return (calmar / 3.0) * 100.0

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Return vs Drawdown (Calmar Ratio)\n"
            f"  - **Concept**: Annualized return divided by maximum drawdown. Higher = better risk-return tradeoff.\n"
            f"  - **Formula**: `Annualized Return / |Max Drawdown|`\n"
            f"  - **Key difference**: Unlike Robustness (consistency), Calmar measures return per unit of worst-case pain.\n"
            f"  - **Scoring**:\n\n"
            f"    | Calmar Ratio | Score | Meaning |\n"
            f"    |-------------|-------|---------|\n"
            f"    | < 0 | 0 | Negative returns |\n"
            f"    | 1.0 | 33 | Moderate risk-return |\n"
            f"    | 2.0 | 67 | Good risk-return |\n"
            f"    | 3.0+ | 100 | Excellent (minimal drawdown for return) |\n"
        )


class DownsideStabilityMetric(BaseMetric):
    """
    Income predictability using semi-deviation (downside only).
    
    Unlike WithdrawalStabilityMetric which penalizes ALL volatility (including
    beneficial upside), this metric only penalizes downside deviation.
    Aligns with the Sortino philosophy: don't punish positive volatility.
    """
    
    def __init__(self, **kwargs):
        super().__init__(
            applicable_categories=['WITHDRAWAL_ONLY', 'HYBRID'],
            **kwargs
        )
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None):
        category = context.get('category', 'WITHDRAWAL_ONLY') if context else 'WITHDRAWAL_ONLY'
        if not self.is_applicable(category):
            return None
        
        withdrawals = stats.get('drawdown_history', [])
        if not withdrawals:
            return 100.0
            
        inflation = params.get('inflation_rate', 0.02)
        
        # Find first non-zero withdrawal year
        first_withdrawal_idx = None
        for i, w in enumerate(withdrawals):
            if w > 0:
                first_withdrawal_idx = i
                break
        
        if first_withdrawal_idx is None:
            return 100.0
        
        # Slice from first withdrawal onward
        withdrawal_phase = withdrawals[first_withdrawal_idx:]
        
        if len(withdrawal_phase) < 2:
            return 100.0
        
        # Convert to real (inflation-adjusted) terms, stop at zero (decouples from Risk)
        real_withdrawals = []
        for i, amount in enumerate(withdrawal_phase):
            if amount <= 0:
                break
            year = first_withdrawal_idx + i + 1
            real_value = amount / ((1 + inflation) ** (year - 1))
            real_withdrawals.append(real_value)
        
        if not real_withdrawals:
            return 0.0

        mean_withdrawal = np.mean(real_withdrawals)
        
        if mean_withdrawal <= 0:
            return 0.0
        
        # Semi-deviation: only penalize downside (withdrawals below mean)
        downside_deviations = [(w - mean_withdrawal) for w in real_withdrawals if w < mean_withdrawal]
        
        if not downside_deviations:
            return 100.0  # No downside volatility at all
        
        semi_dev = np.sqrt(np.mean([d**2 for d in downside_deviations]))
        
        # Downside CV = semi_dev / mean
        downside_cv = semi_dev / mean_withdrawal
        
        # Score: 100 - (downside_cv × 200)
        # Downside CV 0 = 100, 0.25 = 50, 0.5+ = 0
        return max(0.0, float(100 - (downside_cv * 200)))

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Downside Income Stability\n"
            f"  - **Concept**: Measures only DOWNSIDE withdrawal volatility (ignores positive deviations).\n"
            f"  - **Formula**: `Score = 100 - (Downside CV × 200)`\n"
            f"  - **Key difference**: Unlike Withdrawal Stability, does NOT punish positive income surprises.\n"
            f"  - **Scoring**:\n\n"
            f"    | Downside CV | Score | Meaning |\n"
            f"    |------------|-------|---------|\n"
            f"    | 0.0 | 100 | No downside income variation |\n"
            f"    | 0.1 | 80 | Minor income dips |\n"
            f"    | 0.25 | 50 | Moderate downside risk |\n"
            f"    | 0.5+ | 0 | Severe income instability |\n"
        )


class UlcerIndexMetric(BaseMetric):
    """
    Drawdown-depth-and-duration metric (Ulcer Index).
    
    The Ulcer Index captures both how deep drawdowns are and how long recovery takes.
    Unlike max drawdown (single worst event), Ulcer Index accounts for the entire
    drawdown experience over the simulation period.
    
    Uses median_strategy_ulcer_index already computed in stats.py.
    """
    
    def calculate(self, stats: Dict, params: Dict, context: Dict = None) -> float:
        ulcer = stats.get('median_strategy_ulcer_index', 0.0)
        
        # Scoring: UI 0 = 100pts, UI 50 = 50pts, UI 100+ = 0pts
        if ulcer <= 0:
            return 100.0
        elif ulcer >= 100:
            return 0.0
        else:
            return float(100 - ulcer)

    def describe_score_components(self) -> str:
        return (
            f"- **{self.name}**: Drawdown Pain (Ulcer Index)\n"
            f"  - **Concept**: Measures depth AND duration of drawdowns. Higher Ulcer Index = more pain.\n"
            f"  - **Formula**: `Score = 100 - Ulcer Index`\n"
            f"  - **Key difference**: Unlike Stability (income smoothness), Ulcer measures portfolio-level drawdown suffering.\n"
            f"  - **Scoring**:\n\n"
            f"    | Ulcer Index | Score | Meaning |\n"
            f"    |------------|-------|---------|\n"
            f"    | 0-10 | 90-100 | Minimal drawdown pain |\n"
            f"    | 20-30 | 70-80 | Moderate drawdowns |\n"
            f"    | 50 | 50 | Significant drawdown experience |\n"
            f"    | 100+ | 0 | Extreme and prolonged drawdowns |\n"
        )

