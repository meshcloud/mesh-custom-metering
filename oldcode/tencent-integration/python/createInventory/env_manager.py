import os
import logging

def get_env_variables(variables_config):
    """
    Retrieves environment variables based on the provided configuration.
    
    Args:
        variables_config (dict): Dictionary where keys are environment variable names
                                and values are booleans indicating if the variable
                                is mandatory (True) or optional (False).
    
    Returns:
        dict: Dictionary containing the retrieved environment variables.
        
    Raises:
        SystemExit: If any mandatory environment variable is missing.
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    # Initialize result dictionary
    result = {}
    missing_mandatory = []
    
    # Process each environment variable
    for var_name, is_mandatory in variables_config.items():
        value = os.environ.get(var_name)
        
        if value is None:
            if is_mandatory:
                missing_mandatory.append(var_name)
            else:
                logging.warning(f"Optional environment variable '{var_name}' is not set.")
        else:
            result[var_name] = value
    
    # Check if any mandatory variables are missing
    if missing_mandatory:
        missing_vars = ", ".join(missing_mandatory)
        raise RuntimeError(f"Missing required environment variables: {missing_vars}")
    
    return result