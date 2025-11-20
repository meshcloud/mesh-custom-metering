import requests, logging, traceback
from requests.auth import HTTPBasicAuth
from requests.exceptions import RequestException

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError)

# Define what exceptions should trigger a retry
RETRYABLE_EXCEPTIONS = (
    requests.exceptions.RequestException,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError
)

def prepare_api_payload(
    costs, 
    platform_id: str):
    """
    Converts Tencent cost data into a meshStack compatible payload.

    This function transforms a dictionary of Tencent cost items into a payload
    suitable for sending to the meshStack API endpoint:
    https://docs.meshcloud.io/billing-api/index.html#_put_meshresourceusagereports

    Args:
        costs: A list of dictionaries, where each dictionary represents a cost item.
               Each cost item dictionary should contain the following keys:
               "BusinessCodeName", "UsedAmount", "PriceUnit", "SinglePrice",
               "UsedAmountUnit", "RealCost".
        platform_id: The platform identifier string.

    Returns:
        A dictionary representing the meshStack API payload.
    """
    payload = {
        "apiVersion": "v1",
        "kind": "meshResourceUsageReport",
        "fullPlatformIdentifier": platform_id,
        "source": "Tencent integration",
        "lineItems": []
    }
    
    if not isinstance(costs, list):
        raise TypeError("costs argument must be a list.")
    
    for cost_item in costs:
        if not isinstance(cost_item, dict):
            raise TypeError("Each cost item in the costs list must be a dictionary.")

        required_keys = ["BusinessCodeName", "UsedAmount", "PriceUnit", "SinglePrice", "UsedAmountUnit", "RealCost"]
        if not all(key in cost_item for key in required_keys):
            raise ValueError(f"Cost item is missing one or more required keys: {required_keys}")

        payload["lineItems"].append({
            "productName": cost_item["BusinessCodeName"],
            "usageQuantity": cost_item["UsedAmount"],
            "usageType": cost_item["PriceUnit"],
            "usageCost": cost_item["SinglePrice"],
            "currency": "USD",
            "usageUnit": cost_item["UsedAmountUnit"],
            "totalCost": cost_item["RealCost"]
        })

    return payload

# Retry logic is implemented using tenacity library
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=(retry_if_exception_type(RETRYABLE_EXCEPTIONS))
)
def _import_usage_report(
    api_user: str,
    api_secret: str,
    api_host: str,
    payload,
    platform_tenant_id: str,
    date: str):
    
    result = {}  # Initialize the result dictionary
    
    basic = HTTPBasicAuth(api_user, api_secret)
    url = f"{api_host}/api/meshobjects/meshresourceusagereports/{platform_tenant_id}/{date}"
    headers = {
        "Accept": "application/vnd.meshcloud.api.meshobjects.v1+json",
        "Content-Type": "application/vnd.meshcloud.api.meshobjects.v1+json",
    }
    try:
        response = requests.put(url, headers=headers, auth=basic, json=payload)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        
        result = {
            "status": "success",
            "result": response.text
            }
        
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"HTTP error occurred: {http_err}")
        result = {
            "status": "failure", 
            "message": f"HTTP error: {response.text}" if 'response' in locals() else str(http_err)
            }

    except RETRYABLE_EXCEPTIONS as err:
        logging.warning(f"Retrying due to: {err}")
        raise #re-raise to trigger tenacity.

    except Exception as err:
        logging.error(f"An unexpected error occurred: {err}")
        result = {
            "status": "failure",
            "message": str(err)
            }

    return result

def import_usage_report(
    api_user: str,
    api_secret: str,
    api_host: str,
    payload,
    platform_tenant_id: str,
    date: str
):
    """
    Imports usage report data to the specified API endpoint, with retry handling.

    Args:
        api_user: API username for authentication.
        api_secret: API password for authentication.
        api_host: Base URL of the API.
        payload: JSON payload containing the usage report data.
        platform_tenant_id: ID of the platform tenant.
        date: Date of the usage report.

    Returns:
        A dictionary containing the status of the import and the result/message.
    """

    result = {}  # Initialize the result dictionary

    try:
        result = _import_usage_report(api_user, api_secret, api_host, payload, platform_tenant_id, date)
    
    except RetryError as e:
        last_exception = e.last_attempt.exception()
        logging.error(f"All retry attempts failed. Last error: {last_exception}")
        result = {
            "status": "failure",
            "message": str(last_exception)
            }
    
    except Exception as e:
        logging.error(f"An unexpected error occurred outside of retry: {e}")
        result = {
            "status": "failure",
            "message": str(e)
            }

    return result  # Single return statement