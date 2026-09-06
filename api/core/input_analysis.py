import numpy as np
import logging
import pandas as pd

try:
    from statsmodels.tsa.stattools import acf
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False

def calculate_autocorrelation(daily_returns, lags=40):
    """
    Calculates the autocorrelation function (ACF) values and confidence interval.
    
    Args:
        daily_returns (pd.Series): A series of daily returns.
        lags (int): The number of lags to calculate.

    Returns:
        dict: A dictionary containing 'acf_values' and 'conf_interval', or None if calculation fails.
    """
    if not STATSMODELS_AVAILABLE:
        logging.warning("Cannot calculate autocorrelation: 'statsmodels' is not installed.")
        return None
    
    if daily_returns is None or daily_returns.empty:
        logging.warning("Cannot calculate autocorrelation: daily_returns data is empty.")
        return None

    try:
        # Calculate ACF values, excluding the zero lag. fft=True is a fast approximation.
        acf_values = acf(daily_returns, nlags=lags, fft=True)[1:]
        
        # Calculate the 95% confidence interval
        conf_interval = 1.96 / np.sqrt(len(daily_returns))

        return {"acf_values": acf_values, "conf_interval": conf_interval, "lags": lags}
    except Exception as e:
        logging.error(f"Error calculating autocorrelation: {e}", exc_info=True)
        return None

def calculate_historical_drawdowns(prices):
    """
    Calculates the historical drawdowns from a price series.

    Args:
        prices (pd.Series): A series of asset prices.

    Returns:
        pd.Series: A series of drawdown percentages, or None if calculation fails.
    """
    if prices is None or prices.empty:
        logging.warning("Cannot calculate drawdowns: prices data is empty.")
        return None
    
    try:
        cumulative_max = prices.cummax()
        # Drawdown is the percentage decline from the peak.
        drawdowns = (prices - cumulative_max) / cumulative_max * 100
        return drawdowns
    except Exception as e:
        logging.error(f"Error calculating historical drawdowns: {e}", exc_info=True)
        return None

def analyze_returns_distribution(returns_data):
    """
    Calculates key statistics for a distribution of returns.

    Args:
        returns_data (pd.Series): A series of returns.

    Returns:
        dict: A dictionary of statistics (mean, median, p25, p75), or None if calculation fails.
    """
    if returns_data is None or returns_data.empty:
        logging.warning("Cannot analyze returns distribution: data is empty.")
        return None
    
    try:
        stats = {
            'mean': returns_data.mean(),
            'median': returns_data.median(),
            'p25': returns_data.quantile(0.25),
            'p75': returns_data.quantile(0.75)
        }
        return stats
    except Exception as e:
        logging.error(f"Error analyzing returns distribution: {e}", exc_info=True)
        return None