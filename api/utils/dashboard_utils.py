from core.cache import ttl_cache
import random
import numpy as np
import logging
from core.config_loader import load_all_configs
from core.shared_logic import assemble_params
from core.data import load_and_prepare_data

@ttl_cache(ttl=3600)
def get_random_comparison_assets(n=2):
    """
    Selects 'n' random enabled assets from the configuration and computes their
    historical/parametric statistics (CAGR, Volatility).
    
    Returns:
        List of dicts: [{'name': ..., 'cagr': ..., 'vol': ..., 'desc': ...}, ...]
    """
    try:
        config = load_all_configs()
        models = config.get('asset_models', {})
        
        # Filter for enabled assets only
        valid_models = []
        for key, model_config in models.items():
            if key == '_defaults':
                continue
            # Check enabled flag (default to True if not specified, though usually it is)
            if model_config.get('enabled', True):
                valid_models.append(key)
        
        if len(valid_models) < n:
            # If fewer than n, return all
            selected_keys = valid_models
        else:
            selected_keys = random.sample(valid_models, n)
            
        results = []
        for key in selected_keys:
            try:
                # Create minimal parameters to load data
                # We need to assemble full params to handle defaults correctly
                # We don't have user overrides here, so we pass empty dict or minimal
                # Note: assemble_params expects a dict of UI overrides.
                ui_params = {'asset_model': key}
                
                # Assemble full params (merges config.yml, assets.yml defaults)
                params = assemble_params(ui_params)
                
                # Disable caching logic inside load_and_prepare_data if we want fresh?
                # Actually we DO want caching to speed this up.
                data = load_and_prepare_data(params)
                
                if data:
                    mu = data.get('mu', 0.0)
                    sigma = data.get('sigma', 0.0)
                    
                    # Annualize statistics
                    # mu is daily geometric mean return? 
                    # generic calculation: (1+mu)^365 - 1
                    cagr = (1 + mu)**365 - 1
                    vol = sigma * np.sqrt(365)
                    
                    # Get display details
                    model_conf = models[key]
                    name = model_conf.get('display_name', key.replace('_', ' ').title())
                    desc = model_conf.get('description', f"Asset class: {name}")
                    
                    results.append({
                        'name': name,
                        'cagr': cagr,
                        'vol': vol,
                        'desc': desc,
                        'type': model_conf.get('type', 'unknown')
                    })
            except Exception as e:
                logging.error(f"Error loading asset '{key}' for dashboard: {e}")
                continue
                
        return results
        
    except Exception as e:
        logging.error(f"Failed to get comparison assets: {e}")
        return []
