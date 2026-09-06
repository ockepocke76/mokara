from abc import ABC, abstractmethod
import pandas as pd


class BaseStrategy(ABC):
    """
    Abstract base class for all financial strategies.

    The simulation engine will instantiate a concrete strategy class and call its
    methods annually to determine the actions to be taken for that year. This
    interface separates the core simulation mechanics (like asset growth) from
    the decision-making logic of a specific strategy.
    """
    @property
    @abstractmethod
    def parameters(self) -> dict:
        """
        Returns a dictionary defining the strategy's configurable parameters.
        Each key is a parameter name, and the value is a dict with:
        - description: Help text
        - default: Default value
        - min/max/step: Slider constraints (optional)
        - options: List of choices (optional)
        """
        raise NotImplementedError("Strategy must define its parameters.")

    def __init__(self, params: dict):
        """
        Initializes the strategy with all relevant simulation parameters.

        Args:
            params (dict): A dictionary containing all simulation settings.
        """
        self.params = params
        # Strategies can initialize their own state here if needed.

    def reset(self):
        """
        Resets any internal state of the strategy.
        This is called by the simulation engine before starting a new simulation run.
        """
        # Most strategies are stateless, so the default implementation does nothing.
        # Stateful strategies should override this to reset their state.
        pass

    @property
    def default_tax_method(self) -> str:
        """
        Specifies the default tax method for this strategy.
        Should be one of the keys from `tax.method.options` in config.yml (e.g., 'isk', 'capital_gains').
        """
        # Default to 'isk' for custom strategies or as a general fallback.
        return 'isk'

    @property
    @abstractmethod
    def shortfall_funding_policy(self) -> list[str]:
        """
        Defines the strategy's ordered preference for funding cash shortfalls.

        The simulation engine will follow this policy if the strategy's primary
        plan does not generate enough cash to cover all costs (including taxes
        on sales).

        Returns:
            list[str]: An ordered list of funding methods.
                       Valid options are: 'USE_CASH', 'SELL_ASSETS', 'BORROW'.
        """
        raise NotImplementedError("This method must be implemented by a subclass.")

    @abstractmethod
    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        """
        Decides the initial portfolio allocation at the very start of the simulation.

        This method is called only once, before the main annual simulation loop begins.
        It should return a dictionary of actions to take, such as buying assets with
        the initial cash.

        Args:
            initial_portfolio_state (dict): The starting state, typically containing only cash.
                                            Example: {'cash': 1_000_000, 'asset_value': 0, ...}
            market_data_at_start (pd.DataFrame): Market data for the first day of the simulation,
                                                 to determine the initial asset price.

        Returns:
            dict: A dictionary of financial actions. For initial setup, this is typically
                  {'action': 'BUY_ASSET', 'cash_amount': amount_to_invest}.
        """
        raise NotImplementedError("This method must be implemented by a subclass.")


    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        """
        Calculates the desired consumption amount for the current year based on the strategy's rules.
        This represents the user's spending goal for the year.

        Args:
            year (int): The current simulation year (e.g., 1, 2, ..., 30).
            portfolio_state (dict): The state of the portfolio at the START of the year, post-growth.
                                    Example: {'asset_value': 1.2M, 'debt': 100k, 'cash': 50k, 'cost_basis': 500k}
            portfolio_history (list[dict]): A list of portfolio states from the END of all previous years.

        Returns:
            float: The amount of money desired for consumption this year.
        """
        # Default behavior is to return 0. Subclasses should override this.
        return 0.0
 

    def evaluation_category(self) -> str:
        """
        Returns the evaluation category for leaderboard rankings.
        
        Returns:
            str: 'WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', or 'HYBRID'
        """
        # Default to HYBRID for unknown/complex strategies
        return 'HYBRID'
 
    @abstractmethod
    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        """
        Executes the main logic of the strategy for a single year. This includes
        determining how to fund the desired consumption drawdown for the year.
        The strategy should return a dictionary of actions to generate the `desired_drawdown`.

        Args:
            year (int): The current simulation year.
            portfolio_state (dict): The state of the portfolio at the start of the year.
            portfolio_history (list[dict]): History of portfolio states from previous years.
            desired_drawdown (float): The consumption amount for the year, from `get_annual_drawdown`.
            mandatory_costs (float): The sum of all mandatory costs for the year (e.g., fees, taxes)
                                     that must be funded in addition to the drawdown.

        Returns:
            dict: A dictionary of financial actions for the year. Keys must include:
                  'amount_sold', 'amount_bought', 'debt_increase', and 'debt_repayment'.
        """
        # This is a placeholder and should be overridden.
        # The simulation engine is responsible for handling the cash flow logic
        # based on these actions.
        raise NotImplementedError("This method must be implemented by a subclass.")

class TrinityStrategy(BaseStrategy):
    """
    Implements the Trinity Study withdrawal strategy - the famous "4% rule."

    **The gold standard for retirement planning, backed by decades of research.**

    This strategy withdraws a fixed percentage of your initial portfolio value each year,
    adjusted for inflation. Based on the landmark Trinity Study that analyzed historical
    market data to determine safe withdrawal rates for 30-year retirements.

    **How it works:**
    - Year 1: Withdraw 4% of initial portfolio (e.g., $40,000 from $1M)
    - Year 2+: Increase withdrawal amount each year by inflation rate
    - All withdrawals funded by selling assets
    - No borrowing, no complex rebalancing—just simple, predictable income

    **Best for:** Traditional retirees who want predictable, inflation-adjusted income
    with a time-tested approach. Ideal for those who prefer simplicity over complexity.

    **Tax efficiency:** Moderate - pays capital gains taxes on each asset sale.
    """
    display_name = "Trinity Study (Asset Withdrawal)"
    
    def evaluation_category(self) -> str:
        return 'WITHDRAWAL_ONLY'

    @property
    def parameters(self):
        return {
            'withdrawal_rate': {
                'description': 'Annual withdrawal rate as a percentage of the initial portfolio value.',
                'default': 0.04,
                'min': 0.0,
                'max': 0.1,
                'step': 0.01,
                'slider_format': '%.2f%%'
            }
        }

    @property
    def shortfall_funding_policy(self) -> list[str]:
        """
        Trinity strategy prefers to sell more assets to cover any shortfall
        (e.g., from taxes on the initial sale). It will never borrow.
        """
        # The strategy should sell assets first, then use cash. Borrowing is a last resort
        # to handle edge cases where a mandatory cost (like ISK tax from a previous year's
        # value) is due after the portfolio has been fully depleted.
        return ['SELL_ASSETS', 'USE_CASH', 'BORROW']

    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        """
        Invests the full initial investment amount into the asset at the start.
        """
        initial_investment = self.params.get('initial_investment', 0)
        # Action to buy asset with the specified initial cash amount
        return {'action': 'BUY_ASSET', 'cash_amount': initial_investment}

    @classmethod
    def get_user_prompt_template(cls) -> str:
        """Returns a plain English description for users cloning this template."""
        return """I want a simple retirement withdrawal strategy based on the Trinity Study (the famous "4% rule").

**How it should work:**
- In the first year, withdraw 4% of my starting portfolio value
- Each year after that, increase my withdrawal by the inflation rate to maintain purchasing power
- Get the money I need by selling investments each year
- Keep it simple - no borrowing or complicated rebalancing

**Example:** If I start with $1 million, I'd withdraw $40,000 in year 1. If inflation is 2%, I'd withdraw $40,800 in year 2, $41,616 in year 3, and so on.

**Parameters to include:**
- Withdrawal rate: Let me adjust between 3% and 5% (default 4%)"""


    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        """
        Calculates the inflation-adjusted withdrawal amount for the year.
        """
        initial_investment = self.params.get('initial_investment', 0)
        withdrawal_rate = self.params.get('withdrawal_rate', 0.04)
        inflation_rate = self.params.get('inflation_rate', 0.02)
        
        # The withdrawal amount is based on the initial investment and grows with inflation.
        withdrawal_for_consumption = initial_investment * withdrawal_rate * ((1 + inflation_rate)**(year - 1))
        return withdrawal_for_consumption
 
    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        """
        Executes the Trinity withdrawal for the year by selling assets to fund all cash needs.
        """
        current_asset_value = portfolio_state.get('asset_value', 0)

        # --- REFACTOR: Simple Strategy ---
        # The strategy is no longer "tax-aware". It simply commands a sale to cover the known cash needs.
        # The engine passes the mandatory_costs, so the strategy should plan to sell enough to cover them.
        # The strategy's job is to state its cash needs. The Portfolio is responsible for capping the sale at the available asset value.
        amount_to_sell = desired_drawdown + mandatory_costs
 
        return {
            'amount_sold': amount_to_sell, # The engine will cap this at the actual asset value.
            'amount_bought': 0.0,
            'debt_increase': 0.0,
            'debt_repayment': 0.0,
            'amount_contributed': 0.0
        }

class BuyBorrowDieStrategy(BaseStrategy):
    """
    Implements the "Buy, Borrow, Die" tax-optimized leveraging strategy.

    **Tax-efficient wealth preservation through strategic borrowing.**

    This strategy borrows against your portfolio instead of selling assets, avoiding capital
    gains taxes entirely. Inspired by how ultra-wealthy individuals maintain their lifestyle
    while preserving assets for heirs with a stepped-up cost basis.

    **How it works:**
    - Borrow money using your portfolio as collateral (loan-to-value management)
    - Use loan proceeds for living expenses (tax-free borrowing)
    - Never sell assets, avoiding capital gains taxes
    - Implements tiered LTV risk management with automatic deleveraging
    - Assets grow tax-deferred until death, passing to heirs with no unrealized gains

    **Best for:** High-net-worth individuals comfortable with leverage who prioritize
    tax efficiency and legacy preservation. Requires discipline and market resilience.

    **Tax efficiency:** Excellent - minimal to zero capital gains taxes during lifetime.
    """
    display_name = "Buy, Borrow, Die"
    
    def evaluation_category(self) -> str:
        return 'WITHDRAWAL_ONLY'


    @property
    def parameters(self):

        return {
            'drawdown_method': {
                'description': 'Method for determining annual loan drawdown amount.',
                'default': 'initial_percentage',
                'options': ['fixed', 'percentage', 'initial_percentage'],
                'captions': [
                    "A fixed amount, adjusted annually for inflation.",
                    "A percentage of the current portfolio value each year.",
                    "A percentage of the initial portfolio value, adjusted for inflation (Trinity-style)."
                ],
                'widget': 'radio'
            },
            'fixed_drawdown': {
                'description': 'Fixed annual drawdown amount (adjusted for inflation).',
                'default': 400000, 'min': 0, 'max': 2000000, 'step': 50000, 'slider_format': '%d'
            },
            'initial_percentage_rate': {
                'description': 'Drawdown as a percentage of the initial portfolio value, adjusted for inflation (Trinity-style).',
                'default': 0.04, 'min': 0.0, 'max': 0.1, 'step': 0.01, 'slider_format': '%.2f%%'
            },
            'percentage_rate': {
                'description': 'Drawdown as a percentage of current asset value.',
                'default': 0.04, 'min': 0.0, 'max': 0.1, 'step': 0.01, 'slider_format': '%.2f%%'
            },
            'max_drawdown': {
                'description': 'An optional absolute cap on the annual drawdown amount.',
                'default': 600000, 'min': 0, 'max': 5000000, 'step': 50000, 'slider_format': '%d'
            },
            'enable_tiered_ltv': {
                'description': 'Enable a tiered LTV management system with a warning and action tier.',
                'default': True
            },
            'enable_deleveraging': {
                'description': 'Enable selling assets to reduce debt if LTV exceeds the action threshold.',
                'default': True
            },
            'ltv_action_threshold': {
                'description': 'Action Tier: LTV ratio that triggers a deleveraging event.',
                'default': 0.6, 'min': 0.1, 'max': 0.9, 'step': 0.05, 'slider_format': '%.1f%%'
            },
            'ltv_warning_threshold': {
                'description': 'Warning Tier: LTV ratio that suspends drawdowns.',
                'default': 0.5, 'min': 0.0, 'max': 0.9, 'step': 0.05, 'slider_format': '%.1f%%'
            },
            'deleveraging_target': {
                'description': 'The target LTV to reach after a deleveraging sale (for the Action Tier).',
                'default': 0.5, 'min': 0.1, 'max': 0.9, 'step': 0.05, 'slider_format': '%.1f%%'
            }
        }

    @property
    def shortfall_funding_policy(self) -> list[str]:
        """
        BBD strategy prefers to borrow to cover any shortfall. It will never
        sell assets to cover a simple cash shortfall (it only sells for
        explicit deleveraging events).
        """
        return ['BORROW', 'USE_CASH']

    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        """
        Invests the full initial investment amount into the asset at the start.
        """
        initial_investment = self.params.get('initial_investment', 0)
        # Action to buy asset with the specified initial cash amount
        return {'action': 'BUY_ASSET', 'cash_amount': initial_investment}
    @classmethod
    def get_user_prompt_template(cls) -> str:
        """Returns a plain English description for users cloning this template."""
        return """I want a tax-efficient "Buy, Borrow, Die" strategy that borrows money against my portfolio instead of selling investments.
        **How it should work:**
        - Borrow money using my portfolio as collateral to fund my lifestyle
        - Never sell investments (avoiding capital gains taxes entirely)
        - Let me choose how much to borrow each year:
        * Fixed amount that adjusts for inflation
        * Percentage of my current portfolio value
        * Trinity-style: percentage of starting value, adjusted for inflation
        - Protect me from taking on too much debt with safety limits:
        * Warning level (50%): Stop borrowing if debt reaches 50% of portfolio value
        * Action level (60%): If debt exceeds 60%, automatically sell some investments to pay down debt to 50%
        - Set a maximum annual withdrawal amount as a safety cap
        **Example:** With a $2 million portfolio, I could borrow $80,000/year (4%). If my portfolio drops and debt reaches 60% of its value, automatically sell investments to reduce debt back to a safer 50% level.
        **Parameters to include:**
        - Borrowing method: fixed amount, percentage of current value, or Trinity-style
        - Annual amounts for each method
        - Maximum withdrawal cap
        - Debt safety thresholds (warning and action levels)
        - Option to enable/disable automatic debt reduction"""
    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        """
        Calculates the desired loan amount for consumption, subject to LTV limits.
        """
        current_asset_value = portfolio_state.get('asset_value', 0)
        total_debt = portfolio_state.get('debt', 0)
        
        # --- LTV Warning Tier Check ---
        # Check if the LTV at the start of the year exceeds the warning threshold.
        current_ltv = total_debt / current_asset_value if current_asset_value > 0 else float('inf')
        if self.params.get('enable_tiered_ltv', False) and current_ltv > self.params.get('ltv_warning_threshold', float('inf')):
            return 0.0 # Suspend drawdown if LTV is too high.

        # --- Calculate Drawdown Based on Method ---
        drawdown_method = self.params.get('drawdown_method', 'fixed')
        inflation_rate = self.params.get('inflation_rate', 0.0)
        loan_for_drawdown = 0.0

        if drawdown_method == 'percentage':
            loan_for_drawdown = current_asset_value * self.params.get('percentage_rate', 0.0)
            max_drawdown = self.params.get('max_drawdown')
            if max_drawdown is not None:
                loan_for_drawdown = min(loan_for_drawdown, max_drawdown)
        elif drawdown_method == 'initial_percentage':
            initial_investment = self.params.get('initial_investment', 0)
            initial_rate = self.params.get('initial_percentage_rate', 0.0)
            loan_for_drawdown = initial_investment * initial_rate * ((1 + inflation_rate)**(year - 1))
        elif drawdown_method == 'fixed':
            fixed_amount = self.params.get('fixed_drawdown', 0)
            loan_for_drawdown = fixed_amount * ((1 + inflation_rate)**(year - 1))
            
        return loan_for_drawdown

    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        """
        Executes the borrowing logic for the year to fund all cash needs.
        """
        current_asset_value = portfolio_state['asset_value']
        debt_at_start_of_year = portfolio_state['debt']
        cost_basis = portfolio_state['cost_basis']

        # --- Deleveraging Logic (Action Tier) ---
        amount_sold = 0.0
        debt_repayment = 0.0
        debt_increase_for_consumption = desired_drawdown # The strategy decides to borrow for consumption.

        # Deleveraging should only be considered if there's a consumption drawdown request.
        # If the only cash need is for mandatory costs, the strategy should always borrow for them.
        if self.params.get('enable_deleveraging', False) and current_asset_value > 0 and desired_drawdown > 0:
            # The strategy calculates the LTV *after* borrowing for consumption and mandatory costs.
            total_new_debt_needed = desired_drawdown + mandatory_costs
            ltv_after_borrowing = (debt_at_start_of_year + total_new_debt_needed) / current_asset_value

            if ltv_after_borrowing > self.params.get('ltv_action_threshold', float('inf')):
                # --- REFACTOR: Simple Strategy ---
                # The deleveraging calculation is now "pre-tax". It calculates the sale amount
                # needed to hit the target LTV as if there were no tax on the sale. The engine
                # will handle the actual tax, and the final LTV will be slightly higher than
                # the target, realistically reflecting the "tax drag" of the deleveraging event.
                target_ltv = self.params.get('deleveraging_target', 0.0)
                denominator = 1 - target_ltv
                if denominator > 0:
                    amount_sold = (debt_at_start_of_year + total_new_debt_needed - current_asset_value * target_ltv) / denominator
                    amount_sold = min(amount_sold, current_asset_value)
                    # The strategy still needs to signal its intent to use the sale proceeds for repayment.
                    debt_repayment = amount_sold
 
        # If a deleveraging sale is planned, the strategy should not also plan to borrow for consumption.
        # The sale proceeds are the source of funds. The engine's cash waterfall will handle it.
        # However, the strategy still needs to plan to borrow for mandatory costs, as it has no other cash source.
        debt_increase_for_costs = mandatory_costs
        if amount_sold > 0:
            debt_increase_for_consumption = 0.0
            # If selling, the strategy assumes sale proceeds will cover costs, so it doesn't borrow for them.
            debt_increase_for_costs = 0.0

        return {
            'amount_sold': amount_sold,
            'amount_bought': 0.0,
            'debt_increase': debt_increase_for_consumption + debt_increase_for_costs,
            'debt_repayment': debt_repayment,
            'amount_contributed': 0.0
        }