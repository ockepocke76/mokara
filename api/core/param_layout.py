"""
Defines the data-driven layout for the Streamlit sidebar.
This module serves as the single source of truth for the sidebar's structure,
making it easier to manage and reuse for other purposes like reporting.
"""

def get_sidebar_layout():
    """
    Returns a data structure that defines the sidebar layout.

    The structure is a list of dictionaries, where each dictionary represents
    a UI element (e.g., a top-level widget or an expander with widgets).

    Types of elements:
    - 'widget': A single widget to be rendered directly in the sidebar.
    - 'expander': A container with a title and a list of parameter keys to be
                  rendered as widgets inside st.expander.

    This structure dictates the order of elements in the sidebar.
    """
    layout = [
        # --- Strategy Selection ---
        {
            'type': 'widget',
            'key': 'strategy',
            'config_path': 'simulation.strategy'
        },
        {
            'type': 'expander',
            'title': 'Strategy Settings',
            # This is now a placeholder. The content will be dynamically generated
            # based on the selected strategy's class definition.
            'content_type': 'strategy_params'
        },
        # --- Asset Model Selection ---
        {
            'type': 'widget',
            'key': 'asset_model',
            'config_path': 'simulation.asset_model'
        },
        {
            'type': 'expander',
            'title': 'Asset Settings',
            'content_type': 'asset_params'
        },
        # --- General Simulation Settings ---
        {
            'type': 'expander',
            'title': 'Simulation Settings',
            'params': [
                {'key': 'num_years', 'config_path': 'simulation.num_years'}, # Path can be overridden by asset model
                {'key': 'num_simulations', 'config_path': 'simulation.num_simulations'},
                {'key': 'initial_investment', 'config_path': 'simulation.initial_investment'},
            ]
        },
        # --- Rates ---
        {
            'type': 'expander',
            'title': 'Economic Assumptions',
            'params': [
                {'key': 'inflation_rate', 'config_path': 'simulation.inflation_rate'},
                {'key': 'cash_interest_rate', 'config_path': 'simulation.cash_interest_rate'},
            ]
        },
        # --- Tax Settings ---
        {
            'type': 'expander',
            'title': 'Tax Settings',
            'params': [
                {'key': 'tax_method', 'config_path': 'tax.method'},
                {'key': 'isk_tax_rate', 'config_path': 'tax.isk_tax_rate'},
                {'key': 'capital_gains_tax_rate', 'config_path': 'tax.capital_gains_tax_rate'},
            ]
        }
    ]
    return layout