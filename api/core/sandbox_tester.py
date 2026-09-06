"""
Sandbox testing module for strategy validation.

Provides testing capabilities using the REAL simulation engine to show
realistic results with taxes, cash waterfall, and all actual mechanics.
"""

import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional


def run_sandbox_test(strategy_code: str, class_name: str, test_params: Dict[str, Any],
                     seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Run tests using the REAL simulation engine for realistic results.

    Args:
        strategy_code: Strategy class code to test
        class_name: Name of strategy class
        test_params: Dict with test configuration:
            - initial_investment: Starting capital
            - num_years: Years to simulate
            - num_random_paths: Number of random paths (default: 10)
            - use_sp500_backtest: Whether to include S&P 500 backtest (default: True)
            - inflation_rate: Inflation rate (default: 0.02)
            - strategy_params: Dict of strategy-specific parameters
        seed: Optional RNG seed. run_simulation generates all return scenarios
            upfront from the global numpy RNG, so two calls with the same seed
            see identical market paths — required for paired strategy-vs-baseline
            comparisons where an unpaired 10-path sample is mostly noise.
    
    Returns:
        Dict with:
            - success: Boolean
            - random_paths: List of dicts, each containing yearly_results for one path
            - backtest_path: Dict with yearly_results for S&P 500 backtest (if enabled)
            - summary_stats: Aggregated statistics across all paths
            - error: Error message if failed
    """
    from core.sandbox import execute_strategy_code, SandboxedStrategyWrapper
    from simulation import run_simulation
    from core.data import load_and_prepare_data, prepare_simulation_inputs
    from core.shared_logic import assemble_params
    
    try:
        # Validate and get strategy class first (fast fail)
        strategy_class = execute_strategy_code(strategy_code, class_name)
        
        # Build simulation parameters using the centralized assemble_params
        # This ensures asset details (file_path, etc.) from CONFIG are merged in.
        sim_params = assemble_params(test_params)
        
        # Ensure critical parameter names match what load_and_prepare_data expects
        # and set sensible defaults for the sandbox environment if missing
        sim_params.setdefault('initial_investment', 1000000)
        sim_params.setdefault('num_years', 30)
        sim_params.setdefault('num_simulations', test_params.get('num_random_paths', 10))
        sim_params.setdefault('inflation_rate', 0.02)
        sim_params.setdefault('tax_method', 'isk')
        sim_params.setdefault('asset_model', 'parametric') 
        sim_params.setdefault('debt_enabled', True)
        sim_params.setdefault('debt_interest_rate', 0.05)
        
        # Add strategy-specific parameters to the top level (if not already handled by assemble_params)
        strategy_params = test_params.get('strategy_params', {})
        sim_params.update(strategy_params)
        
        logging.info(f"Checking Sandbox sim_params for local_file_path: {'local_file_path' in sim_params} (Model: {sim_params.get('asset_model')})")
        if 'local_file_path' not in sim_params and 'bootstrap' in sim_params.get('asset_model', ''):
            logging.error(f"FATAL: local_file_path MISSING for bootstrap model {sim_params.get('asset_model')}")
        
        # --- STEP 1: Load REAL data using the same pipeline as the main app ---
        # This leverages the caching in core.data, so it is fast after the first load.
        # It ensures we use the EXACT same data (S&P 500, Bitcoin, etc.) as the main sim.
        data = load_and_prepare_data(sim_params)
        
        if not data:
            return {
                "success": False, 
                "error": f"Failed to load market data for model: {sim_params['asset_model']}. Please check your asset configuration."
            }
            
        # --- STEP 2: Prepare simulation inputs (mu, sigma, return sources) ---
        # Uses the shared logic extracted to core.data to ensure parity with background_tasks.py
        sim_inputs = prepare_simulation_inputs(data, sim_params['asset_model'])
        
        # --- STEP 3: Instantiate and Wrap Strategy ---
        # 1. Instantiate user strategy with the full params
        user_strategy_instance = strategy_class(sim_params)
        # 2. Wrap it for safety and metric tracking
        instantiated_strategy = SandboxedStrategyWrapper(user_strategy_instance)
        
        # --- STEP 4: Run the REAL simulation engine ---
        # We pass the real inputs (returns_sources, mu, sigma) just like the main process.
        if seed is not None:
            np.random.seed(seed)
        all_results = run_simulation(
            params=sim_params,
            returns_sources=sim_inputs['returns_sources'],
            mu=sim_inputs['mu'],
            sigma=sim_inputs['sigma'],
            strategy_map={'custom': instantiated_strategy}
        )
        
        # Extract and format results
        random_paths = []
        backtest_path = None
        
        for sim_result in all_results:
            path_data = {
                'yearly_results': sim_result.yearly_results,
                'path_label': 'S&P 500 Backtest' if sim_result.metadata.get('type') == 'backtest' else f"Random Path {len(random_paths) + 1}"
            }
            
            if sim_result.metadata.get('type') == 'backtest':
                backtest_path = path_data
            else:
                random_paths.append(path_data)
        
        # Calculate summary statistics - pass strategy instance for category detection
        summary_stats = _calculate_summary_stats(random_paths, backtest_path, user_strategy_instance)
        
        return {
            'success': True,
            'random_paths': random_paths,
            'backtest_path': backtest_path,
            'summary_stats': summary_stats,
            'asset_name': sim_params.get('asset_name', 'Asset'),
            'error': None
        }
        
    except Exception as e:
        logging.error(f"Sandbox test failed: {e}", exc_info=True)
        return {
            'success': False,
            'random_paths': [],
            'backtest_path': None,
            'summary_stats': {},
            'error': str(e)
        }


def _calculate_summary_stats(random_paths: List[Dict], backtest_path: Optional[Dict], strategy_instance) -> Dict[str, Any]:
    """Calculate aggregate statistics across all paths with enhanced metrics."""
    all_final_net_worths = []
    all_total_consumption = []
    all_max_debt = []
    
    for path in random_paths:
        yearly = path['yearly_results']
        if yearly:
            # Use Title Case field names from Portfolio.record_yearly_snapshot
            all_final_net_worths.append(yearly[-1]['Net Worth'])
            all_total_consumption.append(sum(y['Consumption Delivered'] for y in yearly))
            all_max_debt.append(max(y['Debt'] for y in yearly))
    
    if not all_final_net_worths:
        return {}
    
    # Calculate success rate (net worth > 0 at end)
    success_count = sum(1 for nw in all_final_net_worths if nw > 0)
    success_rate = success_count / len(all_final_net_worths) if all_final_net_worths else 0
    
    # --- Range Metrics (Best/Worst from random paths) ---
    best_final_nw = max(all_final_net_worths)
    worst_final_nw = min(all_final_net_worths)
    
    # --- Backtest Analytics ---
    backtest_analytics = {}
    if backtest_path and backtest_path['yearly_results']:
        yearly = backtest_path['yearly_results']
        
        # Final backtest outcome
        backtest_final_nw = yearly[-1]['Net Worth']
        
        # Calculate max drawdown for backtest
        peak = yearly[0]['Net Worth']
        max_drawdown = 0
        for year_data in yearly:
            nw = year_data['Net Worth']
            if nw > peak:
                peak = nw
            drawdown = (peak - nw) / peak if peak > 0 else 0
            max_drawdown = max(max_drawdown, drawdown)
        
        # Extract totals from yearly_results (already calculated by simulation)
        total_withdrawn = sum(y['Consumption Delivered'] for y in yearly)
        total_contributed = sum(y['Amount Contributed'] for y in yearly)
        total_taxes = sum(y['Tax Paid'] for y in yearly)
        total_fees = sum(y['Fees Paid'] for y in yearly)
        
        # Get strategy category from the strategy itself (proper architecture!)
        try:
            strategy_category = strategy_instance.evaluation_category()
        except Exception:
            # Fallback if strategy doesn't implement the method
            strategy_category = 'UNKNOWN'
        
        backtest_analytics = {
            'backtest_final_nw': backtest_final_nw,
            'backtest_max_drawdown': max_drawdown,
            'backtest_total_withdrawn': total_withdrawn,
            'backtest_total_contributed': total_contributed,
            'backtest_total_taxes': total_taxes,
            'backtest_total_fees': total_fees,
            'strategy_category': strategy_category
        }
    
    return {
        'avg_final_net_worth': np.mean(all_final_net_worths),
        'median_final_net_worth': np.median(all_final_net_worths),
        'std_final_net_worths': np.std(all_final_net_worths),
        'success_rate': success_rate,
        'avg_total_consumption': np.mean(all_total_consumption),
        'max_debt_across_paths': max(all_max_debt) if all_max_debt else 0,
        'num_paths_tested': len(random_paths) + (1 if backtest_path else 0),
        # Range metrics
        'best_final_nw': best_final_nw,
        'worst_final_nw': worst_final_nw,
        # Backtest analytics
        **backtest_analytics
    }



def plot_test_results(test_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate Plotly charts showing test results.
    
    Returns dict of Plotly figure objects for:
    - net_worth: Net worth trajectories over time
    - asset_value: Asset values over time
    - debt: Debt levels over time
    - consumption: Annual consumption/contributions
    """
    import plotly.graph_objects as go
    
    figures = {}
    
    # Prepare data
    all_paths = test_results.get('random_paths', [])
    backtest = test_results.get('backtest_path')
    asset_name = test_results.get('asset_name', 'Asset')
    backtest_label = f"{asset_name} Backtest"
    
    if not all_paths and not backtest:
        return figures
    
    # Net Worth Over Time
    fig_net_worth = go.Figure()
    
    # Add random paths (thin lines) - show legend for first one
    for idx, path in enumerate(all_paths):
        yearly = path['yearly_results']
        years = [y['Year'] for y in yearly]
        net_worths = [y['Net Worth'] for y in yearly]  # Raw values
        
        fig_net_worth.add_trace(go.Scatter(
            x=years,
            y=net_worths,
            mode='lines',
            line=dict(width=1, color='rgba(100, 150, 200, 0.3)'),
            name='Random Paths' if idx == 0 else path['path_label'],
            showlegend=(idx == 0),  # Show legend only for first random path
            legendgroup='random'
        ))
    
    # Add backtest (thick line)
    if backtest:
        yearly = backtest['yearly_results']
        years = [y['Year'] for y in yearly]
        net_worths = [y['Net Worth'] for y in yearly]  # Raw values
        
        fig_net_worth.add_trace(go.Scatter(
            x=years,
            y=net_worths,
            mode='lines',
            line=dict(width=3, color='rgb(255, 127, 14)'),
            name=backtest_label
        ))
    
    fig_net_worth.update_layout(
        title="Net Worth Over Time",
        xaxis_title="Year",
        yaxis_title="Net Worth",
        yaxis=dict(tickformat=".3s"),
        hovermode='x unified',
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    figures['net_worth'] = fig_net_worth
    
    # Asset Value Over Time
    fig_assets = go.Figure()
    for idx, path in enumerate(all_paths):
        yearly = path['yearly_results']
        years = [y['Year'] for y in yearly]
        assets = [y['Asset Value'] for y in yearly]  # Raw values
        fig_assets.add_trace(go.Scatter(
            x=years, y=assets,
            mode='lines',
            line=dict(width=1, color='rgba(50, 200, 100, 0.3)'),
            name='Random Paths' if idx == 0 else '',
            showlegend=(idx == 0),
            legendgroup='random'
        ))
    
    if backtest:
        yearly = backtest['yearly_results']
        years = [y['Year'] for y in yearly]
        assets = [y['Asset Value'] for y in yearly]  # Raw values
        fig_assets.add_trace(go.Scatter(
            x=years, y=assets,
            mode='lines',
            line=dict(width=3, color='rgb(44, 160, 44)'),
            name=backtest_label
        ))
    
    fig_assets.update_layout(
        title="Asset Value Over Time",
        xaxis_title="Year",
        yaxis_title="Asset Value",
        yaxis=dict(tickformat=".3s"),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    figures['asset_value'] = fig_assets
    
    # Debt Over Time
    fig_debt = go.Figure()
    for idx, path in enumerate(all_paths):
        yearly = path['yearly_results']
        years = [y['Year'] for y in yearly]
        debts = [y['Debt'] for y in yearly]  # Raw values
        fig_debt.add_trace(go.Scatter(
            x=years, y=debts,
            mode='lines',
            line=dict(width=1, color='rgba(200, 50, 50, 0.3)'),
            name='Random Paths' if idx == 0 else '',
            showlegend=(idx == 0),
            legendgroup='random'
        ))
    
    if backtest:
        yearly = backtest['yearly_results']
        years = [y['Year'] for y in yearly]
        debts = [y['Debt'] for y in yearly]  # Raw values
        fig_debt.add_trace(go.Scatter(
            x=years, y=debts,
            mode='lines',
            line=dict(width=3, color='rgb(214, 39, 40)'),
            name=backtest_label
        ))
    
    fig_debt.update_layout(
        title="Debt Over Time",
        xaxis_title="Year",
        yaxis_title="Debt",
        yaxis=dict(tickformat=".3s"),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01)
    )
    figures['debt'] = fig_debt
    
    # Consumption Over Time (using backtest as example)
    if backtest:
        yearly = backtest['yearly_results']
        years = [y['Year'] for y in yearly]
        consumption = [y['Consumption Delivered'] for y in yearly]  # Raw values
        
        fig_consumption = go.Figure()
        fig_consumption.add_trace(go.Bar(
            x=years,
            y=consumption,
            name='Annual Consumption',
            marker_color='rgb(158, 202, 225)'
        ))
        
        fig_consumption.update_layout(
            title=f"Annual Consumption ({backtest_label})",
            xaxis_title="Year",
            yaxis_title="Consumption",
            yaxis=dict(tickformat=".3s")
        )
        figures['consumption'] = fig_consumption
    
    return figures
