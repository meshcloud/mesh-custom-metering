import os
import logging
from typing import Dict, Any

# Configure basic logging for this module
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

def get_env_variables(variables_config: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    """
    Retrieves environment variables based on a detailed configuration dictionary.
    """
    retrieved_vars = {}
    missing_required = []

    for var_name, config_details in variables_config.items():
        value = os.environ.get(var_name)
        is_required = config_details.get("required", False) # Default to False if not specified

        if value is None:
            if is_required:
                missing_required.append(var_name)
            else:
                logging.info(f"Optional environment variable '{var_name}' is not set. Description: {config_details.get('description', 'N/A')}")
        else:
            retrieved_vars[var_name] = value

    if missing_required:
        missing_list = ", ".join(missing_required)
        raise RuntimeError(f"Missing required environment variables: {missing_list}. Please set them before running.")

    return retrieved_vars