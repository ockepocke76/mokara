"""
Currency Storage in Simulations - Implementation Guide

## Architecture Overview

The currency field is stored in the simulation parameters JSON blob.
This approach is consistent with the current architecture where all simulation
parameters are stored in the `parameters` column of CACHED_SIMULATIONS.

## Storage Location

**Primary Storage:** `CACHED_SIMULATIONS.parameters` JSON blob
- The `parameters` field already contains all simulation configuration
- Currency is automatically included when saving `ui_params`
- No schema changes needed for new simulations

**Legacy Storage:** `SIMULATIONS.currency` column (V10 migration)
- Added for backward compatibility with old SIMULATIONS table
- This table is no longer actively used for new simulations
- Migration sets default to 'SEK' for existing records

## How Currency is Saved

### 1. User Selects Currency in Settings
```python
# In ui/settings_tab.py
user_settings = {
    'currency': 'SEK',  # or 'USD', 'EUR'
    'currency_symbol': 'SEK',
    'locale': 'sv_SE',
}
st.session_state.user_settings = user_settings
```

### 2. Currency is Included in UI Parameters
```python
# In ui/sidebar.py - automatically included
ui_params = {
    'initial_investment': 5_000_000,  # In user's currency (SEK)
    'currency': st.session_state.user_settings.get('currency', 'SEK'),
    # ... other parameters
}
```

### 3. Parameters Saved to Database
```python
# In db/sqlite_db.py - save_simulation_results()
# The ui_params (including currency) are saved to CACHED_SIMULATIONS.parameters
cursor.execute(
    "INSERT INTO CACHED_SIMULATIONS (simulation_hash, parameters, status) "
    "VALUES (?, ?, 'PENDING')",
    (simulation_hash, json.dumps(ui_params), )
)
```

### 4. Currency Retrieved When Loading
```python
# When loading simulation
params = json.loads(cached_simulation.parameters)
currency = params.get('currency', 'SEK')  # Default to SEK if not found

# All monetary values in params are in this currency
initial_investment = params['initial_investment']  # Already in correct currency
```

## Implementation Checklist

- [x] Create V10 migration for legacy SIMULATIONS table
- [x] Document currency storage approach
- [ ] Ensure currency is included in ui_params when saving simulations
- [ ] Update simulation loading to extract currency from parameters
- [ ] Display currency in simulation history/details

## Example Usage

```python
# Saving a simulation
ui_params = {
    'strategy': 'TrinityStrategy',
    'initial_investment': 5_000_000,  # 5M SEK
    'currency': 'SEK',  # User's selected currency
    'annual_drawdown': 200_000,  # 200K SEK
    # ... other params
}

# All monetary values are in SEK
# No conversion needed!

# Loading a simulation
params = load_simulation_params(simulation_hash)
currency = params.get('currency', 'SEK')

# Display values
print(f"Initial Investment: {format_currency_amount(params['initial_investment'], currency)}")
# Output: "Initial Investment: 5,000,000 SEK"
```

## Benefits

✅ **No schema changes needed** - uses existing JSON storage
✅ **Automatic inclusion** - currency comes from user settings
✅ **Backward compatible** - defaults to SEK if not present
✅ **Simple retrieval** - just parse JSON and extract currency
✅ **Consistent with architecture** - follows existing parameter storage pattern
