import numpy as np
import logging

class Portfolio:
    """
    Manages the financial state of a single simulation run, including assets,
    debt, cash, and all transactions. Acts as the "accountant" for the simulation.
    """
    def __init__(self, params: dict):
        """
        Initializes the portfolio with the starting financial state from the parameters.
        """
        self.params = params
        self.asset_value = params.get('initial_assets', 0.0)
        self.cash = params.get('initial_investment', 0.0)
        self.debt = params.get('initial_debt', 0.0)
        self.cost_basis = 0.0  # Cost basis is established by initial purchases
        
        # Track previous asset value for growth calculation
        self.prev_asset_value = None

        # Accumulators for reporting
        self.accumulated_interest = 0.0
        self.accumulated_tax = 0.0
        self.accumulated_fees = 0.0

        # History for strategy decisions and final results
        self.history = []

    def get_state(self) -> dict:
        """
        Returns a dictionary representing the current state of the portfolio.
        This is passed to the strategy for decision-making.
        """
        # Calculate asset growth metrics
        if self.prev_asset_value is not None and self.prev_asset_value > 0:
            asset_growth_amount = self.asset_value - self.prev_asset_value
            asset_growth_rate = asset_growth_amount / self.prev_asset_value
        else:
            # First year or no previous value: no growth to report
            asset_growth_amount = 0.0
            asset_growth_rate = 0.0
        
        return {
            'asset_value': self.asset_value,
            'cash': self.cash,
            'debt': self.debt,
            'cost_basis': self.cost_basis,
            'net_worth': self.asset_value + self.cash - self.debt,
            'asset_growth_amount': asset_growth_amount,
            'asset_growth_rate': asset_growth_rate,
        }

    def apply_initial_strategy(self, initial_actions: dict):
        """
        Applies the initial asset allocation decided by the strategy at Year 0.
        """
        amount_to_buy = initial_actions.get('cash_amount', 0)
        debt_to_take = initial_actions.get('debt_increase', 0)

        # Take on initial debt, which increases cash available for investment.
        if debt_to_take > 0:
            self.debt += debt_to_take
            self.cash += debt_to_take
        
        # Buy assets with the available cash.
        if amount_to_buy > 0 and self.cash >= amount_to_buy:
            self.cash -= amount_to_buy
            self.asset_value += amount_to_buy
            self.cost_basis += amount_to_buy
        
        return amount_to_buy, debt_to_take

    def apply_asset_growth(self, annual_return: float):
        """
        Applies the annual return to the asset value.
        The asset value cannot go below zero.
        Stores the previous asset value for growth tracking.
        """
        # Store current value before applying growth
        self.prev_asset_value = self.asset_value
        # Apply growth
        self.asset_value = max(0, self.asset_value * (1 + annual_return))

    def accrue_and_apply_cash_interest(self):
        """
        Calculates interest on the current cash balance, adds it to the balance,
        and returns the amount of interest earned for recording purposes.
        Returns the amount of interest earned.
        """
        interest = self.cash * self.params.get('cash_interest_rate', 0.0)
        self.cash += interest
        return interest

    def calculate_mandatory_costs(self, proposed_sale: float = 0.0) -> float:
        """
        Calculates the total mandatory costs for the year based on the current portfolio state.
        This is a read-only method used by the simulation engine to inform the strategy.
        It does NOT modify the portfolio's state.
        """
        asset_management_fee = self.asset_value * self.params.get('asset_management_fee', 0.0)
        interest_paid = self.debt * self.params.get('loan_interest_rate', 0.0)
        
        isk_tax = 0.0
        if self.params.get('tax_method') == 'isk':
            isk_tax = self.asset_value * self.params.get('isk_tax_rate', 0.0)
        
        capital_gains_tax = 0.0
        if proposed_sale > 0 and self.params.get('tax_method') == 'capital_gains':
            # This is an estimate. The strategy will refine this.
            cost_basis_ratio = self.cost_basis / self.asset_value if self.asset_value > 0 else 1.0
            gain = proposed_sale * (1 - cost_basis_ratio)
            capital_gains_tax = max(0, gain * self.params.get('capital_gains_tax_rate', 0.0))

        return asset_management_fee + interest_paid + isk_tax + capital_gains_tax

    def execute_transactions(self, year: int, strategy_actions: dict, consumption_drawdown: float, asset_value_at_start_of_year: float, cash_interest: float, shortfall_funding_policy: list[str]):
        """
        Executes all financial activities for a single year in a specific "waterfall" order.
        This method encapsulates the core bookkeeping complexity.
        """
        # --- 1. Unpack Strategy's Plan & Initialize Cash ---
        amount_contributed = strategy_actions.get('amount_contributed', 0.0)

        # The cash pool starts with cash on hand plus interest earned this year.
        # This variable will be spent down in priority order.
        cash_pool = self.cash + cash_interest

        # --- 2. Calculate Mandatory Costs ---
        asset_management_fee = self.asset_value * self.params.get('asset_management_fee', 0.0)
        interest_paid_on_debt = self.debt * self.params.get('loan_interest_rate', 0.0)
        isk_tax = 0.0
        if self.params.get('tax_method') == 'isk':
            isk_tax = self.asset_value * self.params.get('isk_tax_rate', 0.0)

        # Calculate capital gains tax ONLY on the sale planned by the strategy.
        # Tax from emergency sales will be handled later.
        capital_gains_tax = 0.0
        # --- FIX: The strategy's planned sale amount must be capped at the available asset value. ---
        # This is the true amount that can be sold.
        amount_sold_planned_capped = min(strategy_actions.get('amount_sold', 0.0), self.asset_value)

        if amount_sold_planned_capped > 0 and self.params.get('tax_method') == 'capital_gains':
            cost_basis_ratio = self.cost_basis / asset_value_at_start_of_year if asset_value_at_start_of_year > 0 else 1.0
            gain = amount_sold_planned_capped * (1 - cost_basis_ratio)
            capital_gains_tax = max(0, gain * self.params.get('capital_gains_tax_rate', 0.0))

        total_mandatory_costs_for_year = asset_management_fee + interest_paid_on_debt + isk_tax + capital_gains_tax

        # --- 3. Fund Mandatory Costs (Priority 1) ---
        # Add cash from the strategy's planned actions to the pool.
        # --- FIX: Use the capped sale amount and unpack other actions here. ---
        debt_increase_planned = strategy_actions.get('debt_increase', 0.0)
        cash_pool += amount_sold_planned_capped + debt_increase_planned + amount_contributed

        cost_shortfall = total_mandatory_costs_for_year - cash_pool
        
        amount_sold_for_shortfall = 0.0
        debt_increase_for_shortfall = 0.0
        tax_on_shortfall_sale = 0.0

        if cost_shortfall > 0:
            # Activate emergency funding policy ONLY for mandatory costs.
            shortfall_to_fund = cost_shortfall
            
            for funding_method in shortfall_funding_policy:
                if shortfall_to_fund <= 0: break

                if funding_method == 'USE_CASH':
                    # This should not happen if cash_pool was calculated correctly, but as a safeguard.
                    pass # Cash is already in the pool.

                elif funding_method == 'SELL_ASSETS':
                    tax_rate = self.params.get('capital_gains_tax_rate', 0.0) if self.params.get('tax_method') == 'capital_gains' else 0.0
                    cost_basis_ratio = self.cost_basis / asset_value_at_start_of_year if asset_value_at_start_of_year > 0 else 1.0
                    denominator = 1 - tax_rate * (1 - cost_basis_ratio)
                    
                    if denominator > 0:
                        gross_sale_needed = shortfall_to_fund / denominator
                        # Can't sell more than we have (minus what's already planned to be sold).
                        available_assets_to_sell = self.asset_value - amount_sold_planned_capped
                        actual_sale = min(gross_sale_needed, available_assets_to_sell)
                        
                        amount_sold_for_shortfall += actual_sale
                        
                        # This emergency sale generates its own tax, which is a new mandatory cost.
                        new_tax = actual_sale * tax_rate * (1 - cost_basis_ratio)
                        tax_on_shortfall_sale += new_tax
                        
                        # The cash raised covers the sale's own tax plus a portion of the original shortfall.
                        net_cash_raised = actual_sale - new_tax
                        shortfall_to_fund -= net_cash_raised

                elif funding_method == 'BORROW':
                    debt_increase_for_shortfall += shortfall_to_fund
                    shortfall_to_fund = 0

        # Add cash from emergency funding to the pool.
        cash_pool += amount_sold_for_shortfall + debt_increase_for_shortfall
        
        # Pay all mandatory costs from the pool.
        total_tax_paid_this_year = capital_gains_tax + tax_on_shortfall_sale + isk_tax
        total_costs_paid = asset_management_fee + interest_paid_on_debt + total_tax_paid_this_year
        cash_pool -= total_costs_paid

        # --- 4. Fund Consumption (Priority 2) ---
        # The amount paid for consumption is capped by the cash remaining after all costs are paid.
        # No new borrowing or selling occurs here.
        consumption_paid = min(consumption_drawdown, cash_pool)
        cash_pool -= consumption_paid

        # --- 5. Handle Debt Repayment & Reinvestment (Lowest Priority) ---
        # Use any remaining cash for planned debt repayments or reinvestments.
        debt_repayment_planned = strategy_actions.get('debt_repayment', 0.0)
        amount_bought_planned = strategy_actions.get('amount_bought', 0.0)

        cash_for_debt_repayment = min(debt_repayment_planned, cash_pool, self.debt)
        cash_pool -= cash_for_debt_repayment

        cash_for_buying = min(amount_bought_planned, cash_pool)
        cash_pool -= cash_for_buying

        # --- 6. Update Portfolio State ---
        self.cash = cash_pool # Update final cash balance.

        total_amount_sold = amount_sold_planned_capped + amount_sold_for_shortfall
        total_debt_increase = debt_increase_planned + debt_increase_for_shortfall
        
        self.asset_value -= total_amount_sold
        self.asset_value += cash_for_buying
        self.debt += total_debt_increase
        self.debt -= cash_for_debt_repayment

        if total_amount_sold > 0 and asset_value_at_start_of_year > 0:
            cost_basis_of_sold_assets = self.cost_basis * (total_amount_sold / asset_value_at_start_of_year)
            self.cost_basis -= cost_basis_of_sold_assets
        if cash_for_buying > 0:
            self.cost_basis += cash_for_buying

        # --- 7. Update Accumulators & Return Yearly Data ---
        self.accumulated_interest += interest_paid_on_debt
        self.accumulated_tax += total_tax_paid_this_year
        self.accumulated_fees += asset_management_fee

        return {
            'interest_paid': interest_paid_on_debt,
            'tax_paid': total_tax_paid_this_year,
            'fees_paid': asset_management_fee,
            'amount_sold': total_amount_sold,
            'amount_bought': cash_for_buying,
            'debt_change': total_debt_increase - cash_for_debt_repayment,
            'consumption_paid': consumption_paid, # This is now the actual amount paid
            'amount_contributed': amount_contributed,
        }

    def record_yearly_snapshot(self, year: int, transaction_results: dict, cash_interest: float):
        """
        Records the end-of-year state of the portfolio to its history.
        """
        snapshot = {
            'Year': year,
            'Asset Value': self.asset_value,
            'Debt': self.debt,
            'Cash': self.cash,
            'Net Worth': self.asset_value + self.cash - self.debt,
            'Consumption Delivered': transaction_results.get('consumption_paid', 0),
            'Amount Sold': transaction_results.get('amount_sold', 0),
            'Amount Bought': transaction_results.get('amount_bought', 0),
            'Amount Contributed': transaction_results.get('amount_contributed', 0),
            'Debt Change': transaction_results.get('debt_change', 0),
            'Interest Paid': transaction_results.get('interest_paid', 0),
            'Tax Paid': transaction_results.get('tax_paid', 0),
            'Fees Paid': transaction_results.get('fees_paid', 0),
            'Accumulated Interest': self.accumulated_interest,
            'Accumulated Tax': self.accumulated_tax,
            'Accumulated Fees': self.accumulated_fees,
            'Cash Interest': cash_interest
        }
        self.history.append(snapshot)