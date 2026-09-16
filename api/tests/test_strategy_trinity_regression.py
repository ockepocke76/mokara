import pytest
import json
import os
import pandas as pd
import numpy as np
from core.simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy import TrinityStrategy

GOLDEN_MASTER_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'trinity_golden_master.json')

@pytest.fixture
def trinity_params():
    """
    Standard Trinity parameters.
    """
    return {
        'num_simulations': 1,
        'num_years': 30,
        'initial_investment': 1_000_000,
        'annual_contribution': 0,
        'inflation_rate': 0.03, # 3% inflation
        'asset_model': 'parametric',
        'strategy': 'trinity',
        
        # Strategy specific
        'withdrawal_rate': 0.04,
        
        # Market assumptions (Deterministic)
        'annual_return': 0.07, 
        'annual_volatility': 0.15, # Volatility allows for sequence of return risks checking
    }

def test_generate_and_verify_trinity_golden_master(trinity_params, capsys):
    """
    1. Runs simulation.
    2. Verifies basic 4% rule logic (withdrawals match inflation schedule).
    3. Saves (if not exists) or Compares against Golden Master data.
    """
    # 1. Setup and Run
    strategy = TrinityStrategy(trinity_params)
    strategy_map = {'trinity': strategy}
    
    # Use deterministic seed for volatility
    np.random.seed(42)
    
    simulations = run_simulation(
        trinity_params, 
        mu=trinity_params['annual_return']/365, 
        sigma=trinity_params['annual_volatility'], 
        strategy_map=strategy_map
    )
    results_df = prepare_results_dataframe(simulations)
    
    # Unstack to get metrics as columns
    sim_data = results_df['Sim_0'].unstack(level='Metric')

    # 2. Verify Logic (Sanity Check)
    # Check Year 1 withdrawal is exactly 4% of initial
    expected_y1_withdrawal = trinity_params['initial_investment'] * trinity_params['withdrawal_rate']
    assert sim_data.loc[1]['Consumption Delivered'] == pytest.approx(expected_y1_withdrawal, abs=1.0)

    # Check Year 10 withdrawal is adjusted for inflation (approx)
    # We check 'approx' because simulation timing (start vs end of year) might have slight variance
    inflation_factor = (1 + trinity_params['inflation_rate'])**(10-1)
    expected_y10_withdrawal = expected_y1_withdrawal * inflation_factor
    assert sim_data.loc[10]['Consumption Delivered'] == pytest.approx(expected_y10_withdrawal, rel=0.001)

    print(f"\nDEBUG: Year 1 Withdrawal: {sim_data.loc[1]['Consumption Delivered']}")
    print(f"DEBUG: Year 10 Withdrawal: {sim_data.loc[10]['Consumption Delivered']} (Expected: {expected_y10_withdrawal})")
    
    # 3. Serialization for Golden Master
    columns_to_track = [
        'Net Worth', 'Asset Value', 'Cash', 
        'Amount Sold', 'Consumption Delivered'
    ]
    
    current_results = sim_data[columns_to_track].round(2).to_dict(orient='index')
    
    # 4. Generate or Verify
    if not os.path.exists(GOLDEN_MASTER_PATH):
        os.makedirs(os.path.dirname(GOLDEN_MASTER_PATH), exist_ok=True)
        with open(GOLDEN_MASTER_PATH, 'w') as f:
            json.dump(current_results, f, indent=2)
        print(f"\n[GENERATE] Golden Master data created at {GOLDEN_MASTER_PATH}")
    else:
        with open(GOLDEN_MASTER_PATH, 'r') as f:
            golden_data = json.load(f)
        golden_data = {int(k): v for k,v in golden_data.items()}
        
        print("\n[VERIFY] Comparing against Golden Master...")
        for year, metrics in current_results.items():
            golden_year = golden_data.get(year)
            assert golden_year is not None, f"Year {year} missing in Golden Master"
            for metric, value in metrics.items():
                golden_val = golden_year.get(metric)
                assert value == pytest.approx(golden_val, abs=0.01), \
                    f"Mismatch Year {year} {metric}: Current {value} != Golden {golden_val}"
        
        print("[SUCCESS] Current strategy matches Golden Master exactly.")
