import pytest
import pandas as pd
import numpy as np
from core.stats import calculate_ulcer_index


def test_calculate_ulcer_index_empty_series():
    """Test that empty series returns 0."""
    prices = pd.Series([])
    assert calculate_ulcer_index(prices) == 0.0


def test_calculate_ulcer_index_constant_prices():
    """Test that constant prices (no drawdown) returns 0."""
    prices = pd.Series([100, 100, 100, 100])
    result = calculate_ulcer_index(prices)
    assert result == pytest.approx(0.0)


def test_calculate_ulcer_index_single_drawdown():
    """Test Ulcer Index with a single drawdown scenario."""
    # Peak at 100, drop to 90 (10% drawdown), then recover
    prices = pd.Series([100, 90, 95, 100])
    result = calculate_ulcer_index(prices)
    
    # Manual calculation:
    # Drawdowns: 0%, 10%, 5%, 0%
    # Squared: 0, 100, 25, 0
    # Mean: 125/4 = 31.25
    # Sqrt: 5.59
    assert result == pytest.approx(5.59, rel=0.01)


def test_calculate_ulcer_index_continuous_growth():
    """Test that continuous growth (no drawdown) returns 0."""
    prices = pd.Series([100, 110, 120, 130])
    result = calculate_ulcer_index(prices)
    assert result == pytest.approx(0.0)


def test_calculate_ulcer_index_deep_drawdown():
    """Test Ulcer Index with a deep drawdown."""
    # Peak at 100, deep drop to 50 (50% drawdown)
    prices = pd.Series([100, 80, 60, 50])
    result = calculate_ulcer_index(prices)
    
    # Manual calculation:
    # From peaks: [100, 100, 100, 100]
    # Drawdowns as %: 0%, 20%, 40%, 50%
    # Squared: 0, 400, 1600, 2500
    # Mean: 4500/4 = 1125
    # Sqrt: 33.54
    assert result == pytest.approx(33.54, rel=0.01)


def test_calculate_ulcer_index_with_recovery():
    """Test that recovery periods reduce Ulcer Index."""
    # Same drawdown but with recovery
    prices_no_recovery = pd.Series([100, 90, 80, 70])
    prices_with_recovery = pd.Series([100, 90, 95, 98])
    
    ui_no_recovery = calculate_ulcer_index(prices_no_recovery)
    ui_with_recovery = calculate_ulcer_index(prices_with_recovery)
    
    # Recovery should result in lower Ulcer Index
    assert ui_with_recovery < ui_no_recovery


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
