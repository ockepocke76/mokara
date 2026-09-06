
import pytest
import pandas as pd
import numpy as np
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.stats import calculate_survival_rates_by_year

def test_survival_rate_initial_zero():
    """
    Verifies that year 0 survival rate is 100% even if initial investment is 0.
    Strategies like 'Contribution Only' start with 0 net worth but shouldn't be considered 'failed' at start.
    """
    # Setup params
    params = {
        'num_years': 5,
        'initial_investment': 0, # Contribution strategy implies starting with 0
        'num_simulations': 10
    }
    
    years = range(params['num_years'] + 1)
    metrics = ['Net Worth', 'Asset Value']
    iterables = [years, metrics]
    index = pd.MultiIndex.from_product(iterables, names=['Year', 'Metric'])
    
    # Create data where Net Worth starts at 0 (year 0) and grows (year 1+)
    # This simulates a contribution strategy that hasn't failed
    data = []
    for y in years:
        for m in metrics:
            if m == 'Net Worth':
                if y == 0:
                    row = [0.0] * params['num_simulations'] # Year 0: 0 net worth
                else:
                    row = [1000.0] * params['num_simulations'] # Year 1+: Positive net worth
            else:
                row = [0.0] * params['num_simulations']
            data.append(row)
            
    columns = [f'Sim_{i}' for i in range(params['num_simulations'])]
    results_df = pd.DataFrame(data, index=index, columns=columns)
    
    # Calculate survival rates
    survival_rates = calculate_survival_rates_by_year(results_df, params)
    
    # Assert Year 0 is 100%
    assert survival_rates[0] == 100.0, f"Year 0 survival should be 100.0%, got {survival_rates[0]}%"
    
    # Assert subsequent years are 100% (since we set them to positive)
    for y in range(1, params['num_years'] + 1):
        assert survival_rates[y] == 100.0, f"Year {y} survival should be 100.0%, got {survival_rates[y]}%"

def test_survival_rate_standard():
    """
    Verifies standard behavior where initial investment > 0.
    """
    params = {
        'num_years': 2,
        'initial_investment': 10000,
        'num_simulations': 2
    }
    
    years = range(params['num_years'] + 1)
    metrics = ['Net Worth']
    index = pd.MultiIndex.from_product([years, metrics], names=['Year', 'Metric'])
    
    # Sim 0: Always good
    # Sim 1: Fails at year 2
    data = {
        'Sim_0': [10000, 11000, 12000], 
        'Sim_1': [10000, 5000, -100]
    }
    
    # Need to flatten data correctly for DataFrame construction
    # We only have Net Worth rows here, need to expand if function expects more but it just needs Net Worth
    # The function uses .xs('Net Worth', ...) so we construct full multiindex
    
    df_data = []
    for y in years:
        row = [data['Sim_0'][y], data['Sim_1'][y]]
        df_data.append(row)
        
    results_df = pd.DataFrame(df_data, index=index, columns=['Sim_0', 'Sim_1'])
    
    survival_rates = calculate_survival_rates_by_year(results_df, params)
    
    assert survival_rates[0] == 100.0 # Both > 0
    assert survival_rates[1] == 100.0 # Both > 0
    assert survival_rates[2] == 50.0  # One > 0, One < 0
