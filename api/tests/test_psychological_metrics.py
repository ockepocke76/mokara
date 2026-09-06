import pytest
import pandas as pd
from core.stats import (
    calculate_time_underwater,
    calculate_recovery_time,
    calculate_consecutive_declines,
    calculate_severe_drawdown_count,
    calculate_years_below_initial
)


def test_time_underwater_no_drawdown():
    """Test that continuous growth results in 0 time underwater."""
    net_worth = pd.Series([100, 110, 120, 130, 140])
    result = calculate_time_underwater(net_worth)
    assert result == 0


def test_time_underwater_partial():
    """Test time underwater with recovery periods."""
    # Year 0: 100, Year 1: 90 (underwater), Year 2: 110 (new peak), Year 3: 105 (underwater)
    net_worth = pd.Series([100, 90, 110, 105])
    result = calculate_time_underwater(net_worth)
    assert result == 2  # Years 1 and 3


def test_recovery_time_full_recovery():
    """Test recovery time when portfolio fully recovers."""
    # Peak 100, drop to 50, then gradual recovery to 100
    net_worth = pd.Series([100, 80, 60, 50, 70, 90, 100])
    result = calculate_recovery_time(net_worth)
    # Worst drawdown at index 3 (value 50), recovery at index 6 (value 100)
    assert result == 3  # 3 years from worst to recovery


def test_recovery_time_no_recovery():
    """Test recovery time when portfolio never recovers."""
    net_worth = pd.Series([100, 80, 60, 50, 55])
    result = calculate_recovery_time(net_worth)
    # Never recovered, so returns remaining years
    assert result == 1  # 1 year from worst drawdown to end


def test_consecutive_declines_simple():
    """Test consecutive declines with clear streak."""
    net_worth = pd.Series([100, 90, 80, 70, 80, 90])
    result = calculate_consecutive_declines(net_worth)
    assert result == 3  # Years with declines: indices 1, 2, 3


def test_consecutive_declines_multiple_streaks():
    """Test that function returns the longest streak."""
    net_worth = pd.Series([100, 90, 95, 85, 80, 90])
    result = calculate_consecutive_declines(net_worth)
    # Two streaks: 1 year (index 1) and 2 years (indices 3,4)
    assert result == 2


def test_severe_drawdown_count_single():
    """Test severe drawdown count with single event."""
    # Peak 100, drawdown to 70 (30% drop)
    net_worth = pd.Series([100, 90, 70, 80, 100])
    result = calculate_severe_drawdown_count(net_worth, threshold=0.20)
    assert result == 1  # One severe drawdown event


def test_severe_drawdown_count_multiple():
    """Test severe drawdown count with multiple events."""
    # Two distinct periods exceeding 20%
    net_worth = pd.Series([100, 75, 100, 70, 100])
    result = calculate_severe_drawdown_count(net_worth, threshold=0.20)
    assert result == 2  # Two distinct severe drawdowns


def test_years_below_initial():
    """Test years below initial investment."""
    initial = 100
    net_worth = pd.Series([100, 90, 85, 105, 95, 110])
    result = calculate_years_below_initial(net_worth, initial)
    assert result == 3  # Indices 1, 2, 4


def test_edge_case_empty_series():
    """Test all functions with empty series."""
    empty = pd.Series([])
    assert calculate_time_underwater(empty) == 0
    assert calculate_recovery_time(empty) == 0
    assert calculate_consecutive_declines(empty) == 0
    assert calculate_severe_drawdown_count(empty) == 0
    assert calculate_years_below_initial(empty, 100) == 0


def test_edge_case_single_value():
    """Test all functions with single value."""
    single = pd.Series([100])
    assert calculate_time_underwater(single) == 0
    assert calculate_recovery_time(single) == 0
    assert calculate_consecutive_declines(single) == 0
    assert calculate_severe_drawdown_count(single) == 0
    assert calculate_years_below_initial(single, 100) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
