"""
Test category-aware metrics functionality.

Verifies that metrics correctly return None for incompatible strategy categories
and that scoring adjusts weights appropriately.
"""
import pytest
import numpy as np
from core.metrics import (
    WithdrawalStabilityMetric, ConsumptionRatioMetric, RiskScoreMetric,
    PresentValueMetric, CapitalEfficiencyMetric, RobustnessScoreMetric,
    SharpeRatioMetric, CalmarRatioMetric, DownsideStabilityMetric, UlcerIndexMetric
)


def test_withdrawal_stability_not_applicable_for_contribution():
    """Withdrawal Stability should return None for contribution strategies."""
    metric = WithdrawalStabilityMetric(weight=0.15, name="Withdrawal Stability")
    
    stats = {'drawdown_history': [0, 0, 0]}  # No withdrawals
    params = {'inflation_rate': 0.02}
    context = {'category': 'CONTRIBUTION_ONLY'}
    
    result = metric.calculate(stats, params, context)
    assert result is None, "Should return None for contribution strategies"


def test_withdrawal_stability_applies_to_withdrawal_only():
    """Withdrawal Stability should work for withdrawal-only strategies."""
    metric = WithdrawalStabilityMetric(weight=0.15, name="Withdrawal Stability")
    
    stats = {'drawdown_history': [40000, 41000, 40500, 41500]}  
    params = {'inflation_rate': 0.02}
    context = {'category': 'WITHDRAWAL_ONLY'}
    
    result = metric.calculate(stats, params, context)
    assert result is not None, "Should calculate for withdrawal-only strategies"
    assert 0 <= result <= 100, f"Score should be 0-100, got {result}"


def test_withdrawal_stability_applies_to_hybrid():
    """Withdrawal Stability should work for hybrid strategies."""
    metric = WithdrawalStabilityMetric(weight=0.15, name="Withdrawal Stability")
    
    stats = {'drawdown_history': [40000, 41000, 40500]}
    params = {'inflation_rate': 0.02}
    context = {'category': 'HYBRID'}
    
    result = metric.calculate(stats, params, context)
    assert result is not None, "Should calculate for hybrid strategies"


def test_consumption_ratio_not_applicable_for_contribution():
    """Consumption Ratio should return None for contribution strategies."""
    metric = ConsumptionRatioMetric(weight=0.00, name="Consumption Ratio")
    
    stats = {
        'median_total_withdrawn': 0,
        'median_total_contributions': 500000
    }
    params = {
        'initial_investment': 100000,
        'inflation_rate': 0.02,
        'num_years': 30
    }
    context = {'category': 'CONTRIBUTION_ONLY'}
    
    result = metric.calculate(stats, params, context)
    assert result is None, "Should return None for contribution strategies"


def test_risk_score_applies_to_all_categories():
    """Risk Score should work for all strategy types."""
    metric = RiskScoreMetric(weight=0.20, name="Risk Score")
    
    stats = {'success_rate': 0.95, 'cvar_95_loss': 50000}
    params = {'initial_investment': 1000000}
    
    for category in ['WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', 'HYBRID']:
        context = {'category': category}
        result = metric.calculate(stats, params, context)
        assert result is not None, f"Risk score should apply to {category}"
        assert 0 <= result <= 100, f"Score should be 0-100 for {category}, got {result}"


def test_universal_metrics_have_all_categories():
    """Metrics like Risk Score, Present Value should apply to all categories."""
    universal_metrics = [
        RiskScoreMetric(weight=0.20),
        CapitalEfficiencyMetric(weight=0.15)
    ]
    
    for metric in universal_metrics:
        assert 'WITHDRAWAL_ONLY' in metric.applicable_categories
        assert 'CONTRIBUTION_ONLY' in metric.applicable_categories
        assert 'HYBRID' in metric.applicable_categories


def test_withdrawal_metrics_restricted_categories():
    """Withdrawal-focused metrics should not include CONTRIBUTION_ONLY."""
    withdrawal_metrics = [
        WithdrawalStabilityMetric(weight=0.15),
        ConsumptionRatioMetric(weight=0.00),
        PresentValueMetric(weight=0.20)
    ]
    
    for metric in withdrawal_metrics:
        assert 'WITHDRAWAL_ONLY' in metric.applicable_categories
        assert 'HYBRID' in metric.applicable_categories
        assert 'CONTRIBUTION_ONLY' not in metric.applicable_categories, \
            f"{metric.name} should not apply to CONTRIBUTION_ONLY"


def test_is_applicable_method():
    """Test is_applicable method works correctly."""
    metric = WithdrawalStabilityMetric(weight=0.15)
    
    assert metric.is_applicable('WITHDRAWAL_ONLY') == True
    assert metric.is_applicable('HYBRID') == True
    assert metric.is_applicable('CONTRIBUTION_ONLY') == False


# ============================================================================
# Phase 1: Scoring System Improvements Tests
# ============================================================================

def test_withdrawal_stability_cv_threshold_adjusted():
    """CV=0.3 should score ~57 with the adjusted threshold (was 40 with old multiplier)."""
    metric = WithdrawalStabilityMetric(weight=0.15, name="Withdrawal Stability")
    
    # Create withdrawals with CV ≈ 0.3
    # Mean=40000, StdDev=12000 → CV=0.3
    mean_val = 40000
    withdrawals = [mean_val + 12000, mean_val - 12000, mean_val + 12000, mean_val - 12000,
                   mean_val + 12000, mean_val - 12000, mean_val + 12000, mean_val - 12000]
    
    stats = {'drawdown_history': withdrawals}
    params = {'inflation_rate': 0.0}  # No inflation for clean CV calculation
    context = {'category': 'WITHDRAWAL_ONLY'}
    
    result = metric.calculate(stats, params, context)
    assert result is not None
    # With CV ≈ 0.3 and multiplier 143: score ≈ 100 - 0.3*143 ≈ 57
    # Allow some tolerance for inflation adjustment effects
    assert result > 40, f"CV=0.3 should score above 40, got {result}"
    assert result < 75, f"CV=0.3 should score below 75, got {result}"


def test_withdrawal_stability_cv_high_scores_zero():
    """CV=0.7+ should score 0 with the adjusted threshold."""
    metric = WithdrawalStabilityMetric(weight=0.15, name="Withdrawal Stability")
    
    # Very high variability withdrawals
    withdrawals = [80000, 10000, 80000, 10000, 80000, 10000, 80000, 10000]
    
    stats = {'drawdown_history': withdrawals}
    params = {'inflation_rate': 0.0}
    context = {'category': 'WITHDRAWAL_ONLY'}
    
    result = metric.calculate(stats, params, context)
    assert result is not None
    assert result < 5, f"Very high CV should score near 0, got {result}"


def test_robustness_drawdown_differentiates_accumulation():
    """Robustness drawdown-based scoring should differentiate accumulation strategies."""
    metric = RobustnessScoreMetric(weight=0.05, name="Robustness Score")
    
    # Scenario with low drawdowns (good accumulation strategy)
    low_dd_scenarios = [
        {'stats': {'strategy_max_drawdown': -0.05, 'median_strategy_ulcer_index': 5.0}},
        {'stats': {'strategy_max_drawdown': -0.08, 'median_strategy_ulcer_index': 8.0}},
        {'stats': {'strategy_max_drawdown': -0.06, 'median_strategy_ulcer_index': 6.0}},
    ]
    
    # Scenario with high drawdowns (bad accumulation strategy)
    high_dd_scenarios = [
        {'stats': {'strategy_max_drawdown': -0.40, 'median_strategy_ulcer_index': 40.0}},
        {'stats': {'strategy_max_drawdown': -0.50, 'median_strategy_ulcer_index': 55.0}},
        {'stats': {'strategy_max_drawdown': -0.35, 'median_strategy_ulcer_index': 35.0}},
    ]
    
    low_dd_score = metric.calculate_aggregate(low_dd_scenarios, category='CONTRIBUTION_ONLY')
    high_dd_score = metric.calculate_aggregate(high_dd_scenarios, category='CONTRIBUTION_ONLY')
    
    assert low_dd_score > high_dd_score, \
        f"Low drawdown should score higher ({low_dd_score}) than high drawdown ({high_dd_score})"
    assert low_dd_score > 60, f"Low drawdown strategy should score well, got {low_dd_score}"
    assert high_dd_score < low_dd_score - 20, \
        f"Score gap should be meaningful (>20 points), got {low_dd_score - high_dd_score}"


def test_robustness_sortino_for_withdrawal():
    """Robustness should use Sortino-based scoring for withdrawal strategies (backward compat)."""
    metric = RobustnessScoreMetric(weight=0.05, name="Robustness Score")
    
    scenarios = [
        {'stats': {'strategy_sortino_ratio': 2.0, 'success_rate': 0.95}},
        {'stats': {'strategy_sortino_ratio': 1.8, 'success_rate': 0.92}},
        {'stats': {'strategy_sortino_ratio': 1.5, 'success_rate': 0.88}},
    ]
    
    # Should use Sortino path for withdrawal (not drawdown path)
    score_withdrawal = metric.calculate_aggregate(scenarios, category='WITHDRAWAL_ONLY')
    score_hybrid = metric.calculate_aggregate(scenarios, category='HYBRID')
    score_none = metric.calculate_aggregate(scenarios, category=None)
    
    # All non-CONTRIBUTION_ONLY should use the same Sortino path
    assert score_withdrawal == score_hybrid == score_none, \
        "Withdrawal, Hybrid, and None should all use Sortino-based robustness"
    assert 0 <= score_withdrawal <= 100, f"Score should be 0-100, got {score_withdrawal}"


# =============================================
# Phase 2: New Metric Tests
# =============================================

def test_sharpe_ratio_boundary_values():
    """SharpeRatioMetric should score 0 for negative, linearly to 100 at 2.0."""
    metric = SharpeRatioMetric(weight=0.0, name="Sharpe Ratio")
    
    # Negative Sharpe = 0
    assert metric.calculate({'strategy_sharpe_ratio': -0.5}, {}) == 0.0
    # Zero Sharpe = 0
    assert metric.calculate({'strategy_sharpe_ratio': 0.0}, {}) == 0.0
    # Sharpe 1.0 = 50
    assert metric.calculate({'strategy_sharpe_ratio': 1.0}, {}) == 50.0
    # Sharpe 2.0 = 100
    assert metric.calculate({'strategy_sharpe_ratio': 2.0}, {}) == 100.0
    # Sharpe > 2.0 capped at 100
    assert metric.calculate({'strategy_sharpe_ratio': 5.0}, {}) == 100.0
    # Missing stat defaults to 0 → score 0
    assert metric.calculate({}, {}) == 0.0


def test_calmar_ratio_scoring_range():
    """CalmarRatioMetric should score 0 for negative, linearly to 100 at 3.0."""
    metric = CalmarRatioMetric(weight=0.0, name="Calmar Ratio")
    
    assert metric.calculate({'strategy_calmar_ratio': -1.0}, {}) == 0.0
    assert metric.calculate({'strategy_calmar_ratio': 0.0}, {}) == 0.0
    score_1 = metric.calculate({'strategy_calmar_ratio': 1.0}, {})
    assert abs(score_1 - 33.33) < 1.0, f"Calmar 1.0 should be ~33, got {score_1}"
    assert metric.calculate({'strategy_calmar_ratio': 3.0}, {}) == 100.0
    assert metric.calculate({'strategy_calmar_ratio': 10.0}, {}) == 100.0


def test_downside_stability_category_awareness():
    """DownsideStabilityMetric should return None for CONTRIBUTION_ONLY."""
    metric = DownsideStabilityMetric(weight=0.0, name="Downside Stability")
    
    stats = {'drawdown_history': [50000, 50000, 50000]}
    params = {'inflation_rate': 0.02}
    
    # Should return None for accumulation
    assert metric.calculate(stats, params, {'category': 'CONTRIBUTION_ONLY'}) is None
    
    # Should return a score for withdrawal
    result = metric.calculate(stats, params, {'category': 'WITHDRAWAL_ONLY'})
    assert result is not None
    assert 0.0 <= result <= 100.0


def test_downside_stability_ignores_upside():
    """DownsideStabilityMetric should not penalize upside volatility."""
    metric = DownsideStabilityMetric(weight=0.0, name="Downside Stability")
    params = {'inflation_rate': 0.0}  # No inflation for simpler test
    context = {'category': 'WITHDRAWAL_ONLY'}
    
    # Perfectly stable withdrawals → score 100
    stable = [50000, 50000, 50000, 50000, 50000]
    score_stable = metric.calculate({'drawdown_history': stable}, params, context)
    assert score_stable == 100.0, f"Perfectly stable should be 100, got {score_stable}"
    
    # Only upside variation (some higher) should still score high
    upside_only = [50000, 60000, 70000, 80000, 90000]
    score_upside = metric.calculate({'drawdown_history': upside_only}, params, context)
    # Mean is 70k; only 50k is below mean → small downside CV
    assert score_upside > 50, f"Mostly upside variation should score high, got {score_upside}"
    
    # Severe downside variation should score low
    downside_heavy = [80000, 20000, 80000, 20000, 80000]
    score_downside = metric.calculate({'drawdown_history': downside_heavy}, params, context)
    assert score_downside < score_upside, \
        f"Downside-heavy ({score_downside}) should score lower than upside-only ({score_upside})"


def test_ulcer_index_inverse_scoring():
    """UlcerIndexMetric should score inversely: low ulcer = high score."""
    metric = UlcerIndexMetric(weight=0.0, name="Ulcer Index")
    
    # Zero ulcer = perfect score
    assert metric.calculate({'median_strategy_ulcer_index': 0.0}, {}) == 100.0
    # Ulcer 50 = 50 points
    assert metric.calculate({'median_strategy_ulcer_index': 50.0}, {}) == 50.0
    # Ulcer 100+ = 0 points
    assert metric.calculate({'median_strategy_ulcer_index': 100.0}, {}) == 0.0
    assert metric.calculate({'median_strategy_ulcer_index': 150.0}, {}) == 0.0
    # Missing stat → 0.0 ulcer → 100
    assert metric.calculate({}, {}) == 100.0


def test_new_metrics_registered_in_registry():
    """All 4 new metrics should be registered in METRIC_REGISTRY."""
    from core.strategy_evaluation import METRIC_REGISTRY
    
    new_keys = ['sharpe_ratio_score', 'calmar_ratio_score', 
                'downside_stability_score', 'ulcer_index_score']
    
    for key in new_keys:
        assert key in METRIC_REGISTRY, f"{key} not found in METRIC_REGISTRY"
        metric = METRIC_REGISTRY[key]
        assert metric.weight == 0.0, f"{key} should have 0 base weight, got {metric.weight}"


def test_downside_stability_stops_at_zero():
    """DownsideStabilityMetric should stop counting at zero withdrawals (decoupled from Risk)."""
    metric = DownsideStabilityMetric(weight=0.0, name="Downside Stability")
    params = {'inflation_rate': 0.0}
    context = {'category': 'WITHDRAWAL_ONLY'}
    
    # Withdrawals that go to zero mid-stream → only count pre-zero portion
    withdrawals = [50000, 50000, 50000, 0, 0, 0]
    result = metric.calculate({'drawdown_history': withdrawals}, params, context)
    assert result is not None
    # The 3 stable withdrawals should give a high score
    assert result == 100.0, f"Stable pre-zero withdrawals should be 100, got {result}"


# =============================================
# Phase 3: Capital Efficiency + Scenario Tests
# =============================================

def test_capital_efficiency_excludes_legacy():
    """CapitalEfficiencyMetric should NOT include final net worth in output (consumption-only)."""
    metric = CapitalEfficiencyMetric(weight=0.15, name="Capital Efficiency")
    
    # Strategy with zero withdrawals but huge legacy — should score poorly
    stats_legacy_only = {
        'median_total_withdrawn': 0,
        'median_total_contributions': 0,
        'median_real_final_net_worth': 5_000_000,  # Big legacy, but should be ignored
    }
    params = {'initial_investment': 1_000_000, 'inflation_rate': 0.02, 'num_years': 40}
    
    score = metric.calculate(stats_legacy_only, params)
    # With no withdrawals, efficiency ratio = 0 / 1M = 0 → score should be 0
    assert score == 0.0, f"No withdrawals should give 0 score even with legacy, got {score}"
    
    # Strategy with good withdrawals — should score well
    stats_good_withdrawals = {
        'median_total_withdrawn': 3_000_000,
        'median_total_contributions': 0,
        'median_real_final_net_worth': 0,
    }
    score_with_withdrawals = metric.calculate(stats_good_withdrawals, params)
    assert score_with_withdrawals > 20, f"Good withdrawals should score well, got {score_with_withdrawals}"


def test_scenario_weights_sum_to_one():
    """TEST_SCENARIOS weights must sum to 1.0."""
    from core.strategy_evaluation import TEST_SCENARIOS
    
    total = sum(s['weight'] for s in TEST_SCENARIOS)
    assert abs(total - 1.0) < 1e-9, f"Scenario weights sum to {total}, expected 1.0"


def test_scenario_count():
    """TEST_SCENARIOS should have 10 scenarios after Phase 3."""
    from core.strategy_evaluation import TEST_SCENARIOS
    
    assert len(TEST_SCENARIOS) == 10, f"Expected 10 scenarios, got {len(TEST_SCENARIOS)}"
    names = [s['name'] for s in TEST_SCENARIOS]
    assert 'Stagflation' in names, "Stagflation scenario missing"
    assert 'Deflation' in names, "Deflation scenario missing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
