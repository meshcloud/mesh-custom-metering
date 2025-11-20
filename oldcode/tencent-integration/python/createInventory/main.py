import json, logging, traceback

from typing import Dict, Tuple, Any, Optional

from mesh_client import MeshStackClient, MeshStackAPIError
from tencent_client import TencentOrgClient
import env_manager

import functions_framework
import google.cloud.logging
import google.api_core.exceptions
from google.cloud import secretmanager, pubsub_v1

from google.api_core.retry import Retry
from google.api_core.exceptions import GoogleAPICallError, RetryError

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

def publish_msg_to_topic(
    data: Dict[str, Any],
    gcp_project_id: str,
    topic_name: str,
    timeout: float = 5.0,
    retry: Optional[Retry] = None
) -> Dict[str, Any]:
    """
    Publish a message to a Google Cloud Pub/Sub topic.

    Args:
        data (Dict[str, Any]): The message data to publish.
        gcp_project_id (str): The Google Cloud project ID.
        topic_name (str): The name of the Pub/Sub topic.
        timeout (float): The timeout in seconds for the publish operation. Default is 5.0 seconds.
        retry (Optional[Retry]): The retry policy to apply. If None, no retry will be attempted.

    Returns:
        Dict[str, Any]: A dictionary with the status and result or error message.

    Raises:
        ValueError: If any of the required parameters are missing or invalid.
        GoogleAPICallError: If there is an issue with the Google Cloud API call.
        RetryError: If the retry limit is exceeded.
        Exception: For any other unexpected errors.
    """
    response: Dict[str, Any] = {}

    # Validate input parameters
    if not topic_name or not data or not gcp_project_id:
        error_msg = "Missing topic name, message, and/or GCP project ID parameter."
        logging.error(error_msg)
        raise ValueError(error_msg)

    try:
        # Prepare the message
        message_prepared = json.dumps(data)

        # Initialize the PublisherClient
        publisher = pubsub_v1.PublisherClient()

        # Create the topic path
        topic_path = publisher.topic_path(gcp_project_id, topic_name)

        # Publish the message with optional retry and timeout
        publish_future = publisher.publish(topic_path, message_prepared.encode("utf-8"), retry=retry)

        # Wait for the publish operation to complete
        message_id = publish_future.result(timeout=timeout)

        # Prepare the response
        response = {"status": "success", "message_id": message_id}
        return response

    except ValueError as ve:
        logging.error(f"ValueError: {str(ve)}")
        raise
    except GoogleAPICallError as gae:
        logging.error(f"GoogleAPICallError: {str(gae)}")
        raise
    except RetryError as re:
        logging.error(f"RetryError: {str(re)}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error while publishing message to {topic_name}: {str(e)} {traceback.format_exc()}")
        raise
    

def main(request) -> Tuple[str, int]:
    """
    Main function to retrieve environment variables, fetch secrets, build inventory,
    and publish messages to Pub/Sub topics.

    Args:
        request: The request object (typically from a cloud function trigger).

    Returns:
        Tuple[str, int]: A tuple containing a response message and HTTP status code.
    """
    # Initialize the response
    response: Tuple[str, int] = ('Function executed successfully', 200)

    # Set up Google Cloud Logging
    client = google.cloud.logging.Client()
    client.setup_logging()

    # Define required environment variables
    env_vars = {
        "GCP_PROJECT_ID": True,
        "GCP_SECRET_ID_MESHSECRET": True,
        "MESH_API_HOST": True,
        "MESH_API_USER": True,
        "PLATFORM_ID": True,
        "TCT_SECRET_ID": True,
        "GCP_SECRET_ID_TCTSECRET": True, 
        "INVENTORY_TOPIC": True,
        "TENANTS_TOPIC": True
    }

    try:
        # Retrieve environment variables
        env = env_manager.get_env_variables(env_vars)

        # Retrieve secrets from GCP Secret Manager
        mesh_api_secret: str = retrieve_secretManager_secret(
            env["GCP_PROJECT_ID"], env["GCP_SECRET_ID_MESHSECRET"]
        )
        tct_secret_key: str = retrieve_secretManager_secret(
            env["GCP_PROJECT_ID"], env["GCP_SECRET_ID_TCTSECRET"]
        )

        # Initialize clients and retrieve inventory
        mesh_client = MeshStackClient(
            env["MESH_API_HOST"], env["MESH_API_USER"], mesh_api_secret
        )
        mesh_inventory = mesh_client.retrieve_mesh_tenants(env["PLATFORM_ID"])

        tencent_client = TencentOrgClient(env["TCT_SECRET_ID"], tct_secret_key)
        tencent_inventory = tencent_client.retrieve_accounts()

        # Check if both inventories were retrieved successfully
        if mesh_inventory.status != "success" or tencent_inventory.status != "success":
            error_msg = (
                f"Error while building inventory: "
                f"MeshStack: {mesh_inventory.message}, "
                f"Tencent: {tencent_inventory.message}"
            )
            logging.error(error_msg)
            raise RuntimeError(error_msg)

        # Build the combined inventory
        inventory: Dict[str, Any] = {
            "meshStack": MeshStackClient.convert_tenants_to_dict(mesh_inventory.result),
            "tencent": TencentOrgClient.convert_accounts_to_dict(tencent_inventory.result)
        }

        # Publish the inventory to the first Pub/Sub topic
        logging.info("Publishing inventory to Pub/Sub topic.")
        status: Dict[str, str] = publish_msg_to_topic(
            inventory, env["GCP_PROJECT_ID"], env["INVENTORY_TOPIC"]
        )
        if status.get("status") != "success":
            logging.error(f"Failed to publish inventory: {status}")
            raise RuntimeError(f"Failed to publish inventory: {status}")

        # Publish tenant local IDs to the second Pub/Sub topic
        for account_id in inventory["meshStack"]:
            status = publish_msg_to_topic(
                account_id, env["GCP_PROJECT_ID"], env["TENANTS_TOPIC"]
            )
            if status.get("status") != "success":
                logging.error(f"Failed to publish account ID {account_id}: {status}")
                raise RuntimeError(f"Failed to publish account ID {account_id}: {status}")
            logging.info(f"Successfully published account ID {account_id}: {status}")

    except ValueError as ve:
        logging.error(f"ValueError: {ve}")
        response = ('Bad Request: Invalid input or configuration', 400)
    except GoogleAPICallError as gae:
        logging.error(f"GoogleAPICallError: {gae}")
        response = ('Google Cloud API Error', 502)
    except RuntimeError as re:
        logging.error(f"RuntimeError: {re}")
        response = ('Internal Server Error: Failed to process inventory', 500)
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        response = ('Internal Server Error', 500)

    return response
