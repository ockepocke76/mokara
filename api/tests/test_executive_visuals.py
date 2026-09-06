"""
Test script for executive summary visualizations.

This script creates sample data and generates the executive visualizations
to verify they work correctly before running a full simulation.
"""

from reporting.executive_visuals import create_financial_health_bubble, create_success_gauges

# Sample simulation parameters
sample_params = {
    'strategy': 'trinity',
    'initial_investment': 1000000,
    'num_years': 30,
    'asset_name': 'S&P 500',
    'ticker_symbol': 'GSPC'
}

# Sample statistics
sample_stats = {
    'median_final_net_worth': 3500000,
    'median_total_withdrawn': 2000000,
    'median_total_contributions': 0,
    'success_rate': 0.92,
    'chance_of_ruin': 0.05,
    'chance_of_real_profit': 0.95,
    'median_accumulated_interest': 0,
    'median_accumulated_tax': 150000,
    'median_accumulated_fees': 50000
}

# Test bubble chart
print("🎨 Generating Financial Health Bubble Chart...")
bubble_fig = create_financial_health_bubble(sample_params, sample_stats, currency='SEK')
if bubble_fig:
    print("✅ Bubble chart created successfully!")
    # Save to HTML for visual inspection
    bubble_fig.write_html('/tmp/bubble_chart_test.html')
    print("   Saved to: /tmp/bubble_chart_test.html")
else:
    print("❌ Failed to create bubble chart")

# Test gauges
print("\n📊 Generating Success Gauges...")
gauges_fig = create_success_gauges(sample_stats)
if gauges_fig:
    print("✅ Success gauges created successfully!")
    # Save to HTML for visual inspection
    gauges_fig.write_html('/tmp/gauges_test.html')
    print("   Saved to: /tmp/gauges_test.html")
else:
    print("❌ Failed to create gauges")

print("\n✨ Test complete! Open the HTML files in a browser to view the visualizations.")
