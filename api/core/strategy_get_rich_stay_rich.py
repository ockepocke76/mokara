from core.strategy import BaseStrategy
import pandas as pd

class GetRichStayRichStrategy(BaseStrategy):
    """
    Implements the "Get Rich, Stay Rich" hybrid strategy with three distinct phases.

    **Dynamic wealth accumulation with automatic risk reduction.**

    This strategy adjusts between aggressive growth and conservative preservation based on your
    net worth relative to a target. Designed for those who want to grow wealth aggressively when
    below target, then automatically shift to capital preservation once the goal is reached.

    **How it works:**
    - **Phase 1 (Get Rich):** 100% stock allocation with regular contributions until hitting target net worth
    - **Phase 2 (Build Buffer):** Sell excess growth to build a cash reserve (2+ years of withdrawals)
    - **Phase 3 (Stay Rich):** Maintain cash buffer, withdraw inflation-adjusted income, preserve capital

    **Best for:** Younger professionals building wealth who want automatic risk reduction upon reaching
    their financial independence number. Ideal for those targeting a specific "lifestyle portfolio" size.

    **Tax efficiency:** Moderate - rebalancing and buffer management trigger capital gains taxes.
    """
    display_name = "Get Rich, Stay Rich"
    
    def evaluation_category(self) -> str:
        return 'HYBRID'


    def __init__(self, params: dict):
        super().__init__(params)
        self.stay_rich_phase_activated = False
        self.build_buffer_phase_activated = False  # NEW: Intermediate phase to build cash buffer
        self.inflation_adjusted_target_net_worth = self.params.get('target_net_worth', 10000000)
        self.net_worth_at_switch = None
        self.year_of_switch = -1

    def reset(self):
        """
        Resets the internal state of the strategy.
        """
        self.stay_rich_phase_activated = False
        self.build_buffer_phase_activated = False  # NEW
        self.inflation_adjusted_target_net_worth = self.params.get('target_net_worth', 10000000)
        self.net_worth_at_switch = None
        self.year_of_switch = -1

    @property
    def parameters(self):
        return {
            'target_net_worth': {
                'description': 'Base target net worth to switch to Stay Rich phase (will be adjusted for inflation annually).',
                'default': 10000000,
                'min': 1000000,
                'max': 100000000,
                'step': 1000000,
                'slider_format': '%d'
            },
            'cash_years_on_stay_rich': {
                'description': 'Years of withdrawal to hold in cash in Stay Rich phase.',
                'default': 2,
                'min': 0,
                'max': 10,
                'step': 1,
                'slider_format': '%d'
            },
            'withdrawal_rate': {
                'description': 'Annual withdrawal rate in Stay Rich phase.',
                'default': 0.04,
                'min': 0.0,
                'max': 0.1,
                'step': 0.01,
                'slider_format': '%.2f%%'
            },
            'reserve_replenishment_rate': {
                'description': 'Percentage of excess gains used to rebuild cash reserve in good years.',
                'default': 0.50,
                'min': 0.0,
                'max': 1.0,
                'step': 0.05,
                'slider_format': '%.0f%%'
            },
            'annual_contribution': {
                'description': 'Annual contribution to the portfolio in Get Rich phase.',
                'default': 120_000,
                'min': 0,
                'max': 1_000_000,
                'step': 10_000,
                'slider_format': '%d'
            }
        }

    @property
    def shortfall_funding_policy(self) -> list[str]:
        return ['SELL_ASSETS', 'USE_CASH']

    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        """
        Invests the full initial investment amount into the asset at the start.
        """
        initial_investment = self.params.get('initial_investment', 0)
        return {'action': 'BUY_ASSET', 'cash_amount': initial_investment}

    @classmethod
    def get_user_prompt_template(cls) -> str:
        """Returns a plain English description for users cloning this template."""
        return """I want a "Get Rich, Stay Rich" strategy that automatically switches from aggressive growth to conservative preservation when I hit my wealth target.
**How it should work in three phases:**
**Phase 1 - Get Rich (Building Wealth):**
- I'm still working and adding money to my portfolio each year
- Invest everything in stocks for maximum growth
- No withdrawals during this phase - focus on accumulation
- Continue until my net worth reaches my target (e.g., $10 million)
**Phase 2 - Build Safety Buffer (Transition):**
- Once I hit my target, sell some investments to build a cash reserve
- Cash reserve should equal 2 years worth of planned withdrawals
- This gives me a cushion for market downturns
**Phase 3 - Stay Rich (Preservation):**
- Start withdrawing 4% per year (adjusted for inflation)
- Pull money from my cash reserve for living expenses
- Refill the cash reserve by selling investments when markets are up
- If markets are doing well, use 50% of gains to rebuild my cash buffer
**Example:** I contribute $120,000/year until I reach $10M. Then I build a $800k cash reserve (2 years ×$400k withdrawal). Finally, I take $400k/year for expenses, keeping that 2-year buffer topped up.
**Parameters to include:**
- Target net worth to trigger the switch (default $10 million)
- Annual contribution amount during growth phase (default $120,000)
- Withdrawal rate during preservation phase (default 4%)
- Years of cash to hold in reserve (default 2 years)
- How aggressively to rebuild cash buffer in good years (default 50% of gains)"""

    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        """
        Calculates the desired consumption amount for the current year based on the strategy's rules.
        Only returns drawdown if in Stay Rich phase (Phase 3).
        """
        # Only return drawdown if in Stay Rich phase
        if not self.stay_rich_phase_activated:
            return 0.0
        
        inflation_rate = self.params.get('inflation_rate', 0.02)
        withdrawal_rate = self.params.get('withdrawal_rate', 0.04)
        
        years_in_stay_rich = year - self.year_of_switch
        
        return self.net_worth_at_switch * withdrawal_rate * ((1 + inflation_rate)**(years_in_stay_rich))

    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        """
        Executes the main logic of the strategy for a single year.
        Three phases: Get Rich → Build Buffer → Stay Rich
        """
        inflation_rate = self.params.get('inflation_rate', 0.02)
        current_net_worth = portfolio_state.get('net_worth', 0.0)
        current_asset_value = portfolio_state.get('asset_value', 0.0)
        current_cash = portfolio_state.get('cash', 0.0)
        base_target = self.params.get('target_net_worth', 10000000)
        inflation_exponent = max(0, year - 2)
        current_year_target = base_target * ((1 + inflation_rate)**inflation_exponent)
        
        withdrawal_rate = self.params.get('withdrawal_rate', 0.04)
        cash_years = self.params.get('cash_years_on_stay_rich', 2)
        target_spending = current_year_target * withdrawal_rate
        target_cash_buffer = target_spending * cash_years

        # --- Phase Transition Checks ---
        # Phase 1 → Phase 2: Asset value reaches target
        if not self.build_buffer_phase_activated and current_asset_value >= current_year_target:
            self.build_buffer_phase_activated = True
        
        # Phase 2 → Phase 3: Cash buffer is built
        if self.build_buffer_phase_activated and not self.stay_rich_phase_activated:
            if current_cash >= target_cash_buffer:
                self.stay_rich_phase_activated = True
                self.net_worth_at_switch = current_net_worth
                self.year_of_switch = year

        # --- Phase 3: Stay Rich ---
        if self.stay_rich_phase_activated:
            # Dynamic cash buffer based on market performance
            replenishment_rate = self.params.get('reserve_replenishment_rate', 0.50)
            cash_at_start_of_year = portfolio_state.get('cash', 0.0)
            
            # Get asset growth from portfolio state
            asset_growth_amount = portfolio_state.get('asset_growth_amount', 0.0)
            total_cash_needed = desired_drawdown + mandatory_costs
            
            # Determine if this is a good year or bad year
            if asset_growth_amount >= total_cash_needed:
                # --- GOOD YEAR: Rebuild cash reserve ---
                excess = asset_growth_amount - total_cash_needed
                target_buffer = desired_drawdown * cash_years
                buffer_deficit = max(0, target_buffer - cash_at_start_of_year)
                
                # Determine replenishment rate
                # If buffer is critically low (< 50% of target), use 100% of excess to rebuild
                if cash_at_start_of_year < target_buffer * 0.5:
                    effective_rate = 1.0
                else:
                    effective_rate = replenishment_rate
                
                # Use a portion of excess to rebuild buffer
                amount_to_add_to_buffer = min(excess * effective_rate, buffer_deficit)
                
                # Sell enough to fund drawdown/costs AND add to buffer
                # The cash from the sale will be: total_cash_needed (spent) + amount_to_add_to_buffer (held)
                net_trade_amount = total_cash_needed + amount_to_add_to_buffer
            else:
                # --- BAD YEAR: Use cash reserve ---
                available_buffer = cash_at_start_of_year
                
                # Use cash to reduce asset sales
                cash_to_use = min(total_cash_needed, available_buffer)
                # Sell less because we're using existing cash
                net_trade_amount = total_cash_needed - cash_to_use
            
            amount_to_sell = max(0, net_trade_amount)
            amount_to_buy = max(0, -net_trade_amount)

            return {
                'amount_sold': amount_to_sell,
                'amount_bought': amount_to_buy,
                'debt_increase': 0.0,
                'debt_repayment': 0.0,
                'amount_contributed': 0.0
            }

        # --- Phase 2: Build Buffer ---
        if self.build_buffer_phase_activated:
            # Sell growth to build cash buffer, but ONLY if we are above target asset value
            contribution_amount = self.params.get('annual_contribution', 0)
            inflation_adjusted_contribution = contribution_amount * ((1 + inflation_rate)**(year - 1))
            cash_at_start_of_year = portfolio_state.get('cash', 0.0)
            
            asset_growth_amount = portfolio_state.get('asset_growth_amount', 0.0)
            
            # Calculate excess assets above target
            excess_assets = max(0, current_asset_value - current_year_target)
            
            # Only sell growth that is also excess above target
            # This ensures we don't sell recovery growth if we dropped below target
            amount_to_sell = max(0, min(asset_growth_amount, excess_assets))
            
            return {
                'amount_sold': amount_to_sell,
                'amount_bought': cash_at_start_of_year + inflation_adjusted_contribution,
                'debt_increase': 0.0,
                'debt_repayment': 0.0,
                'amount_contributed': inflation_adjusted_contribution
            }

        # --- Phase 1: Get Rich ---
        contribution_amount = self.params.get('annual_contribution', 0)
        inflation_adjusted_contribution = contribution_amount * ((1 + inflation_rate)**(year - 1))
        cash_at_start_of_year = portfolio_state.get('cash', 0.0)
        
        return {
            'amount_sold': 0.0,
            'amount_bought': cash_at_start_of_year + inflation_adjusted_contribution,
            'debt_increase': 0.0,
            'debt_repayment': 0.0,
            'amount_contributed': inflation_adjusted_contribution
        }
