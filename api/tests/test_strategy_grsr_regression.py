import pytest
import json
import os
import pandas as pd
import numpy as np
from simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy

GOLDEN_MASTER_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'grsr_golden_master.json')

@pytest.fixture
def regression_params():
    """
    Parameters designed to trigger all phases:
    - Start at 5M (50% of target)
    - Target 10M
    - High growth (10%) to hit target quickly
    - 20 year duration to ensure time for all phases
    """
    return {
        'num_simulations': 1,
        'num_years': 20,
        'initial_investment': 5_000_000,
        'annual_contribution': 120_000,
        'inflation_rate': 0.02,
        'asset_model': 'parametric',
        'strategy': 'get_rich_stay_rich',
        
        # Strategy specific
        'target_net_worth': 10_000_000,
        'cash_years_on_stay_rich': 2,
        'withdrawal_rate': 0.04,
        'reserve_replenishment_rate': 0.5,
        
        # Market assumptions (Deterministic for regression)
        'annual_return': 0.10, # 10% return ensures we hit target
        'annual_volatility': 0.0, # Zero valatility for deterministic results
    }

def test_generate_and_verify_golden_master(regression_params, capsys):
    """
    1. Runs simulation.
    2. Verifies phase transitions occurred (Get Rich -> Build Buffer -> Stay Rich).
    3. Saves (if not exists) or Compares against Golden Master data.
    """
    # 1. Setup and Run
    strategy = GetRichStayRichStrategy(regression_params)
    strategy_map = {'get_rich_stay_rich': strategy}
    
    # Use deterministic seed/parameters
    simulations = run_simulation(
        regression_params, 
        mu=regression_params['annual_return']/365, 
        sigma=regression_params['annual_volatility'], 
        strategy_map=strategy_map
    )
    results_df = prepare_results_dataframe(simulations)
    
    # FIX: Unstack the multi-index to get metrics as columns
    # Structure is Index=[Year, Metric], Column=Sim_0
    # After unstack(level='Metric'), Index=Year, Columns=Metric
    sim_data = results_df['Sim_0'].unstack(level='Metric')

    # 2. Verify Transitions (Logic Check)
    # Phase 1: Start (Year 1) should be 100% invested (Cash approx 0 or just contribution)
    assert sim_data.loc[1]['Net Worth'] >= 5_000_000
    
    # Find active phases
    years_with_drawdown = sim_data[sim_data['Consumption Delivered'] > 0].index.tolist()
    years_building_buffer = sim_data[(sim_data['Amount Sold'] > 0) & (sim_data['Consumption Delivered'] == 0)].index.tolist()
    
    print(f"\nDEBUG: Years building buffer: {years_building_buffer}")
    print(f"DEBUG: Years with drawdown (Stay Rich): {years_with_drawdown}")

    # Assert we actually hit the phases
    assert len(years_building_buffer) > 0, "Strategy never entered 'Build Buffer' phase!"
    assert len(years_with_drawdown) > 0, "Strategy never entered 'Stay Rich' phase!"
    
    # 3. Serialization for Golden Master
    # We select key columns to track for regression
    columns_to_track = [
        'Net Worth', 'Asset Value', 'Cash', 
        'Amount Sold', 'Amount Bought', 'Amount Contributed', 
        'Consumption Delivered', 'Cash Interest'
    ]
    
    # Convert dataframe to simple dict for JSON
    current_results = sim_data[columns_to_track].round(2).to_dict(orient='index')
    
    # 4. Generate or Verify
    # If GOLDEN_MASTER_PATH doesn't exist or we force update, write it.
    
    if not os.path.exists(GOLDEN_MASTER_PATH):
        os.makedirs(os.path.dirname(GOLDEN_MASTER_PATH), exist_ok=True)
        with open(GOLDEN_MASTER_PATH, 'w') as f:
            json.dump(current_results, f, indent=2)
        print(f"\n[GENERATE] Golden Master data created at {GOLDEN_MASTER_PATH}")
    else:
        # If it exists, we VERIFY against it
        with open(GOLDEN_MASTER_PATH, 'r') as f:
            golden_data = json.load(f)
        
        # Convert keys back to int for comparison (json keys are strings)
        golden_data = {int(k): v for k,v in golden_data.items()}
        
        print("\n[VERIFY] Comparing against Golden Master...")
        for year, metrics in current_results.items():
            golden_year = golden_data.get(year)
            assert golden_year is not None, f"Year {year} missing in Golden Master"
            
            for metric, value in metrics.items():
                golden_val = golden_year.get(metric)
                # Use small tolerance for floating point diffs
                assert value == pytest.approx(golden_val, abs=0.01), \
                    f"Mismatch Year {year} {metric}: Current {value} != Golden {golden_val}"
        
        print("[SUCCESS] Current strategy matches Golden Master exactly.")
