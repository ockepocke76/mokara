import logging
from config import CONFIG

def validate_params(params):
    """
    Validates simulation parameters against the min/max ranges defined in the config.
    
    This function is currency-aware: for parameters marked with is_currency=true,
    it applies the appropriate currency scaling before validation to ensure
    that SEK values (which are ~10x USD) are validated against scaled ranges.
    
    Args:
        params (dict): The assembled simulation parameters.

    Returns:
        list: A list of error messages. An empty list means validation passed.
    """
    errors = []
    
    # Get user's currency for scaling currency-aware parameters
    from core.simulation_currency import get_simulation_currency
    user_currency = get_simulation_currency(params)
    
    def check_value(param_name, value, config_section):
        """Helper to check a single parameter's value against its config."""
        if param_name in config_section:
            conf = config_section[param_name]
            
            # Check if this parameter is currency-aware
            is_currency_param = conf.get('is_currency', False)
            
            # If it's a currency parameter, scale the ranges to match the user's currency
            if is_currency_param:
                from core.currency_config import convert_parameter_range
                conf = convert_parameter_range(conf, user_currency)
            
            min_val = conf.get('min')
            max_val = conf.get('max')
            if min_val is not None and value < min_val:
                errors.append(f"Validation Error: '{param_name}' ({value:,}) is below the minimum allowed value of {min_val:,} for currency {user_currency}.")
            if max_val is not None and value > max_val:
                errors.append(f"Validation Error: '{param_name}' ({value:,}) is above the maximum allowed value of {max_val:,} for currency {user_currency}.")

    # Check all relevant sections of the config
    for section_name, section_config in CONFIG.items():
        for param_name, value in params.items():
            if isinstance(section_config, dict) and param_name in section_config:
                check_value(param_name, value, section_config)

    return errors