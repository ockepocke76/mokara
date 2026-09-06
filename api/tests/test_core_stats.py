import pytest
import numpy as np
import pandas as pd
import sys
from pathlib import Path

# Add project root to path to allow absolute imports
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.stats import calculate_historical_mu_sigma

def test_calculate_historical_mu_sigma_simple():
    """Tests the calculation with a simple, gapless price series."""
    prices = pd.Series([100, 101, 102, 101.5])
    log_returns = np.log(prices / prices.shift(1)).dropna()
    expected_mu = log_returns.mean()
    expected_sigma = log_returns.std()

    mu, sigma = calculate_historical_mu_sigma(prices)

    assert mu == pytest.approx(expected_mu)
    assert sigma == pytest.approx(expected_sigma)

def test_calculate_historical_mu_sigma_with_gap():
    """Tests that the calculation is correct with a weekend gap in the index."""
    dates = pd.to_datetime(['2023-01-05', '2023-01-06', '2023-01-09']) # Thursday, Friday, Monday
    prices = pd.Series([100, 101, 103], index=dates)
    
    # The log return from 6th to 9th should be treated as a single period
    log_returns = np.log(prices / prices.shift(1)).dropna()
    expected_mu = log_returns.mean()
    expected_sigma = log_returns.std()

    mu, sigma = calculate_historical_mu_sigma(prices)

    assert mu == pytest.approx(expected_mu)
    assert sigma == pytest.approx(expected_sigma)
    assert len(log_returns) == 2 # Ensure the gap is treated as one step

def test_calculate_historical_mu_sigma_empty():
    """Tests the function with an empty price series."""
    prices = pd.Series([], dtype=float)
    mu, sigma = calculate_historical_mu_sigma(prices)
    assert mu == 0.0
    assert sigma == 0.0

def test_calculate_historical_mu_sigma_single_price():
    """Tests the function with a single price point, which should result in zero mu/sigma."""
    prices = pd.Series([100.0])
    mu, sigma = calculate_historical_mu_sigma(prices)
    assert mu == 0.0
    assert sigma == 0.0
