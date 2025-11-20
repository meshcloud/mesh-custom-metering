import json, base64, logging, os, traceback
from typing import Dict

import env_manager
import mesh_client

import functions_framework
import google.cloud.logging
from google.cloud import secretmanager
from cloudevents.http import CloudEvent


# Lookup if each Tencent account already exists in meshStack
# if the account does not exist, save as tenant to be imported
def findNewdTenants(inventory):
    listTenantsToCreate = []
    try:
        meshStackInventory = inventory["meshStack"]
        tencentInventory = inventory["tencent"]
        for account in tencentInventory:
            if not (
                account in meshStackInventory
            ):  # meshStack tenant does not exist in Tencent, i.e. was deleted at source
                listTenantsToCreate.append(
                    {
                        "localId": account,
                        "projectDisplayName": tencentInventory[account]["Name"],
                        "landingZoneId": tencentInventory[account]["NodeId"],
                    }
                )
    except Exception as e:
        logging.error(
            f"Error while extracting new tenants: {str(e)} {traceback.format_exc()}"
        )
        listTenantsToCreate = []
    return listTenantsToCreate


def retrieve_secretManager_secret(project_id: str, secret_id: str) -> str:
    """
    Retrieve the latest version of a secret from Google Secret Manager.

    Args:
        project_id (str): The ID of the Google Cloud project.
        secret_id (str): The ID of the secret.

    Returns:
        str: The secret value.
    """
    version_id = "latest"
    name = f"projects/{project_id}/secrets/{secret_id}/versions/{version_id}"
    client = secretmanager.SecretManagerServiceClient()

    try:
        response = client.access_secret_version(request={"name": name})
        secret_key = response.payload.data.decode("UTF-8")
        return secret_key
    except google.api_core.exceptions.GoogleAPIError as e:
        logging.error(f"An error occurred: {e}")
        raise


# Register a CloudEvent function with the Functions Framework
@functions_framework.cloud_event
def main(event):

    result = {"ack": False, "statusCode": 500}

    # Instantiates a client and integrates the handler with the Python logging module
    client = google.cloud.logging.Client()
    client.setup_logging()

    # Define required environment variables
    env_vars = {
        "WORKSPACE_ID": True,
        "PLATFORM_ID": True,
        "PAYMENT_ID": True,
        "MESH_API_HOST": True,
        "MESH_API_USER": True,
        "GCP_PROJECT_ID": True,
        "GCP_SECRET_ID_MESHSECRET": True,
    }

    try:
        # Retrieve environment variables
        env = env_manager.get_env_variables(env_vars)

        # Retrieve secrets from GCP Secret Manager
        mesh_api_secret = retrieve_secretManager_secret(
            env["GCP_PROJECT_ID"], env["GCP_SECRET_ID_MESHSECRET"]
        )

        # Process received message
        data = json.loads(
            base64.b64decode(event.data["message"]["data"]).decode("utf-8")
        )
        logging.info(f"Received data: {data}")

        # Compare list of existing meshstack tenants and tencent accounts and extract tenants / projects to be created
        newTenants = findNewdTenants(data)
        if len(newTenants) > 0:
            result = manage_new_tenant(newTenants, env)
        else:
            logging.info("No new Tencent accounts have been found.")
            result = {"ack": True, "statusCode": 200}

    except Exception as e:
        logging.error(
            f"Error while processing pubsub message: {str(e)} {traceback.format_exc()}"
        )
        result = {"ack": False, "statusCode": 500}

    return result


def manage_new_tenant(newTenants, env):
    result = {}

    try:

        logging.info(f"Newly detected Tencent accounts: {json.dumps(newTenants)}")

        # Create API payload for new tenants and projects
        api_payload = mesh_client.prepareApiPayload(
            newTenants, env["WORKSPACE_ID"], env["PLATFORM_ID"], env["PAYMENT_ID"]
        )

        # Send request to meshStack API
        import_response = mesh_client.declarativeImport(
            env["MESH_API_HOST"], env["MESH_API_USER"], mesh_api_secret, api_payload
        )

        if import_response["status"] == "success":
            logging.info(f"Imported status: {json.dumps(import_response)}")
            result = {"ack": True, "statusCode": 200}
        else:
            logging.error(f"Imported status: {json.dumps(import_response)}")
            result = {"ack": False, "statusCode": 500}

    except mesh_client.RETRYABLE_EXCEPTIONS as e:
        # Log the error after all retries have failed
        logging.error(f"API call failed after all retry attempts: {str(e)}")
        result = {"ack": False, "statusCode": 500}

    return result
