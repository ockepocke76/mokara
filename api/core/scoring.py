import numpy as np
import logging

def _normalize_and_clip(value, min_val, max_val):
    """Normalizes a value to a 0-1 scale and clips it within that range."""
    if max_val == min_val:
        return 0.0
    normalized = (value - min_val) / (max_val - min_val)
    return np.clip(normalized, 0.0, 1.0)

def calculate_risk_score(stats: dict, params: dict) -> float:
    """
    Calculates a composite risk score on a scale of 1-10.
    1 = Very Low Risk, 10 = Very High Risk.

    The score is a weighted average of several risk factors:
    - Risk of Ruin (60%): The probability of insolvency or portfolio depletion.
    - Volatility of Outcome (20%): The dispersion of final net worth outcomes.
    - Leverage Risk (20%): The level of debt relative to asset value.
    """
    try:
        # --- 1. Risk of Ruin (Catastrophic Failure) ---
        # This is the most important factor.
        risk_factor_ruin = stats.get('chance_of_ruin', 0.0)

        # --- 2. Volatility of Outcome (Uncertainty) ---
        # Use Interquartile Range as a percentage of the median.
        # A higher value means more uncertainty in the final outcome.
        median_nw = stats.get('median_final_net_worth', 0.0)
        iqr_nw = stats.get('iqr_final_net_worth', 0.0)
        if median_nw > 0:
            relative_iqr = iqr_nw / median_nw
            # Normalize: Assume a relative IQR of 2.0 (i.e., spread is 2x the median) is very high risk.
            risk_factor_volatility = _normalize_and_clip(relative_iqr, 0.0, 2.0)
        else:
            risk_factor_volatility = 1.0 # If median is zero or negative, volatility risk is max.

        # --- 3. Leverage Risk (Margin Call / Forced Sale Risk) ---
        # Use the 90th percentile of the maximum LTV reached in any year.
        # This represents a "bad case" leverage scenario.
        if params['strategy'] == 'buy_borrow_die':
            p90_max_ltv = stats.get('p90_max_ltv', 0.0)
            # Normalize: An LTV of 50% is considered very high risk.
            risk_factor_leverage = _normalize_and_clip(p90_max_ltv, 0.0, 0.5)
        else: # Trinity strategy has no leverage risk.
            risk_factor_leverage = 0.0

        # --- 4. Combine Factors with Weights ---
        weights = {'ruin': 0.6, 'volatility': 0.2, 'leverage': 0.2}
        total_risk_normalized = (
            risk_factor_ruin * weights['ruin'] +
            risk_factor_volatility * weights['volatility'] +
            risk_factor_leverage * weights['leverage']
        )

        # --- 5. Scale to 1-10 ---
        # Scale from 0-1 to 1-10.
        final_score = 1 + (total_risk_normalized * 9)
        return round(final_score, 1)

    except Exception as e:
        logging.error(f"Failed to calculate risk score: {e}", exc_info=True)
        return -1.0 # Return an error value

def calculate_risk_return_score(stats: dict, params: dict) -> float:
    """
    Calculates a risk-return score on a scale of 1-10.
    1 = Poor risk/return trade-off, 10 = Excellent risk/return trade-off.

    This score is high if the potential for real (inflation-adjusted) return is high
    and the risk of catastrophic loss is low.
    """
    try:
        # --- 1. Upside Potential ---
        # Use the median real final net worth as a multiple of the initial investment.
        initial_investment = params.get('initial_investment', 1.0)
        median_real_nw = stats.get('median_real_final_net_worth', 0.0)
        real_return_multiple = median_real_nw / initial_investment if initial_investment > 0 else 0.0
        # Normalize: A 5x real return is considered excellent.
        upside_score = _normalize_and_clip(real_return_multiple, 0.0, 5.0)

        # --- 2. Downside Risk ---
        # Combine risk of ruin and the chance of not making a real profit.
        chance_of_ruin = stats.get('chance_of_ruin', 0.0)
        chance_of_no_real_profit = 1.0 - stats.get('chance_of_real_profit', 0.0)
        downside_risk = (chance_of_ruin * 0.7) + (chance_of_no_real_profit * 0.3) # Weight ruin more heavily
        # Invert to get a "safety score"
        safety_score = 1.0 - downside_risk

        # --- 3. Combine and Scale ---
        # A simple average of the upside potential and the safety score.
        combined_score = (upside_score * 0.5) + (safety_score * 0.5)
        final_score = 1 + (combined_score * 9)
        return round(final_score, 1)

    except Exception as e:
        logging.error(f"Failed to calculate risk-return score: {e}", exc_info=True)
        return -1.0