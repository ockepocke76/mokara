from core.strategy import BaseStrategy
import pandas as pd

class Test3(BaseStrategy):
    """
    A strategy implementing a Growth phase (100% invested with contributions) 
    followed by a Preservation phase (fixed, inflation-adjusted withdrawal 
    based on anchor value and dynamic cash buffer management).
    """
    
    parameters = {
        'initial_cash_injection': {
            'label': 'Initial Cash Injection', 
            'default': 50000.0, 
            'description': 'Lump sum cash contributed at the very start of Year 1, in addition to the initial simulation investment. (Pre-tax, pre-cost).'
        },
        'monthly_contribution_base': {
            'label': 'Base Monthly Contribution', 
            'default': 1000.0, 
            'description': 'The baseline monthly contribution amount (Year 1 basis), adjusted annually for inflation. (Pre-tax, pre-cost).'
        },
        'rich_target_value': {
            'label': 'Wealth Threshold', 
            'default': 10000000.0, 
            'description': 'The asset value (pre-tax) required to switch from Growth to Preservation phase.'
        },
        'withdrawal_rate': {
            'label': 'Preservation Withdrawal Rate', 
            'default': 0.04, 
            'description': 'Percentage of the initial Preservation Phase anchor asset value to withdraw annually. (Pre-tax).'
        },
        'cash_buffer_years': {
            'label': 'Cash Buffer Target (Years)', 
            'default': 2.0, 
            'description': 'Target cash buffer maintained during the Preservation Phase, calculated as N years of the current annual withdrawal amount.'
        }
    }

    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        """
        Invests all initial cash (seed capital + initial injection) 100% into assets.
        """
        
        initial_cash_injection = self.params.get('initial_cash_injection', 50000.0)
        cash_from_seed = initial_portfolio_state.get('cash', 0.0)
        total_cash_to_invest = cash_from_seed + initial_cash_injection
        
        # We contribute the initial injection immediately and invest all resulting cash
        return {
            'amount_contributed': initial_cash_injection, 
            'action': 'BUY_ASSET', 
            'cash_amount': total_cash_to_invest
        }

    @property
    def shortfall_funding_policy(self) -> list[str]:
        # Prioritize selling assets to cover tax shortfalls over borrowing
        return ['SELL_ASSETS', 'USE_CASH']

    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        
        target = self.params.get('rich_target_value')
        withdrawal_rate = self.params.get('withdrawal_rate')
        inflation_rate = self.params.get('inflation_rate')
        
        anchor_year = None
        anchor_value = None
        
        # Check history to determine if the transition occurred
        # History contains states from Year 0 up to Year (year - 1)
        for entry in portfolio_history:
            if entry['asset_value'] >= target:
                anchor_year = entry['year']
                anchor_value = entry['asset_value']
                break
                
        if anchor_year is None:
            # Growth Phase: No withdrawal
            return 0.0
        
        # Preservation Phase: Calculate Inflation Adjusted Drawdown
        
        # The inflation multiplier is applied from the anchor year up to the current year
        years_since_anchor = float(year) - float(anchor_year)
        
        # Defensive check for edge cases, though years_since_anchor should be >= 0
        if years_since_anchor < 0.0:
            years_since_anchor = 0.0
            
        inflation_multiplier = (1.0 + inflation_rate)**years_since_anchor
        
        base_drawdown = anchor_value * withdrawal_rate
        desired_drawdown = base_drawdown * inflation_multiplier
        
        return desired_drawdown

    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        
        inflation_rate = self.params.get('inflation_rate')
        monthly_contribution_base = self.params.get('monthly_contribution_base')
        cash_buffer_years = self.params.get('cash_buffer_years')
        target = self.params.get('rich_target_value')
        
        annual_contribution_base = monthly_contribution_base * 12.0
        
        # --- 1. Determine Phase ---
        anchor_year = None
        for entry in portfolio_history:
            if entry['asset_value'] >= target:
                anchor_year = entry['year']
                break

        # --- 2. Action Planning ---
        
        amount_contributed = 0.0
        amount_sold = 0.0
        amount_bought = 0.0
        
        C_start = portfolio_state.get('cash', 0.0)
        
        if anchor_year is None:
            # Growth Phase: Contribute and invest 100%
            
            # Years elapsed = year - 1 (Year 1 means 0 years of inflation adjustment applied)
            years_elapsed = float(year) - 1.0
            
            if years_elapsed < 0.0:
                 years_elapsed = 0.0
                 
            inflation_multiplier = (1.0 + inflation_rate)**years_elapsed
            amount_contributed = annual_contribution_base * inflation_multiplier
            
            # Invest all current cash plus the new contribution
            amount_bought = C_start + amount_contributed
            
        else:
            # Preservation Phase: Manage Cash Buffer and Fund Drawdown
            
            # Contributions cease (amount_contributed remains 0.0)
            
            D_total = desired_drawdown + mandatory_costs
            
            # Target Cash Buffer (CBT) must be maintained at end of year
            CBT = cash_buffer_years * desired_drawdown
            
            # Calculate Net Trade required to reach CBT after covering D_total
            # Net_Trade = CBT - C_start + D_total
            # If Net_Trade > 0: Sell assets (positive sales increases cash)
            # If Net_Trade < 0: Buy assets (negative sales / purchases decreases cash)
            
            net_trade = CBT - C_start + D_total
            
            if net_trade > 0.0:
                amount_sold = net_trade
            else:
                amount_bought = -net_trade
                
        return {
            'amount_contributed': amount_contributed,
            'amount_sold': amount_sold,
            'amount_bought': amount_bought,
            'debt_increase': 0.0,
            'debt_repayment': 0.0
        }