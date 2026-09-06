import unittest
import pandas as pd
import numpy as np
import sys
from pathlib import Path

# Add project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.input_analysis import calculate_autocorrelation, calculate_historical_drawdowns, analyze_returns_distribution, STATSMODELS_AVAILABLE

@unittest.skipIf(not STATSMODELS_AVAILABLE, "statsmodels library not found, skipping autocorrelation tests")
class TestInputAnalysis(unittest.TestCase):

    def test_calculate_autocorrelation(self):
        """
        Tests the calculate_autocorrelation function with a known series.
        """
        # A simple alternating series with known negative autocorrelation at lag 1.
        # We use a large series because the fft=True method is an approximation that is more accurate with more data points.
        data = [1, -1] * 1000
        daily_returns = pd.Series(data)
        
        lags = 5
        result = calculate_autocorrelation(daily_returns, lags=lags)

        self.assertIsNotNone(result)
        self.assertIn('acf_values', result)
        self.assertIn('conf_interval', result)
        self.assertEqual(len(result['acf_values']), lags)

        # The ACF at lag 1 for a perfectly alternating series should be -1.0
        self.assertAlmostEqual(result['acf_values'][0], -1.0, places=2)
        # The ACF at lag 2 should be +1.0
        self.assertAlmostEqual(result['acf_values'][1], 1.0, places=2)

    def test_calculate_historical_drawdowns(self):
        """
        Tests the calculate_historical_drawdowns function with a known price series.
        """
        # A simple series: peak, dip, partial recovery, new peak, new dip
        prices = pd.Series([100, 110, 88, 99, 120, 96])
        
        drawdowns = calculate_historical_drawdowns(prices)

        self.assertIsNotNone(drawdowns)
        self.assertIsInstance(drawdowns, pd.Series)
        self.assertEqual(len(drawdowns), len(prices))

        # Expected drawdowns as percentages:
        # 100 -> 0% (from 100)
        # 110 -> 0% (from 110)
        # 88  -> -20% (from 110)
        # 99  -> -10% (from 110)
        # 120 -> 0% (from 120)
        # 96  -> -20% (from 120)
        expected_values = [0.0, 0.0, -20.0, -10.0, 0.0, -20.0]
        
        for i, val in enumerate(expected_values):
            self.assertAlmostEqual(drawdowns.iloc[i], val, places=2)

    def test_analyze_returns_distribution(self):
        """
        Tests the analyze_returns_distribution function with a known series.
        """
        # A simple series for easy calculation of stats
        returns = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

        stats = analyze_returns_distribution(returns)

        self.assertIsNotNone(stats)
        self.assertIsInstance(stats, dict)

        # Expected values
        self.assertAlmostEqual(stats['mean'], 5.5, places=2)
        self.assertAlmostEqual(stats['median'], 5.5, places=2)
        self.assertAlmostEqual(stats['p25'], 3.25, places=2) # (2+3)/2 for quantile
        self.assertAlmostEqual(stats['p75'], 7.75, places=2) # (7+8)/2 for quantile