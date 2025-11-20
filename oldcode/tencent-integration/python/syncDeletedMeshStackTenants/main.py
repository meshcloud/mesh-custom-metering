import json, base64, logging, os, traceback, re
from typing import Dict, List, Any

import env_manager
import mail_client

from jinja2 import Environment, FileSystemLoader

import functions_framework
import google.cloud.logging
from google.cloud import secretmanager
from cloudevents.http import CloudEvent

# --- Global Configuration and Helper Functions ---

# Compiled regex for email validation (compiled once at module load)
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}$")

def is_valid_email_format(email_address: str) -> bool:
    """
    Checks if a given string conforms to a common email address format.
    """
    if not isinstance(email_address, str):
        return False
    return bool(_EMAIL_REGEX.match(email_address))

def parse_email_string_to_list_and_validate(email_string: str) -> List[str]:
    """
    Transforms a comma-separated string of email addresses into a clean list of emails,
    validating each for a common email format. Invalid emails are logged and excluded.
    """
    valid_emails = []

    try:
        if not isinstance(email_string, str):
            logging.warning(f"Input for email parsing must be a string, but received type {type(email_string)}. Returning empty list.")
            return []

        # Split and strip first
        raw_emails = [email.strip() for email in email_string.split(',') if email.strip()]

        if not raw_emails:
            logging.info("No email addresses found in the input string after splitting and stripping.")
            return []

        for email in raw_emails:
            if is_valid_email_format(email):
                valid_emails.append(email)
            else:
                logging.warning(f"Invalid email format detected and excluded: '{email}'")

    except Exception as e:
        logging.error(f"An unexpected error occurred during email parsing or validation: {e}")
        return [] # Return empty list on any unexpected error

    return valid_emails

def render_email_template(template_name: str, context_data: Dict[str, Any], jinja_env: Environment) -> str:
    """
    Loads a Jinja2 template and renders it with provided data.
    """
    template = jinja_env.get_template(template_name)
    return template.render(context_data)


def find_deleted_tenants(inventory: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Compares meshStack and Tencent inventories to identify deleted tenants.
    """
    list_tenants_to_delete = []
    try:
        mesh_stack_inventory = inventory["meshStack"]
        tencent_inventory = inventory["tencent"]
        for tenant in mesh_stack_inventory:
            if not (
                tenant in tencent_inventory
            ):  # meshStack tenant does not exist in Tencent, i.e. was deleted at source
                list_tenants_to_delete.append(
                    {
                        "localId": tenant,
                        "tenantIdentifier": mesh_stack_inventory[tenant]["tenantIdentifier"],
                    }
                )
    except Exception as e:
        logging.error(
            f"Error while extracting deleted tenants: {str(e)} {traceback.format_exc()}"
        )
        list_tenants_to_delete = []

    return list_tenants_to_delete


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


def manage_deleted_tenants(
    deleted_tenants: List[Dict[str, str]],
    jinja_env: Environment,
    env_vars: Dict[str, str],
    mail_secret: str
    ) -> bool:
    """
    Manages the notification process for deleted tenants.
    """
    try:
        notification_subject = "Tencent Account Deletion Notification"

        # Data dictionary to pass to the Jinja2 template

        template_context = {
            "greeting_text": "Hello team",
            "items": deleted_tenants,
            "subject": notification_subject
        }

        # Render the HTML body using Jinja2
        html_email_body = render_email_template('email.html', template_context, jinja_env)
        logging.info(f"Generated HTML email body for {len(deleted_tenants)} deleted tenants.")

        # Check the format of the sender's email
        sender_email = env_vars.get('SENDER_MAIL')
        if not sender_email or not is_valid_email_format(sender_email):
            logging.error(f"Invalid or missing sender mail format: '{sender_email}'")
            return False

        # Check the recipients mail
        recipient_emails_string = env_vars.get("RECIPIENT_MAIL")
        valid_recipient_emails = parse_email_string_to_list_and_validate(recipient_emails_string)

        if not valid_recipient_emails:
            logging.error("No valid recipient email addresses were provided or found.")
            return False
    
        # Call mail_client.send_email with the validated list of recipients
        return mail_client.send_email(
            sender_email=sender_email,
            app_password=mail_secret,
            to_email=valid_recipient_emails, # Passed as a list
            subject=notification_subject,
            body=html_email_body,
            is_html=True
        )
    except Exception as e:
        logging.error(f"Error while managing deleted tenant notification: {str(e)} {traceback.format_exc()}")
        return False

# --- Main Cloud Function Entry Point ---
@functions_framework.cloud_event
def main(cloud_event: CloudEvent):
    """
    Cloud Function triggered by a CloudEvent (e.g., Pub/Sub message).
    It compares cloud inventories and sends notifications for deleted tenants.
    """
    # Instantiates a client and integrates the handler with the Python logging module
    client = google.cloud.logging.Client()
    client.setup_logging()
    logging.info("Cloud Function execution started.")

    # Define required environment variables (more descriptive config)
    env_vars_config = {
        "SENDER_MAIL": {"required": True, "description": "Sender email address."},
        "RECIPIENT_MAIL": {"required": True, "description": "Comma-separated recipient email addresses."},
        "WORKSPACE_ID": {"required": True, "description": "MeshStack Workspace ID."},
        "GCP_PROJECT_ID": {"required": True, "description": "GCP Project ID for Secret Manager."},
        "GCP_SECRET_ID_MESHSECRET": {"required": True, "description": "Secret ID for email sending credentials."},
    }

    try:
        # Setup Jinja2 environment (can be global for performance, but fine here)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_dir = os.path.join(script_dir, 'templates')
        jinja2_conf = Environment(loader=FileSystemLoader(template_dir))

        # Retrieve environment variables using env_manager (assumed to handle errors/missing)
        env = env_manager.get_env_variables(env_vars_config) 
        
        # Retrieve secrets from GCP Secret Manager
        mesh_mail_secret = retrieve_secretManager_secret(
            env["GCP_PROJECT_ID"], env["GCP_SECRET_ID_MESHSECRET"]
        )

        # Process received message data from CloudEvent
        if not cloud_event.data or "message" not in cloud_event.data or "data" not in cloud_event.data["message"]:
            logging.error("CloudEvent data missing 'message' or 'data' field, or data is empty.")
            return {"ack": False, "statusCode": 400}

        encoded_data = cloud_event.data["message"]["data"]
        decoded_payload = base64.b64decode(encoded_data).decode("utf-8")
        data = json.loads(decoded_payload)
        logging.info(f"Received inventory data: {data}")

        # Compare inventories and find deleted tenants
        deleted_tenants = find_deleted_tenants(data)

        # If no deleted tenants, log and exit successfully
        if not deleted_tenants:
            logging.info("No deleted Tencent accounts have been found. Exiting.")
            return {"ack": True, "statusCode": 200}

        # Manage notification for deleted tenants
        notification_success = manage_deleted_tenants(
            deleted_tenants,
            jinja2_conf,
            env,
            mesh_mail_secret
        )

        if not notification_success:
            logging.error("Failed to send notification for deleted tenants.")
            # Return an error status code to trigger Pub/Sub retries (if configured).
            return {"ack": False, "statusCode": 500}
        
        logging.info("Successfully processed deleted tenants and sent notification.")
        return {"ack": True, "statusCode": 200}

    except KeyError as e:
        logging.error(f"Missing required configuration (environment variable or event data key): {e} {traceback.format_exc()}")
        return {"ack": False, "statusCode": 400} # Bad request if configuration is missing
    except json.JSONDecodeError as e:
        logging.error(f"Invalid JSON payload received in CloudEvent: {e} {traceback.format_exc()}")
        return {"ack": False, "statusCode": 400}
    except Exception as e:
        logging.error(
            f"An unhandled error occurred in the main function: {str(e)} {traceback.format_exc()}"
        )
        # Return an error status code for Pub/Sub to potentially retry.
        return {"ack": False, "statusCode": 500}