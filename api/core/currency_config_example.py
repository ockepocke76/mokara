"""
Example: How to Use Currency Configuration for UI Parameter Scaling

This example shows how to use the currency_config module to scale
parameter ranges for UI display based on the user's selected currency.

IMPORTANT: Simulations run in the user's selected currency (SEK, USD, or EUR).
Values are stored directly in the user's currency - no conversion to USD.
"""

from core.currency_config import (
    convert_parameter_range,
    get_parameter_description,
    get_currency_ratio,
    format_currency_amount
)
from config import CONFIG

# Example 1: Get base parameter from config (defined for USD as reference)
base_investment_config = CONFIG['simulation']['initial_investment']
# This has: min=100K, max=1M, step=100K (USD reference values)

# Example 2: Get user's selected currency from settings
user_currency = 'SEK'  # This would come from st.session_state.user_settings['currency']

# Example 3: Scale the parameter range for UI display
if base_investment_config.get('is_currency', False):
    # Scale ranges for better UX in the user's currency
    scaled_range = convert_parameter_range(base_investment_config, user_currency)
    
    print(f"Reference (USD): min={base_investment_config['min']}, max={base_investment_config['max']}")
    print(f"Scaled ({user_currency}): min={scaled_range['min']}, max={scaled_range['max']}")
    
    # Output:
    # Reference (USD): min=100000, max=1000000
    # Scaled (SEK): min=1000000, max=10000000
else:
    # This parameter doesn't need currency scaling
    scaled_range = base_investment_config

# Example 4: Use in Streamlit slider
# st.slider(
#     label=scaled_range['display_name'],
#     min_value=scaled_range['min'],
#     max_value=scaled_range['max'],
#     step=scaled_range['step'],
#     value=scaled_range['value']
# )

# Example 5: Store user input directly in their currency
user_input_sek = 5_000_000  # User selected 5M SEK
# NO CONVERSION NEEDED - store directly
stored_value = user_input_sek  # = 5,000,000 SEK

print(f"User input: {user_input_sek:,} SEK")
print(f"Stored value: {stored_value:,} SEK (no conversion!)")
# Output: 
# User input: 5,000,000 SEK
# Stored value: 5,000,000 SEK (no conversion!)

# Example 6: Get description with currency appended
description = get_parameter_description(base_investment_config, 'SEK')
print(description)
# Output: "Initial portfolio value. Currency: Swedish Krona (SEK)."

# Example 7: Format currency for display
formatted = format_currency_amount(5_000_000, 'SEK')
print(formatted)
# Output: "5,000,000 SEK"

# Example 8: Asset price conversion (separate concern)
# When loading USD-denominated assets for a SEK user:
# asset_price_usd = 100  # S&P 500 price in USD
# usd_sek_rate = 10.5    # Historical rate from USD_SEK History.csv
# asset_price_sek = asset_price_usd * usd_sek_rate  # = 1050 SEK
# This conversion happens ONCE when loading asset data, not at display time!
