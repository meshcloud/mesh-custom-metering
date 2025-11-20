import logging
import requests
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Union
from requests.auth import HTTPBasicAuth
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError
)

# Define custom exceptions for better error handling
class MeshStackAPIError(Exception):
    """Base exception for MeshStack API errors"""
    pass

class MeshStackAuthenticationError(MeshStackAPIError):
    """Raised when authentication fails"""
    pass

class MeshStackResourceNotFoundError(MeshStackAPIError):
    """Raised when a requested resource is not found"""
    pass

# Define data classes for better type hints and data structure
@dataclass
class MeshTenant:
    #local_id: str
    projectId: str
    platformIdentifier: str
    landingZoneId: str
    tenantIdentifier: str
    
    def to_dict(self) -> Dict:
        """Convert MeshTenant instance to dictionary"""
        return asdict(self)

@dataclass
class APIResponse:
    status: str
    result: Optional[Dict] = None
    message: Optional[str] = None

class MeshStackClient:
    """Client for interacting with MeshStack API"""
    
    RETRYABLE_EXCEPTIONS = (
        requests.exceptions.RequestException,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.HTTPError
    )

    def __init__(self, api_host: str, api_user: str, api_secret: str):
        self.api_host = api_host.rstrip('/')
        self.auth = HTTPBasicAuth(api_user, api_secret)
        self.headers = {
            "Accept": "application/vnd.meshcloud.api.meshtenant.v3.hal+json"
        }

    @staticmethod
    def convert_tenants_to_dict(tenants: Dict[str, MeshTenant]) -> Dict:
        """
        Static method to convert a dictionary of MeshTenant objects to a plain dictionary format.
        
        Args:
            tenants: Dictionary with tenant local_ids as keys and MeshTenant objects as values
            
        Returns:
            Dictionary with tenant local_ids as keys and tenant data as dictionary values
        """
        if not tenants:
            return {}
            
        return {
            local_id: tenant.to_dict() 
            for local_id, tenant in tenants.items()
        }

    def _extract_mesh_tenants(self, api_response: Dict) -> List[Dict]:
        """Extract tenant information from the API response"""
        return api_response.get("_embedded", {}).get("meshTenants", [])

    def _filter_tenant_data(self, tenants: List[Dict]) -> Dict[str, MeshTenant]:
        """Filter and transform tenant data into structured objects"""
        output = {}
        for tenant in tenants:
            spec = tenant.get("spec", {})
            metadata = tenant.get("metadata", {})
            
            local_id = spec.get("localId")
            if not local_id:
                continue

            # Check for required fields
            required_fields = {
                "projectId": metadata.get("ownedByProject"),
                "platformIdentifier": metadata.get("platformIdentifier"),
                "landingZoneId": spec.get("landingZoneIdentifier"),
                "tenantIdentifier": metadata.get("tenantIdentifier")
            }

            if all(required_fields.values()):
                output[local_id] = MeshTenant(
                    #local_id=local_id,
                    **required_fields
                )

        return output

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS)
    )
    def _fetch_page(self, platform_identifier: str, page: int, page_size: int = 10) -> APIResponse:
        """Fetch a single page of tenant data"""
        params = {
            "platformIdentifier": platform_identifier,
            "size": page_size,
            "page": page,
        }
        
        url = f"{self.api_host}/api/meshobjects/meshtenants"
        logging.info(f"Sending API request to {url} with params {params}")
        
        response = requests.get(
            url,
            params=params,
            headers=self.headers,
            auth=self.auth
        )

        if response.status_code == requests.codes.ok:
            return APIResponse(status="success", result=response)
        elif response.status_code == 401:
            raise MeshStackAuthenticationError("Authentication failed")
        elif response.status_code == 404:
            raise MeshStackResourceNotFoundError("Resource not found")
        else:
            return APIResponse(
                status="failure",
                message=f"HTTP {response.status_code}: {response.text}"
            )

    def fetch_page(self, platform_identifier: str, page: int, page_size: int = 10) -> APIResponse:
        """Wrapper for _fetch_page with error handling"""
        try:
            return self._fetch_page(platform_identifier, page, page_size)
        except RetryError as e:
            error_msg = f"All retry attempts failed. Last error: {e.last_attempt.exception()}"
            logging.error(error_msg)
            return APIResponse(status="failure", message=error_msg)
        except MeshStackAPIError as e:
            logging.error(str(e))
            return APIResponse(status="failure", message=str(e))

    def retrieve_mesh_tenants(
        self,
        platform_identifier: str,
        page_size: int = 10
    ) -> APIResponse:
        """
        Retrieve all MeshStack tenants for a given platform.
        
        Args:
            platform_identifier: The platform to retrieve tenants for
            page_size: Number of items per page
            
        Returns:
            APIResponse containing dictionary of MeshTenant objects keyed by local_id
        """
        current_page = 0
        temp_tenants = []

        while True:
            response = self.fetch_page(platform_identifier, current_page, page_size)
            
            if response.status != "success":
                logging.error(f"Error while fetching response from MeshStack API: {response.message}")
                return APIResponse(status="failure", message=response.message)

            api_resp_json = response.result.json()
            temp_tenants.extend(self._extract_mesh_tenants(api_resp_json))

            if current_page >= api_resp_json["page"]["totalPages"]:
                break
                
            current_page += 1

        mesh_stack_tenants = self._filter_tenant_data(temp_tenants)
        logging.info(
            f"Retrieved {len(mesh_stack_tenants)} existing MeshStack tenants "
            f"for the platform {platform_identifier}"
        )
        
        return APIResponse(status="success", result=mesh_stack_tenants)
