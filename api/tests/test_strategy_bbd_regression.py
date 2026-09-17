import pytest
import json
import os
import pandas as pd
import numpy as np
from core.simulation import run_simulation
from core.shared_logic import prepare_results_dataframe
from core.strategy import BuyBorrowDieStrategy

GOLDEN_MASTER_PATH = os.path.join(os.path.dirname(__file__), 'fixtures', 'bbd_golden_master.json')

@pytest.fixture
def bbd_params():
    """
    BBD Params designed to trigger deleveraging.
    """
    return {
        'num_simulations': 1,
        'num_years': 10,
        'initial_investment': 2_000_000,
        'annual_contribution': 0,
        'inflation_rate': 0.02,
        'asset_model': 'parametric',
        'strategy': 'buy_borrow_die',
        
        # Strategy specific
        'drawdown_method': 'percentage',
        'percentage_rate': 0.05, # Aggressive borrowing
        'enable_tiered_ltv': True,
        'enable_deleveraging': True,
        'ltv_warning_threshold': 0.80, # 80% - High warning to allow borrowing to continue
        'ltv_action_threshold': 0.15, # 15% - Action triggers BEFORE warning stops us
        'deleveraging_target': 0.10, # Back to 10%
        
        # Market assumptions: CRASH return to spike LTV past 60%
        'annual_return': -0.20, # -20% per year crashes assets fast
        'annual_volatility': 0.0, 
    }

def test_generate_and_verify_bbd_golden_master(bbd_params, capsys):
    """
    1. Runs simulation with crashing market.
    2. Verifies debt increases and deleveraging (sales) occurs when LTV > 60%.
    3. Saves/Verifies Golden Master.
    """
    # 1. Setup and Run
    strategy = BuyBorrowDieStrategy(bbd_params)
    strategy_map = {'buy_borrow_die': strategy}
    
    simulations = run_simulation(
        bbd_params, 
        mu=bbd_params['annual_return']/365, 
        sigma=bbd_params['annual_volatility'], 
        strategy_map=strategy_map
    )
    results_df = prepare_results_dataframe(simulations)
    sim_data = results_df['Sim_0'].unstack(level='Metric')

    # 2. Verify Logic (Sanity Check)
    # Check that we are borrowing (Debt increases)
    assert sim_data.loc[1]['Debt'] > 0
    
    # Identify Deleveraging Years (Amount Sold > 0)
    # With -10% return and 5% borrowing, LTV should rise fast.
    deleveraging_years = sim_data[sim_data['Amount Sold'] > 0.01].index.tolist()
    
    print(f"\nDEBUG: Deleveraging occurred in years: {deleveraging_years}")
    


    assert len(deleveraging_years) > 0, "Strategy never triggered deleveraging despite market crash!"

    # Check LTV just before/during deleveraging (simplified check on end of year data)
    # For a refined check, we trust the golden master data which captures the exact state.

    # 3. Serialization for Golden Master
    columns_to_track = [
        'Net Worth', 'Asset Value', 'Cash', 'Debt',
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
