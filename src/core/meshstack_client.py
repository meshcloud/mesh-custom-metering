import requests
import logging
from requests.auth import HTTPBasicAuth
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)
from typing import List, Dict, Optional

RETRYABLE_EXCEPTIONS = (
    requests.exceptions.RequestException,
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.HTTPError
)


class MeshStackClient:
    def __init__(
        self, 
        meshfed_host: str,
        kraken_host: str,
        api_user: str, 
        api_secret: str
    ):
        self.meshfed_host = meshfed_host.rstrip('/')
        self.kraken_host = kraken_host.rstrip('/')
        self.api_user = api_user
        self.api_secret = api_secret
        self.auth = HTTPBasicAuth(api_user, api_secret)
        
        self.meshfed_headers = {
            "Accept": "application/vnd.meshcloud.api.meshtenant.v3.hal+json"
        }
        
        self.kraken_headers = {
            "Accept": "application/vnd.meshcloud.api.meshobjects.v1+json",
            "Content-Type": "application/vnd.meshcloud.api.meshobjects.v1+json",
        }

    def get_tenants(self, platform_id: str, page_size: int = 100, include_deleted: bool = True) -> Dict:
        url = f"{self.meshfed_host}/api/meshobjects/meshtenants"
        current_page = 0
        all_tenant_ids = []
        
        logging.debug(f"Fetching tenants for platform {platform_id}, URL: {url}, include_deleted: {include_deleted}")
        
        try:
            while True:
                params = {
                    "platformIdentifier": platform_id,
                    "size": page_size,
                    "page": current_page
                }
                
                if not include_deleted:
                    params["state"] = "ACTIVE"
                
                logging.debug(f"Requesting page {current_page} with params: {params}")
                
                response = requests.get(url, headers=self.meshfed_headers, auth=self.auth, params=params)
                logging.debug(f"MeshStack tenants API response status: {response.status_code}")
                response.raise_for_status()
                
                data = response.json()
                logging.debug(f"MeshStack tenants API response: {data}")
                tenants = data.get("_embedded", {}).get("meshTenants", [])
                
                logging.debug(f"Found {len(tenants)} tenants on page {current_page}")
                
                for tenant in tenants:
                    spec = tenant.get("spec", {})
                    metadata = tenant.get("metadata", {})
                    local_id = spec.get("localId")
                    deletion_info = metadata.get("deletionInfo")
                    
                    if local_id:
                        tenant_info = {
                            "id": local_id,
                            "status": "DELETED" if deletion_info else "ACTIVE"
                        }
                        all_tenant_ids.append(tenant_info)
                        status_msg = f" (DELETED)" if deletion_info else ""
                        logging.debug(f"Added tenant ID: {local_id}{status_msg}")
                
                page_info = data.get("page", {})
                total_pages = page_info.get("totalPages", 0)
                
                logging.debug(f"Page {current_page + 1} of {total_pages}")
                
                if current_page >= total_pages - 1:
                    break
                
                current_page += 1
            
            active_count = sum(1 for t in all_tenant_ids if t["status"] == "ACTIVE")
            deleted_count = sum(1 for t in all_tenant_ids if t["status"] == "DELETED")
            logging.info(
                f"Retrieved {len(all_tenant_ids)} tenants for platform {platform_id} "
                f"({active_count} active, {deleted_count} deleted)"
            )
            return {
                "status": "success",
                "tenant_ids": [t["id"] for t in all_tenant_ids],
                "tenant_details": all_tenant_ids
            }
        except requests.exceptions.HTTPError as http_err:
            error_msg = f"HTTP error: {response.text}" if 'response' in locals() else str(http_err)
            logging.error(f"HTTP error fetching tenants: {error_msg}")
            return {
                "status": "failure",
                "message": error_msg
            }
        except Exception as err:
            logging.error(f"Error fetching tenants: {err}")
            return {
                "status": "failure",
                "message": str(err)
            }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS)
    )
    def _submit_usage_report(
        self,
        platform_tenant_id: str,
        date: str,
        payload: Dict
    ) -> Dict:
        url = f"{self.kraken_host}/api/meshobjects/meshresourceusagereports/{platform_tenant_id}/{date}"
        
        logging.debug(f"Submitting usage report - URL: {url}")
        logging.debug(f"Payload: {payload}")
        
        try:
            response = requests.put(url, headers=self.kraken_headers, auth=self.auth, json=payload)
            logging.debug(f"MeshStack submit report API response status: {response.status_code}")
            logging.debug(f"MeshStack submit report API response: {response.text}")
            response.raise_for_status()
            
            return {
                "status": "success",
                "result": response.text
            }
        except requests.exceptions.HTTPError as http_err:
            error_msg = f"HTTP error: {response.text}" if 'response' in locals() else str(http_err)
            logging.error(f"HTTP error occurred: {error_msg}")
            return {
                "status": "failure",
                "message": error_msg
            }
        except RETRYABLE_EXCEPTIONS as err:
            logging.warning(f"Retrying due to: {err}")
            raise
        except Exception as err:
            logging.error(f"Unexpected error: {err}")
            return {
                "status": "failure",
                "message": str(err)
            }

    def submit_usage_report(
        self,
        platform_tenant_id: str,
        date: str,
        payload: Dict
    ) -> Dict:
        try:
            return self._submit_usage_report(platform_tenant_id, date, payload)
        except RetryError as e:
            last_exception = e.last_attempt.exception()
            logging.error(f"All retry attempts failed. Last error: {last_exception}")
            return {
                "status": "failure",
                "message": str(last_exception)
            }
        except Exception as e:
            logging.error(f"Unexpected error outside of retry: {e}")
            return {
                "status": "failure",
                "message": str(e)
            }


def prepare_payload(
    line_items: List[Dict],
    platform_id: str,
    source: str
) -> Dict:
    if not isinstance(line_items, list):
        raise TypeError("line_items must be a list")
    
    payload = {
        "apiVersion": "v1",
        "kind": "meshResourceUsageReport",
        "fullPlatformIdentifier": platform_id,
        "source": source,
        "lineItems": line_items
    }
    
    logging.debug(f"Prepared payload with {len(line_items)} line items for platform {platform_id}")
    
    return payload
