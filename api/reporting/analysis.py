import logging
from .content import get_methodology_description
from core.strategy import TrinityStrategy, BuyBorrowDieStrategy
from core.strategy_get_rich_stay_rich import GetRichStayRichStrategy
from core.currency_config import format_currency_amount
from core.llm import call_gemini_safe

try:
    from core.llm import call_gemini_safe
    GEMINI_AVAILABLE = True
except ImportError:
    logging.warning("core.llm not found or unavailable. Gemini analysis will be skipped.")
    GEMINI_AVAILABLE = False

# ============================================================================
# Strategy Description Registry
# ============================================================================
# This registry maps strategy names to functions that generate their
# AI analysis descriptions. This makes it easy to add new strategies
# without modifying the core prompt generation logic.
# ============================================================================

def _describe_trinity_strategy(params):
    """Generate AI prompt description for Trinity strategy."""
    return f"""
- **Strategy:** Asset Withdrawal (Trinity-style)
    - **Base Withdrawal Rate:** {params['withdrawal_rate']:.2%} of initial portfolio per year
    - **Inflation Adjustment:** {params['inflation_rate']:.2%} per year
"""

def _describe_get_rich_stay_rich_strategy(params, currency='SEK'):
    """Generate AI prompt description for Get Rich Stay Rich strategy."""
    target_worth_formatted = format_currency_amount(params.get('target_net_worth', 0), currency, decimals=0)
    return f"""
- **Strategy:** Get Rich Stay Rich
    - **Target Net Worth:** {target_worth_formatted}
    - **Withdrawal Rate (Stay Rich Phase):** {params.get('withdrawal_rate', 0.0):.2%} of target net worth
    - **Cash Reserve Years:** {params.get('cash_years_on_stay_rich', 2)} years
    - **Inflation Adjustment:** {params.get('inflation_rate', 0.02):.2%} per year
"""

def _describe_buy_borrow_die_strategy(params, currency='SEK'):
    """Generate AI prompt description for Buy Borrow Die strategy."""
    if 'drawdown_method' not in params:
        return "- **Strategy:** Buy Borrow Die (Borrowing)\n    - **Note:** Detailed parameters not available\n"
    
    details = "- **Strategy:** Loan Drawdown (Buy Borrow Die)\n"
    if 'loan_interest_rate' in params:
        details += f"- **Loan Interest Rate:** {params['loan_interest_rate']:.2%}\n"
    
    if params['drawdown_method'] == 'percentage':
        max_drawdown_formatted = format_currency_amount(int(params['max_drawdown']), currency, decimals=0) if params['max_drawdown'] is not None else 'None'
        details += f"""
- **Drawdown Model:** Percentage-based
    - **Rate:** {params['percentage_drawdown']:.2%} of asset value per year
    - **Max Consumption Delivered:** {max_drawdown_formatted} """
    else:  # 'fixed'
        fixed_drawdown_formatted = format_currency_amount(params['fixed_drawdown'], currency, decimals=0)
        details += f"""
- **Drawdown Model:** Fixed amount
    - **Base Amount:** {fixed_drawdown_formatted} per year
    - **Inflation Adjustment:** {params['inflation_rate']:.2%} per year"""
    return details

def _describe_custom_strategy(params):
    """Generate AI prompt description for custom strategies."""
    description = params.get('custom_strategy_description', 'No description provided')
    strategy_name = params.get('custom_strategy_name', 'Unnamed')
    details = f"- **Strategy:** Custom Strategy ({strategy_name})\n"
    details += f"    - **Description:** {description}\n"
    
    # Include strategy-specific parameters if available
    strategy_params = params.get('custom_strategy_params', {})
    if strategy_params:
        details += "    - **Strategy Parameters:**\n"
        for param_name, param_value in strategy_params.items():
            # Format the parameter nicely
            if isinstance(param_value, float):
                if 0 < param_value < 1:  # Likely a percentage
                    details += f"        - {param_name.replace('_', ' ').title()}: {param_value:.2%}\n"
                else:
                    details += f"        - {param_name.replace('_', ' ').title()}: {param_value:.2f}\n"
            elif isinstance(param_value, int):
                details += f"        - {param_name.replace('_', ' ').title()}: {param_value:,}\n"
            else:
                details += f"        - {param_name.replace('_', ' ').title()}: {param_value}\n"
    
    return details

# Registry mapping strategy names to their description functions
STRATEGY_DESCRIPTION_REGISTRY = {
    'trinity': _describe_trinity_strategy,
    'get_rich_stay_rich': _describe_get_rich_stay_rich_strategy,
    'buy_borrow_die': _describe_buy_borrow_die_strategy,
    'custom': _describe_custom_strategy,
}

def _get_prompt_drawdown_details(params, currency='SEK'):
    """Builds the drawdown/strategy details part of the Gemini prompt."""
    strategy = params.get('strategy', 'unknown')
    
    # Check registry first
    if strategy in STRATEGY_DESCRIPTION_REGISTRY:
        # Pass currency to strategy description functions that support it
        desc_func = STRATEGY_DESCRIPTION_REGISTRY[strategy]
        try:
            return desc_func(params, currency)
        except TypeError:
            # Function doesn't accept currency parameter (e.g., trinity, custom)
            return desc_func(params)
    
    # Unknown strategy - provide generic description
    return f"- **Strategy:** {strategy.replace('_', ' ').title()}\n    - **Note:** Strategy-specific parameters not available for AI analysis\n"

def _get_prompt_tax_details(params):
    """Builds the tax details part of the Gemini prompt."""
    tax_method = params.get('tax_method')
    if tax_method == 'isk':
        return f"""
- **Tax Model:** ISK-style Wealth Tax
    - **Rate:** {params.get('isk_tax_rate', 0.0):.3%} of total asset value per year"""
    elif tax_method == 'capital_gains':
        return f"""
- **Tax Model:** Capital Gains Tax
    - **Rate:** {params.get('capital_gains_tax_rate', 0.0):.1%} on profits from asset sales"""
    return "- **Tax Model:** None"

def _get_prompt_deleveraging_details(params):
    """Builds the LTV management details part of the Gemini prompt."""
    if params.get('enable_deleveraging', False) or params.get('enable_tiered_ltv', False):
        details = "\n- **LTV Management Strategy:** Enabled"
        if params.get('enable_tiered_ltv', False):
            details += f"\n    - **Warning Tier:** Suspend all drawdowns if LTV exceeds {params['ltv_warning_threshold']:.1%}."
        if params.get('enable_deleveraging', False):
            details += f"\n    - **Action Tier:** Trigger asset sales to deleverage if LTV exceeds {params['ltv_action_threshold']:.1%}."
            details += f"\n    - **Target LTV After Sale:** {params['deleveraging_target']:.1%}"
        return details
    return "- **LTV Management Strategy:** Disabled (or not applicable for Trinity mode)"

def _get_prompt_asset_details(params):
    """Builds the asset model details part of the Gemini prompt."""
    if params['asset_model'] == 'parametric':
        return f"""
- **Asset Growth Model:** Parametric (Synthetic)
    - **Assumed Annual Return:** {params.get('annual_return', 0.0) * 100:.1f}%
    - **Assumed Annual Volatility:** {params.get('annual_volatility', 0.0) * 100:.1f}%"""
    
    # Bootstrap models (covers bootstrap_btc, bootstrap_stockindex, bootstrap_synthetic)
    details = f"- **Asset Growth Model:** Bootstrap from {params['asset_name']} historical data"
    threshold = params.get('return_threshold_rate')
    if threshold is not None and threshold >= 0:
        details += f"\n    - **Return Threshold:** {params['return_threshold_rate']:.2%}"
    if params.get('asset_management_fee', 0.0) > 0:
        details += f"\n    - **Asset Management Fee:** {params['asset_management_fee']:.2%}"
    return details

def _clean_methodology_text(methodology_text_func):
    """Fetches and cleans the methodology text for the prompt."""
    methodology_text = methodology_text_func()
    return (
        methodology_text.replace('<br/>', '\n')
        .replace('<b>', '**').replace('</b>', '**')
        .replace('<i>', '*').replace('</i>', '*')
        .replace('<u>', '').replace('</u>', '')
    )

def get_gemini_analysis_prompt(params, stats, currency='SEK', strategy_description=None):
    logging.info("Generating Gemini analysis prompt.")
    """Generates a detailed prompt for an AI to analyze the simulation results.
    
    Args:
        params: Simulation parameters
        stats: Statistical results
        currency: Currency code
        strategy_description: Optional description of the strategy being analyzed
    """

    initial_investment_formatted = format_currency_amount(params['initial_investment'], currency, decimals=0)
    
    prompt = f"""You are an expert financial analyst. Write a professional, objective analysis of the following Monte Carlo simulation results for a formal report.

FORMATTING: Use numeric digits for all numbers (e.g., "25,000,000 SEK"), commas as thousand separators, no markdown headings (#), no LaTeX. Dive directly into the assessment.

**Simulation Setup & Parameters:**
- **Strategy:** {' '.join(word.capitalize() for word in params['strategy'].split('_'))}
{f"- **Strategy Description:** {strategy_description}" if strategy_description else ""}
- **Simulations:** {params['num_simulations']:,} | **Time Horizon:** {params['num_years']} years | **Initial:** {initial_investment_formatted}
{_get_prompt_asset_details(params)}
{_get_prompt_drawdown_details(params, currency)}
{_get_prompt_tax_details(params)}
{_get_prompt_deleveraging_details(params)}

**Key Outcomes (Year {params['num_years']}):"""
    
    # Universal outcome metrics (no strategy-specific branching)
    p25_final = format_currency_amount(int(stats.get('p25_final_net_worth', 0)), currency, decimals=0)
    p75_final = format_currency_amount(int(stats.get('p75_final_net_worth', 0)), currency, decimals=0)
    median_final = format_currency_amount(int(stats.get('median_final_net_worth', 0)), currency, decimals=0)
    real_final = format_currency_amount(int(stats.get('median_real_final_net_worth', 0)), currency, decimals=0)
    total_withdrawn = format_currency_amount(int(stats.get('median_total_withdrawn', 0)), currency, decimals=0)
    
    prompt += f"""
- **Median Final Net Worth:** {median_final} (Real: {real_final})
- **Range (25th-75th):** {p25_final} to {p75_final}
- **Total Withdrawn:** {total_withdrawn}
- **Success Rate:** {stats.get('success_rate', 0.0):.1%} | **Chance of Profit:** {stats.get('chance_of_profit', 0.0):.1%}"""
    
    # Conditional metrics based on available data
    years_remaining = stats.get('median_years_of_spending_left')
    if years_remaining is not None and years_remaining != 'N/A':
        prompt += f"\n- **Years of Spending Left:** {years_remaining:.1f}"
    if stats.get('chance_of_ruin', 0) > 0:
        prompt += f"\n- **Risk of Ruin:** {stats.get('chance_of_ruin', 0.0):.1%}"
    if stats.get('median_final_ltv_stat', 0) > 0:
        prompt += f"\n- **Median Final LTV:** {stats.get('median_final_ltv_stat', 0.0):.1%}"
    
    # === KEY CONTEXTUAL INSIGHTS (reduced to 2-3 most important) ===
    prompt += "\n\n**Key Insights:**\n"
    
    # 1. Outcome uncertainty
    p5_val = stats.get('p5_final_net_worth', 0)
    p95_val = stats.get('p95_final_net_worth', 0)
    median_val = stats.get('median_final_net_worth', 0)
    if median_val > 0:
        spread_ratio = (p95_val - p5_val) / median_val
        spread_desc = "high" if spread_ratio > 2 else "moderate" if spread_ratio > 1 else "low"
        p5_formatted = format_currency_amount(int(p5_val), currency, decimals=0)
        p95_formatted = format_currency_amount(int(p95_val), currency, decimals=0)
        prompt += f"- **Outcome Uncertainty ({spread_desc}):** 90% range: {p5_formatted} to {p95_formatted} ({spread_ratio:.1f}x median)\n"
    
    # 2. Cost efficiency
    initial = params.get('initial_investment', 0)
    total_costs = stats.get('median_accumulated_total_costs', 0)
    if initial > 0 and median_val > initial:
        gross_return = median_val - initial
        cost_pct = (total_costs / gross_return) * 100 if gross_return > 0 else 0
        costs_formatted = format_currency_amount(int(total_costs), currency, decimals=0)
        prompt += f"- **Cost Efficiency:** Costs ({costs_formatted}) consumed {cost_pct:.1f}% of returns\n"
    
    # Risk metrics (shortened - values only)
    prompt += f"""
**Risk Metrics:**
- Sharpe: {stats.get('asset_sharpe_ratio', 0.0):.2f} | Sortino: {stats.get('asset_sortino_ratio', 0.0):.2f} | Ulcer Index: {stats.get('asset_ulcer_index', 0.0):.2f}"""
    var_formatted = format_currency_amount(int(stats.get('var_95_loss', 0)), currency, decimals=0)
    prompt += f"\n- VaR (95%): {var_formatted}"
    
    # Psychological Stress Indicators
    prompt += f"""

**Psychological Stress Indicators:**
- Time Underwater: {stats.get('median_time_underwater', 0):.1f} years spent below previous peak
- Recovery Time: {stats.get('median_recovery_time', 0):.1f} years to recover from worst drawdown
- Consecutive Losses: Up to {stats.get('p90_consecutive_declines', 0):.1f} years of back-to-back declines (90th percentile)
- Severe Drawdowns: {stats.get('median_severe_drawdown_count', 0):.1f} times experiencing >20% drops
- Years Below Initial: {stats.get('median_years_below_initial', 0):.1f} years below starting capital
"""
    
    # Methodology summary (condensed)
    prompt += f"""

**Methodology:** Bootstrap Monte Carlo simulation using historical returns with random sampling. Results show probability distribution across {params['num_simulations']:,} scenarios.

**RISK CALIBRATION:**
- SUCCESS > 95%: Safe | 85-95%: MODERATE RISK | < 85%: HIGH RISK
Avoid "high success" language for rates below 95%.

**STRATEGY-AWARE EVALUATION:**
The Strategy Description defines what SUCCESS means for this strategy.
Evaluate outcomes based on the strategy's STATED GOALS, not generic assumptions.
A low final balance is failure for some strategies but success for others.
Let the strategy description guide your interpretation.

**Analysis Structure:**
1. **Overall Viability** (given stated goals, apply risk calibration)
2. **Key Risk Factors** (volatility, costs, sequence risk)
3. **Recommendations** (actionable improvements relative to goals)
"""
    return prompt.strip()

def get_gemini_analysis(prompt, api_key, analytics_tracking_info=None):
    logging.info("Sending prompt to Gemini API.")
    """Sends a prompt to the Gemini API and returns the analysis text."""
    if not GEMINI_AVAILABLE:
        return "AI analysis skipped: The 'google-genai' library is not installed. Please run 'pip install google-genai'."
    
    if not api_key:
        return "AI analysis skipped: The Gemini API key is not configured. For Streamlit deployment, add 'GEMINI_API_KEY' to your secrets. For local execution, set it as an environment variable."

    try:
        # Use centralized wrapper
        text, error_msg, usage_meta = call_gemini_safe('gemini-2.0-flash', prompt, api_key=api_key)
        
        if error_msg:
             logging.warning(f"AI Analysis blocked: {error_msg}")
             return f"AI analysis unavailable: {error_msg}"
             
        if not text:
             return "AI analysis unavailable: No response generated."

        logging.info("Successfully received analysis from Gemini.")
        
        # --- Analytics Tracking ---
        if analytics_tracking_info and 'service' in analytics_tracking_info:
            try:
                service = analytics_tracking_info['service']
                user_id = analytics_tracking_info.get('user_id')
                operation = analytics_tracking_info.get('operation', 'analysis')
                
                # Use actual token counts if available, otherwise fallback to estimation
                prompt_tokens = usage_meta.get('prompt_tokens', len(prompt) // 4) if usage_meta else len(prompt) // 4
                completion_tokens = usage_meta.get('completion_tokens', len(text) // 4) if usage_meta else len(text) // 4
                
                service.track_ai_usage(
                    user_id=user_id,
                    operation=operation,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens
                )
            except Exception as e:
                logging.warning(f"Failed to track AI analytics: {e}")

        # Replace markdown with simple line breaks for PDF
        return text.replace('**', '').replace('*', '')

    except Exception as e:
        error_message = f"An error occurred while contacting the Gemini API: {e}"
        logging.error(error_message)
        return f"AI analysis failed: {error_message}"

def get_executive_summary_prompt(params, stats, strategy_description, currency='SEK'):
    """Generates a prompt to create a two-part executive summary."""
    logging.info("Generating executive summary prompt.")

    # Safely get stats with defaults
    median_final_net_worth = stats.get('median_final_net_worth', 0)
    p25_final_net_worth = stats.get('p25_final_net_worth', 0)
    p75_final_net_worth = stats.get('p75_final_net_worth', 0)
    success_rate = stats.get('success_rate', 0.0) * 100
    sortino_ratio = stats.get('asset_sortino_ratio', 0.0)
    downside_volatility = stats.get('downside_volatility', 0.0)
    p95_ltv = stats.get('p95_max_ltv', 0.0) * 100
    liquidation_percentage = stats.get('chance_of_ruin', 0.0) * 100
    median_longevity = stats.get('median_years_of_spending_left')
    if median_longevity is None:
        median_longevity = 'N/A'
    ruin_rate = (1 - stats.get('success_rate', 1.0)) * 100 if params['strategy'] == 'trinity' else liquidation_percentage
    median_total_drawdown = stats.get('median_total_withdrawn', 0)
    median_total_contributions = stats.get('median_total_contributions', 0)
    median_total_costs = stats.get('median_accumulated_total_costs', 0)
    median_accumulated_interest = stats.get('median_accumulated_interest', 0)
    median_accumulated_tax = stats.get('median_accumulated_tax', 0)
    median_accumulated_fees = stats.get('median_accumulated_fees', 0)

    # Format all currency values
    median_final_formatted = format_currency_amount(median_final_net_worth, currency, decimals=0)
    p25_formatted = format_currency_amount(p25_final_net_worth, currency, decimals=0)
    p75_formatted = format_currency_amount(p75_final_net_worth, currency, decimals=0)
    contributions_formatted = format_currency_amount(median_total_contributions, currency, decimals=0)
    drawdown_formatted = format_currency_amount(median_total_drawdown, currency, decimals=0)
    costs_formatted = format_currency_amount(median_total_costs, currency, decimals=0)
    interest_formatted = format_currency_amount(median_accumulated_interest, currency, decimals=0)
    tax_formatted = format_currency_amount(median_accumulated_tax, currency, decimals=0)
    fees_formatted = format_currency_amount(median_accumulated_fees, currency, decimals=0)

    prompt = f"""
You are an expert financial analyst. Your task is to generate a two-part executive summary for a financial simulation. Use the provided strategy description to understand its goals and interpret the data dashboard.

IMPORTANT FORMATTING RULES:
- Write all numbers using numeric digits, NOT words (e.g., write "25,000,000 SEK" not "twenty-five million SEK")
- Write percentages as digits (e.g., "81.8%" not "eighty-one point eight percent")
- Use commas as thousand separators (e.g., "1,000,000" not "1000000")
- Do not use LaTeX or mathematical notation

Strategy Description: '{strategy_description}'

Simulation Data Dashboard:

Performance:
Final Net Worth (Median): {median_final_formatted}
Final Net Worth Range (25th-75th Percentile): {p25_formatted} to {p75_formatted}
Success Rate: {success_rate:.1f}%

Costs and Contributions:
Total Contributions (Median): {contributions_formatted}
Total Withdrawn for Living Expenses (Median): {drawdown_formatted}
Total Costs (Median): {costs_formatted}
    - Interest: {interest_formatted}
    - Tax: {tax_formatted}
    - Fees: {fees_formatted}


Risk:
Asset Risk-Adjusted Return (Sortino Ratio): {sortino_ratio:.2f}
Downside Volatility: {downside_volatility:.2f}
"""
    
    # Only include leverage metrics if the strategy actually uses debt
    # Check if there's accumulated interest, which indicates borrowing
    if median_accumulated_interest > 0:
        prompt += f"""Leverage:
Peak Loan-to-Value (LTV) (95th Percentile): {p95_ltv:.1f}%
Liquidation Events: {liquidation_percentage:.1f}% of simulations
"""
    
    prompt += f"""Retirement/Withdrawal:
Portfolio Longevity (Median): {median_longevity if isinstance(median_longevity, str) else f'{median_longevity:.1f}'} years
Chance of Ruin: {ruin_rate:.1f}%

**CRITICAL RISK CALIBRATION (For Retirement Planning):**
Apply these FIRE community standards when evaluating success rates:
- SUCCESS RATE > 95%: Safe for retirement planning
- SUCCESS RATE 85-95%: MODERATE RISK - Requires contingency planning  
- SUCCESS RATE < 85%: HIGH RISK - Significant probability of portfolio depletion

**STRATEGY-AWARE EVALUATION:**
The Strategy Description defines what SUCCESS means. Evaluate outcomes based on the strategy's STATED GOALS, not generic assumptions. Let the strategy description guide your interpretation.

Part 1: Quantitative Summary 
Based on the data, write a brief, objective paragraph summarizing the key outcomes of the simulation. Apply the risk calibration standards above - do NOT describe success rates below 95% as "high" or "excellent". Evaluate outcomes based on what the strategy is TRYING to achieve (from the Strategy Description). Use plain text formatting without special characters.

Part 2: Qualitative Analysis & Recommendations
Now, provide a qualitative interpretation with actionable advice. Explain the story behind the numbers. Based on the strategy's stated goals and the resulting data, address:

1. Did the strategy successfully achieve its described purpose?
2. What are the key risks (especially cost drag and success rate)?
3. **What are your specific recommendations?** (e.g., lower withdrawal rate, larger cash buffer, fee reduction, de-leveraging)
4. Who is this suitable for?

Write a second paragraph that provides this insight and clear, actionable recommendations.
"""
    return prompt.strip()

def get_executive_summary_from_gemini(prompt, api_key):
    """Sends a prompt to Gemini and returns the two-part executive summary."""
    logging.info("Getting executive summary from Gemini.")
    return get_gemini_analysis(prompt, api_key)