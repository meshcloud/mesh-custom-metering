import requests, logging, traceback
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

from typing import Dict, List, Any, Optional

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

# Define what exceptions should trigger a retry
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.RequestException,  # Base exception for all requests exceptions
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError,
)

# Using the api https://docs.meshcloud.io/api/index.html#mesh_object_declarative_import to
# import meshstack objects i.e. projects and tenants


# Retry logic is implemented using tenacity library
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=(retry_if_exception_type(RETRYABLE_EXCEPTIONS)),
)
def declarativeImport(api_host: str, api_user: str, api_secret: str, payload):

    response = {}
    try:
        # Prepare API call settings
        basic = HTTPBasicAuth(api_user, api_secret)
        url = api_host.rstrip("/") + "/api/meshobjects"
        headers = {
            "Accept": "application/vnd.meshcloud.api.meshobjects.v1+json",
            "Content-Type": "application/vnd.meshcloud.api.meshobjects.v1+json",
        }
        response = requests.put(url, headers=headers, auth=basic, json=payload)
        if response.status_code == requests.codes.ok:
            response = {"status": "success", "result": logging.info(response.json())}
        else:
            response = {"status": "failure", "message": logging.info(response.json())}

    except Exception as e:
        logging.error(f"Error during API call: {str(e)} {traceback.format_exc()}")
        response = {"status": "failure", "message": str(e)}
        raise

    return response


def prepare_api_payload(
    tenants: List[Dict[str, str]],
    workspace_id: str,
    platform_id: str,
    payment_id: str,
    tags: Optional[Dict[str, List[str]]] = None,
) -> List[Dict[str, Any]]:
    """
    Generate payload for creating new MeshStack projects and tenants.

    The project ID is set to the same value as the tenant ID. Each tenant
    entry results in two objects in the output: one meshProject and one meshTenant.

    Args:
        tenants: List of tenant dictionaries, each containing:
            - localId: Unique identifier for the tenant
            - projectDisplayName: Display name for the project
            - landingZoneId: Identifier for the landing zone
        workspace_id: Identifier for the owning workspace
        platform_id: Identifier for the platform
        payment_id: Identifier for the payment method
        tags: Optional dictionary of tag categories and values to apply to projects

    Returns:
        List of MeshStack object definitions ready for API import

    Raises:
        ValueError: If required parameters are missing or invalid
    """
    # Validate input parameters
    if not tenants:
        logging.warning("No tenant information available to generate the API payload.")
        return []

    if not workspace_id or not platform_id or not payment_id:
        raise ValueError("workspace_id, platform_id, and payment_id are required")

    # Default tags if none provided
    default_tags = {
        "Environment": ["Production"],
        "GxPRelevant": ["No"],
        "DataClassification": ["Confidential"],
        "BusinessUnit": ["Enabling Functions"],
    }

    applied_tags = tags if tags is not None else default_tags
    output = []

    # Validate required fields for each tenant
    valid_tenants = []
    for tenant in tenants:
        if not isinstance(tenant, dict):
            logging.warning(f"Invalid tenant format, expected dictionary: {tenant}")
            continue

        required_fields = ["localId", "projectDisplayName", "landingZoneId"]
        missing_fields = [field for field in required_fields if field not in tenant]

        if missing_fields:
            logging.warning(
                f"Tenant missing required fields {missing_fields}: {tenant}"
            )
            continue

        valid_tenants.append(tenant)

    logging.info(f"Preparing payload for {len(valid_tenants)} valid tenants")

    # Create meshProject and meshTenant objects for each valid tenant
    for tenant in valid_tenants:
        tenant_id = tenant["localId"]

        # Create meshProject object
        project = {
            "apiVersion": "v2",
            "kind": "meshProject",
            "metadata": {
                "name": tenant_id,
                "ownedByWorkspace": workspace_id,
            },
            "spec": {
                "displayName": tenant["projectDisplayName"],
                "paymentMethodIdentifier": payment_id,
                "tags": applied_tags,
            },
        }

        # Create meshTenant object
        mesh_tenant = {
            "apiVersion": "v3",
            "kind": "meshTenant",
            "metadata": {
                "ownedByProject": tenant_id,
                "ownedByWorkspace": workspace_id,
                "platformIdentifier": platform_id,
            },
            "spec": {
                "localId": tenant_id,
                "landingZoneIdentifier": tenant["landingZoneId"],
            },
        }

        output.append(project)
        output.append(mesh_tenant)

    logging.info(f"Created payload with {len(output)} total MeshStack objects")
    return output
