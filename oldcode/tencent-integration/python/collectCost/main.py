from cloudevents.http import CloudEvent

import functions_framework
import google.cloud.logging
import json
import base64
import logging
import traceback
from datetime import datetime, date
from google.cloud import secretmanager

import env_manager
import mesh_client
import tencent_client

def retrieve_secretManager_secret(
    project_id: str,
    secret_id: str
    ) -> str:
    """
    Retrieve the latest version of a secret from Google Secret Manager.

    Args:
        project_id (str): The ID of the Google Cloud project.
        secret_id (str): The ID of the secret.

    Returns:
        str: The secret value.
    """
    version_id = 'latest'
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    client = secretmanager.SecretManagerServiceClient()

    try:
        response = client.access_secret_version(request={"name": name})
        secret_key = response.payload.data.decode("UTF-8")
        return secret_key
    
    except google.api_core.exceptions.GoogleAPIError as e:
        logging.error(f"An error occurred: {e}")
        raise
    
def is_valid_period(
    date_string: str,
    format: str
    ) -> bool:
    """
    Check if a date string is in the expected format.
    
    Args:
        date_string: Date string to validate
        format: Expected date format
        
    Returns:
        bool: True if date is valid, False otherwise
    """
    if not date_string:  # Handle empty input
        return False
    try:
        datetime.strptime(date_string, format)
        return True
    except ValueError:
        return False

def prepare_period(usage_period: str):
    """
    Format dates for Tencent and meshStack API calls.
    Tencent expects %Y-%m, while meshStack expects %Y-%m-01Z
    
    Args:
        usage_period: Input date string
        
    Returns:
        dict: Formatted dates for Tencent and meshStack
    """
    result = {}
    tencent_month_format = "%Y-%m"
    # Use period if provided as part of env variables, otherwise use current month
    if is_valid_period(usage_period, tencent_month_format):
        result["tencent"] = usage_period
    else:
        result["tencent"] = date.today().strftime(tencent_month_format)
    
    result["meshstack"] = result["tencent"] + "-01Z"
        
    return result

# Register a CloudEvent function with the Functions Framework
@functions_framework.cloud_event
def main(event):  
    tencent_region = 'ap-guangzhou'
    
    # Prepare the response for Pubsub
    result = {'ack': False, 'statusCode': 500}
    
    # Instantiates a log client and integrates the handler with the Python logging module
    client = google.cloud.logging.Client()
    client.setup_logging()
    
    # Define required environment variables
    env_vars_config = {
        "GCP_PROJECT_ID": {"required": True,"description":"The ID of GCP project where the function should be deployed"}, 
        "WORKSPACE_ID": {"required": True,"description": "The ID of the workspace where the Tencent project exist"},
        "PLATFORM_ID": {"required": True,"description":"The ID of the Tencent platform in meshStack"},
        "GCP_SECRET_ID_MESHSECRET": {"required": True,"description":"ID of the secret in GCP Secret manager"},
        "MESH_COST_API_HOST": {"required": True,"description":"The host where meshStack API are available"},
        "MESH_API_USER": {"required": True,"description": "User name required for meshStack API authentication"},
        "GCP_SECRET_ID_TCTSECRET": {"required": True,"description":"ID of the secret in GCP Secret manager"},
        "TCT_SECRET_ID": {"required": True,"description":"The secred ID required for Tencent API authentication"},
        "USAGE_PERIOD": {"required": False,"description": "Billing period to retrieve"}
    }
    
    try:
        # Retrieve environment variables
        env = env_manager.get_env_variables(env_vars_config)

        # Retrieve secrets
        mesh_api_secret = retrieve_secretManager_secret(
            env["GCP_PROJECT_ID"], env["GCP_SECRET_ID_MESHSECRET"]
        )
        tct_secret_key = retrieve_secretManager_secret(
            env["GCP_PROJECT_ID"], env["GCP_SECRET_ID_TCTSECRET"]
        )

        # Retrieve list of accounts from pub sub topic
        data = json.loads(base64.b64decode(event.data["message"]["data"]).decode('utf-8'))
        logging.debug(f"Received meshStack accounts {data}")
    
        # Create Tencent client using the new library function    
        client = tencent_client.create_tencent_client(
            env["TCT_SECRET_ID"], 
            tct_secret_key, 
            tencent_region
        )
        
        # Prepare date format for API calls
        # Get method is used to prevent an exception when optional key USAGE_PERIOD is missing
        formated_usage_periods = prepare_period(env.get("USAGE_PERIOD"))
        
        # Retrieve cost for each account
        account_id = data
        logging.info(f"Processing account: {account_id}")
        logging.info("Retrieving cloud expenses for the period: " + formated_usage_periods["tencent"])
        
        # Use the tencent_client library to get costs
        tencent_response = tencent_client.get_tencent_costs_per_account(
            client,
            account_id,
            formated_usage_periods["tencent"],
            100
        )

        if tencent_response and tencent_response['status'] == "success":
            # Aggregate the cost data using the library function
            aggregated_result = tencent_client.aggregate_cost(tencent_response['result'])

            # If cost data is not empty, update meshStack
            if len(aggregated_result) > 0:
                payload = mesh_client.prepare_api_payload(aggregated_result, env["PLATFORM_ID"])
                meshstack_response = mesh_client.import_usage_report(
                    env["MESH_API_USER"],
                    mesh_api_secret,
                    env["MESH_COST_API_HOST"],
                    payload, 
                    account_id,
                    formated_usage_periods["meshstack"]
                )

                if meshstack_response and meshstack_response["status"] == "success":
                    logging.info(f"Usage report has been imported for the account {account_id}")
                    logging.debug(meshstack_response["result"])
                else:
                    logging.error(f"Error occurred during the import of the usage report for the account {account_id}: " + meshstack_response["message"])
            else:
                logging.info(f"No cost for the account {account_id}")    
        else:
            logging.error(f"Error while retrieving billing for {account_id}: " + tencent_response["message"])
        
        logging.info(f"Processing of {account_id} is finished")
    except Exception as err:
        logging.error(f"Error while processing the cloud costs: {err} {traceback.format_exc()}")
    
    # Success is always returned, regardless of whether the cost retrieval and import were successful.
    # This is because another attempt will be made the following day to import the monthly cloud spendings.
    result = {'ack': True, 'statusCode': 200}
    
    return result