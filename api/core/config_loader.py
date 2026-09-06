import yaml
from pathlib import Path
import logging
from copy import deepcopy

def load_all_configs():
    """
    Loads and merges configurations from config.yml and assets/assets.yml
    into a single, comprehensive dictionary. It enriches the asset model
    definitions with the parameter configurations from the `_defaults` template
    in assets.yml.
    """
    config_path = Path(__file__).parent.parent / "config.yml"
    assets_path = Path(__file__).parent.parent / "assets" / "assets.yml"

    with open(config_path, 'r') as f:
        main_config = yaml.safe_load(f)
    
    with open(assets_path, 'r') as f:
        asset_models_config = yaml.safe_load(f)

    # --- REFACTOR: Intelligently merge parameter templates into asset models ---
    # Get the default parameter definitions from the assets.yml file
    param_defaults = asset_models_config.get('_defaults', {})

    for model_key, model_config in asset_models_config.items():
        if model_key == '_defaults' or 'parameters' not in model_config:
            continue

        # For each parameter in an asset model (e.g., num_years)...
        for param_key, param_value in model_config['parameters'].items():
            # If the parameter value is not a dictionary, it's a simple override
            # like `num_years: 30` or `local_file_path: '...'`.
            if not isinstance(param_value, dict):
                # Check if this parameter has a default definition in `_defaults`.
                if param_key in param_defaults:
                    # If it does, create a full dictionary for it, copying the template
                    # and setting the specific value. This is for UI-configurable params.
                    param_definition = deepcopy(param_defaults[param_key])
                    param_definition['value'] = param_value
                    model_config['parameters'][param_key] = param_definition
                # If it's not in _defaults (like `local_file_path`), we leave it as a
                # simple key-value pair. `assemble_params` will handle it.

    main_config['asset_models'] = asset_models_config

    logging.info("All configurations loaded and merged successfully.")
    return main_config